"""教师按任教资格认领/退出教学班；目录库始终只读。"""
from datetime import datetime

from fastapi import HTTPException

from .catalog import meetings_for_offerings, offerings_for_term, required_offerings
from .db import read_connection, transaction
from .schedules import _open_term


def _professor_id(cursor, user_id: int, *, lock: bool = False) -> str:
    cursor.execute(
        "SELECT professor_id FROM professor_profile WHERE user_id=%s AND status='ACTIVE'" + (" FOR UPDATE" if lock else ""),
        (user_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(403, "账号尚未绑定有效教师档案")
    return row["professor_id"]


def teacher_offerings(user_id: int, term_code: str) -> dict:
    with read_connection() as connection, connection.cursor() as cursor:
        professor_id = _professor_id(cursor, user_id)
        cursor.execute(
            "SELECT course_id FROM professor_qualification WHERE professor_id=%s",
            (professor_id,),
        )
        qualified = {row["course_id"] for row in cursor.fetchall()}
        cursor.execute(
            "SELECT status,registration_opens_at,registration_closes_at FROM academic_term WHERE term_code=%s",
            (term_code,),
        )
        term = cursor.fetchone()
        if not term:
            raise HTTPException(404, "学期不存在")
    offerings = [
        {**offering, "is_mine": offering["professor_id"] == professor_id}
        for offering in offerings_for_term(term_code)
        if offering["course_id"] in qualified
    ]
    now = datetime.now()
    registration_open = term["status"] == "OPEN" and term["registration_opens_at"] <= now <= term["registration_closes_at"]
    return {
        "professor_id": professor_id,
        "term_code": term_code,
        "term_status": term["status"],
        "registration_open": registration_open,
        "offerings": offerings,
    }


def current_roster(user_id: int, term_code: str, offering_id: str) -> dict:
    """教师只可查看自己教学班在开放学期内已提交的报名名单。"""
    with read_connection() as connection, connection.cursor() as cursor:
        professor_id = _professor_id(cursor, user_id)
        cursor.execute(
            "SELECT t.status AS term_status,r.status AS offering_status "
            "FROM teaching_assignment a "
            "JOIN offering_registration_state r ON r.offering_id=a.offering_id "
            "JOIN academic_term t ON t.term_code=r.term_code "
            "WHERE a.offering_id=%s AND a.professor_id=%s AND r.term_code=%s",
            (offering_id, professor_id, term_code),
        )
        state = cursor.fetchone()
        if not state:
            raise HTTPException(404, "教学班不存在或不属于你")
        if state["term_status"] != "OPEN" or state["offering_status"] != "OPEN":
            raise HTTPException(409, "选课已关闭，请查看最终名单")
        cursor.execute(
            "SELECT s.student_id,p.full_name,e.enrolled_at "
            "FROM enrollment e JOIN student_schedule s ON s.schedule_id=e.schedule_id "
            "JOIN student_profile p ON p.student_id=s.student_id "
            "WHERE e.offering_id=%s AND s.term_code=%s "
            "AND s.status='SUBMITTED' AND e.status='ENROLLED' "
            "ORDER BY s.student_id",
            (offering_id, term_code),
        )
        students = list(cursor.fetchall())
    return {"term_code": term_code, "offering_id": offering_id, "students": students}


def _check_teaching_conflict(cursor, professor_id: str, term_code: str, offering_id: str) -> None:
    cursor.execute(
        "SELECT a.offering_id FROM teaching_assignment a "
        "JOIN offering_registration_state s ON s.offering_id=a.offering_id "
        "WHERE a.professor_id=%s AND s.term_code=%s",
        (professor_id, term_code),
    )
    assigned = [row["offering_id"] for row in cursor.fetchall()]
    if not assigned:
        return
    meetings = meetings_for_offerings(cursor, [offering_id] + assigned)
    proposed = [m for m in meetings if m["offering_id"] == offering_id]
    existing = [m for m in meetings if m["offering_id"] != offering_id]
    for a in proposed:
        for b in existing:
            if a["weekday"] == b["weekday"] and a["start_period"] <= b["end_period"] and b["start_period"] <= a["end_period"]:
                raise HTTPException(409, f"与已认领的教学班 {b['offering_id']} 上课时间冲突")


def claim_offering(user_id: int, term_code: str, offering_id: str) -> dict:
    with transaction() as connection, connection.cursor() as cursor:
        _open_term(cursor, term_code)
        professor_id = _professor_id(cursor, user_id, lock=True)
        offering = required_offerings(cursor, term_code, [offering_id])[offering_id]
        cursor.execute(
            "SELECT 1 FROM professor_qualification WHERE professor_id=%s AND course_id=%s",
            (professor_id, offering["course_id"]),
        )
        if not cursor.fetchone():
            raise HTTPException(403, "你没有教授这门课程的资格")
        cursor.execute(
            "INSERT INTO offering_registration_state (offering_id,term_code,capacity) "
            "VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE offering_id=offering_id",
            (offering_id, term_code, offering["capacity"]),
        )
        cursor.execute(
            "SELECT status FROM offering_registration_state WHERE offering_id=%s FOR UPDATE",
            (offering_id,),
        )
        state = cursor.fetchone()
        if state["status"] != "OPEN":
            raise HTTPException(409, "该教学班不再开放教师认领")
        cursor.execute(
            "SELECT professor_id FROM teaching_assignment WHERE offering_id=%s",
            (offering_id,),
        )
        assignment = cursor.fetchone()
        if assignment:
            if assignment["professor_id"] == professor_id:
                raise HTTPException(409, "你已经认领了该教学班")
            raise HTTPException(409, "该教学班已有教师认领")
        _check_teaching_conflict(cursor, professor_id, term_code, offering_id)
        cursor.execute(
            "INSERT INTO teaching_assignment (offering_id,professor_id) VALUES (%s,%s)",
            (offering_id, professor_id),
        )
        cursor.execute(
            "INSERT INTO audit_log (user_id,action,entity_type,entity_id) "
            "VALUES (%s,'CLAIM_OFFERING','OFFERING',%s)",
            (user_id, offering_id),
        )
    return teacher_offerings(user_id, term_code)


def release_offering(user_id: int, term_code: str, offering_id: str) -> dict:
    with transaction() as connection, connection.cursor() as cursor:
        _open_term(cursor, term_code)
        professor_id = _professor_id(cursor, user_id)
        required_offerings(cursor, term_code, [offering_id])
        cursor.execute(
            "SELECT status FROM offering_registration_state WHERE offering_id=%s FOR UPDATE",
            (offering_id,),
        )
        state = cursor.fetchone()
        if not state or state["status"] != "OPEN":
            raise HTTPException(409, "该教学班不能退出认领")
        cursor.execute(
            "DELETE FROM teaching_assignment WHERE offering_id=%s AND professor_id=%s",
            (offering_id, professor_id),
        )
        if cursor.rowcount != 1:
            raise HTTPException(409, "该教学班不是由你认领的")
        cursor.execute(
            "INSERT INTO audit_log (user_id,action,entity_type,entity_id) "
            "VALUES (%s,'RELEASE_OFFERING','OFFERING',%s)",
            (user_id, offering_id),
        )
    return teacher_offerings(user_id, term_code)
