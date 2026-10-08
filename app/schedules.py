"""学生选课：草稿不占名额，提交时在同一事务中校验并占名额。"""
from collections import defaultdict
from datetime import datetime

from fastapi import HTTPException

from .catalog import CATALOG, meetings_for_offerings, required_offerings
from .db import read_connection, transaction
from .models import ChoiceInput


def student_id_for_user(cursor, user_id: int) -> str:
    cursor.execute(
        "SELECT student_id FROM student_profile WHERE user_id=%s AND status='ACTIVE'",
        (user_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(403, "账号尚未绑定有效学生档案")
    return row["student_id"]


def _open_term(cursor, term_code: str) -> None:
    cursor.execute(
        "SELECT status,registration_opens_at,registration_closes_at "
        "FROM academic_term WHERE term_code=%s FOR SHARE",
        (term_code,),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "学期不存在")
    now = datetime.now()
    if row["status"] != "OPEN" or not (row["registration_opens_at"] <= now <= row["registration_closes_at"]):
        raise HTTPException(409, "当前不在选课开放时间内")


def _validate_positions(choices: list[ChoiceInput], *, complete: bool) -> None:
    positions = [(choice.choice_type, choice.priority) for choice in choices]
    ids = [choice.offering_id for choice in choices]
    if len(set(positions)) != len(positions) or len(set(ids)) != len(ids):
        raise HTTPException(400, "不能重复选择教学班或志愿位置")
    for choice in choices:
        limit = 4 if choice.choice_type == "PRIMARY" else 2
        if not 1 <= choice.priority <= limit:
            raise HTTPException(400, "主选序号应为 1–4，备选序号应为 1–2")
    if complete and (set(positions) != {
        *( ("PRIMARY", n) for n in range(1, 5)),
        *( ("ALTERNATE", n) for n in range(1, 3)),
    }):
        raise HTTPException(400, "提交时必须恰好选择 4 门主选和 2 门备选")


def _ensure_states(cursor, term_code: str, offerings: dict[str, dict]) -> None:
    for offering_id, offering in offerings.items():
        cursor.execute(
            "INSERT INTO offering_registration_state (offering_id,term_code,capacity) "
            "VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE offering_id=offering_id",
            (offering_id, term_code, offering["capacity"]),
        )


def _release_enrollments(cursor, schedule_id: int) -> None:
    cursor.execute(
        "SELECT offering_id FROM enrollment WHERE schedule_id=%s AND status='ENROLLED'",
        (schedule_id,),
    )
    offering_ids = sorted(row["offering_id"] for row in cursor.fetchall())
    for offering_id in offering_ids:
        cursor.execute(
            "UPDATE offering_registration_state SET enrolled_count=enrolled_count-1 "
            "WHERE offering_id=%s AND enrolled_count>0",
            (offering_id,),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("名额计数与选课记录不一致，请联系管理员")
    cursor.execute("DELETE FROM enrollment WHERE schedule_id=%s", (schedule_id,))


def save_draft(user_id: int, term_code: str, choices: list[ChoiceInput]) -> dict:
    _validate_positions(choices, complete=False)
    with transaction() as connection, connection.cursor() as cursor:
        _open_term(cursor, term_code)
        student_id = student_id_for_user(cursor, user_id)
        offerings = required_offerings(cursor, term_code, [c.offering_id for c in choices])
        _ensure_states(cursor, term_code, offerings)
        cursor.execute(
            "SELECT schedule_id,status FROM student_schedule WHERE student_id=%s AND term_code=%s FOR UPDATE",
            (student_id, term_code),
        )
        schedule = cursor.fetchone()
        if schedule and schedule["status"] == "FINALIZED":
            raise HTTPException(409, "最终课表不能修改")
        if schedule:
            schedule_id = schedule["schedule_id"]
            if schedule["status"] == "SUBMITTED":
                _release_enrollments(cursor, schedule_id)
            cursor.execute("DELETE FROM schedule_choice WHERE schedule_id=%s", (schedule_id,))
            cursor.execute(
                "UPDATE student_schedule SET status='DRAFT',submitted_at=NULL WHERE schedule_id=%s",
                (schedule_id,),
            )
        else:
            cursor.execute(
                "INSERT INTO student_schedule (student_id,term_code,status) VALUES (%s,%s,'DRAFT')",
                (student_id, term_code),
            )
            schedule_id = cursor.lastrowid
        for choice in choices:
            cursor.execute(
                "INSERT INTO schedule_choice "
                "(schedule_id,offering_id,term_code,choice_type,priority) VALUES (%s,%s,%s,%s,%s)",
                (schedule_id, choice.offering_id, term_code, choice.choice_type, choice.priority),
            )
        cursor.execute(
            "INSERT INTO audit_log (user_id,action,entity_type,entity_id) VALUES (%s,'SAVE_DRAFT','SCHEDULE',%s)",
            (user_id, str(schedule_id)),
        )
    return get_schedule(user_id, term_code)


def _validate_prerequisites(cursor, student_id: str, offerings: dict[str, dict], primary_ids: list[str]) -> None:
    course_ids = [offerings[offering_id]["course_id"] for offering_id in primary_ids]
    placeholders = ",".join(["%s"] * len(course_ids))
    cursor.execute(
        f"SELECT course_id,prerequisite_course_id,minimum_grade FROM {CATALOG}.course_prerequisite "
        f"WHERE course_id IN ({placeholders})",
        tuple(course_ids),
    )
    requirements = cursor.fetchall()
    if not requirements:
        return
    cursor.execute(
        f"SELECT o.course_id,e.letter_grade FROM enrollment e "
        f"JOIN student_schedule s ON s.schedule_id=e.schedule_id "
        f"JOIN {CATALOG}.course_offering o ON o.offering_id=e.offering_id "
        "WHERE s.student_id=%s AND e.status='COMPLETED' AND e.letter_grade IS NOT NULL",
        (student_id,),
    )
    grade_order = {"A": 4, "B": 3, "C": 2, "D": 1}
    passed = defaultdict(int)
    for row in cursor.fetchall():
        passed[row["course_id"]] = max(passed[row["course_id"]], grade_order.get(row["letter_grade"], 0))
    for requirement in requirements:
        if passed[requirement["prerequisite_course_id"]] < grade_order[requirement["minimum_grade"]]:
            raise HTTPException(400, f"{requirement['course_id']} 尚未满足先修课 {requirement['prerequisite_course_id']}")


def _validate_conflicts(cursor, primary_ids: list[str]) -> None:
    by_day: dict[int, list[dict]] = defaultdict(list)
    for meeting in meetings_for_offerings(cursor, primary_ids):
        for existing in by_day[meeting["weekday"]]:
            if existing["offering_id"] != meeting["offering_id"] and (
                meeting["start_period"] <= existing["end_period"]
                and existing["start_period"] <= meeting["end_period"]
            ):
                raise HTTPException(400, f"主选教学班 {meeting['offering_id']} 与 {existing['offering_id']} 时间冲突")
        by_day[meeting["weekday"]].append(meeting)


def submit_schedule(user_id: int, term_code: str) -> dict:
    with transaction() as connection, connection.cursor() as cursor:
        _open_term(cursor, term_code)
        student_id = student_id_for_user(cursor, user_id)
        cursor.execute(
            "SELECT schedule_id,status FROM student_schedule WHERE student_id=%s AND term_code=%s FOR UPDATE",
            (student_id, term_code),
        )
        schedule = cursor.fetchone()
        if not schedule or schedule["status"] != "DRAFT":
            raise HTTPException(409, "请先保存草稿；已提交课表无需重复提交")
        schedule_id = schedule["schedule_id"]
        cursor.execute(
            "SELECT choice_id,offering_id,choice_type,priority FROM schedule_choice WHERE schedule_id=%s",
            (schedule_id,),
        )
        rows = cursor.fetchall()
        choices = [ChoiceInput(**row) for row in rows]
        _validate_positions(choices, complete=True)
        offerings = required_offerings(cursor, term_code, [c.offering_id for c in choices])
        primary_ids = [c.offering_id for c in choices if c.choice_type == "PRIMARY"]
        _validate_prerequisites(cursor, student_id, offerings, primary_ids)
        _validate_conflicts(cursor, primary_ids)
        for offering_id in sorted(primary_ids):
            cursor.execute(
                "SELECT capacity,enrolled_count,status FROM offering_registration_state "
                "WHERE offering_id=%s AND term_code=%s FOR UPDATE",
                (offering_id, term_code),
            )
            state = cursor.fetchone()
            if not state or state["status"] != "OPEN" or state["enrolled_count"] >= state["capacity"]:
                raise HTTPException(409, f"教学班 {offering_id} 已关闭或已满")
        for choice in rows:
            if choice["choice_type"] == "PRIMARY":
                cursor.execute(
                    "UPDATE offering_registration_state SET enrolled_count=enrolled_count+1 WHERE offering_id=%s",
                    (choice["offering_id"],),
                )
                cursor.execute(
                    "INSERT INTO enrollment (schedule_id,choice_id,offering_id,status) VALUES (%s,%s,%s,'ENROLLED')",
                    (schedule_id, choice["choice_id"], choice["offering_id"]),
                )
                cursor.execute("UPDATE schedule_choice SET status='ENROLLED' WHERE choice_id=%s", (choice["choice_id"],))
        cursor.execute(
            "UPDATE student_schedule SET status='SUBMITTED',submitted_at=NOW() WHERE schedule_id=%s",
            (schedule_id,),
        )
        cursor.execute(
            "INSERT INTO audit_log (user_id,action,entity_type,entity_id) VALUES (%s,'SUBMIT_SCHEDULE','SCHEDULE',%s)",
            (user_id, str(schedule_id)),
        )
    return get_schedule(user_id, term_code)


def delete_schedule(user_id: int, term_code: str) -> dict:
    """删除开放学期的课表；已提交的主选名额必须同时释放。"""
    with transaction() as connection, connection.cursor() as cursor:
        _open_term(cursor, term_code)
        student_id = student_id_for_user(cursor, user_id)
        cursor.execute(
            "SELECT schedule_id,status FROM student_schedule "
            "WHERE student_id=%s AND term_code=%s FOR UPDATE",
            (student_id, term_code),
        )
        schedule = cursor.fetchone()
        if not schedule or schedule["status"] == "DELETED":
            raise HTTPException(404, "当前学期没有可删除的课表")
        if schedule["status"] == "FINALIZED":
            raise HTTPException(409, "最终课表不能删除")
        schedule_id = schedule["schedule_id"]
        if schedule["status"] == "SUBMITTED":
            _release_enrollments(cursor, schedule_id)
        cursor.execute("DELETE FROM schedule_choice WHERE schedule_id=%s", (schedule_id,))
        cursor.execute(
            "UPDATE student_schedule SET status='DELETED',submitted_at=NULL "
            "WHERE schedule_id=%s",
            (schedule_id,),
        )
        cursor.execute(
            "INSERT INTO audit_log (user_id,action,entity_type,entity_id) "
            "VALUES (%s,'DELETE_SCHEDULE','SCHEDULE',%s)",
            (user_id, str(schedule_id)),
        )
    return {"term_code": term_code, "status": "EMPTY", "choices": []}


def get_schedule(user_id: int, term_code: str) -> dict:
    with read_connection() as connection, connection.cursor() as cursor:
        student_id = student_id_for_user(cursor, user_id)
        cursor.execute(
            "SELECT schedule_id,status,submitted_at,finalized_at FROM student_schedule "
            "WHERE student_id=%s AND term_code=%s",
            (student_id, term_code),
        )
        schedule = cursor.fetchone()
        if not schedule or schedule["status"] == "DELETED":
            return {"term_code": term_code, "status": "EMPTY", "choices": []}
        cursor.execute(
            "SELECT c.choice_id,c.offering_id,c.choice_type,c.priority,c.status,e.status AS enrollment_status "
            "FROM schedule_choice c LEFT JOIN enrollment e ON e.choice_id=c.choice_id "
            "WHERE c.schedule_id=%s ORDER BY FIELD(c.choice_type,'PRIMARY','ALTERNATE'),c.priority",
            (schedule["schedule_id"],),
        )
        choices = cursor.fetchall()
        return {
            "term_code": term_code,
            "schedule_id": schedule["schedule_id"],
            "status": schedule["status"],
            "submitted_at": schedule["submitted_at"],
            "finalized_at": schedule["finalized_at"],
            "choices": choices,
        }
