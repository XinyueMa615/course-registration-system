"""教师最终名单与成绩；学生只读自己的已完成成绩单。"""
from __future__ import annotations

from fastapi import HTTPException

from .catalog import CATALOG
from .db import read_connection, transaction
from .professors import _professor_id


def _previous_completed_term(cursor) -> str | None:
    """以教务确认教学结束的最近学期为上一已完成学期。"""
    cursor.execute(
        "SELECT term_code FROM academic_term WHERE status='CLOSED' AND completed_at IS NOT NULL "
        "ORDER BY year DESC, FIELD(semester,'SPRING','SUMMER','FALL','WINTER') DESC LIMIT 1"
    )
    row = cursor.fetchone()
    return row["term_code"] if row else None


def grade_offerings(user_id: int) -> dict:
    with read_connection() as connection, connection.cursor() as cursor:
        professor_id = _professor_id(cursor, user_id)
        term_code = _previous_completed_term(cursor)
        if not term_code:
            return {"term_code": None, "offerings": []}
        cursor.execute(
            f"SELECT r.offering_id,o.course_id,o.section_code,c.title "
            f"FROM teaching_assignment a JOIN offering_registration_state r ON r.offering_id=a.offering_id "
            f"JOIN {CATALOG}.course_offering o ON o.offering_id=r.offering_id "
            f"JOIN {CATALOG}.course c ON c.course_id=o.course_id "
            "WHERE a.professor_id=%s AND r.term_code=%s AND r.status='COMMITTED' "
            "ORDER BY o.course_id,o.section_code",
            (professor_id, term_code),
        )
        offerings = list(cursor.fetchall())
    return {"term_code": term_code, "offerings": offerings}


def _owned_closed_offering(cursor, professor_id: str, term_code: str, offering_id: str) -> dict:
    previous = _previous_completed_term(cursor)
    if term_code != previous:
        raise HTTPException(409, "成绩只能录入最近一个已完成学期的教学班")
    cursor.execute(
        "SELECT t.status AS term_status,r.status AS offering_status "
        "FROM academic_term t JOIN offering_registration_state r ON r.term_code=t.term_code "
        "JOIN teaching_assignment a ON a.offering_id=r.offering_id "
        "WHERE t.term_code=%s AND r.offering_id=%s AND a.professor_id=%s",
        (term_code, offering_id, professor_id),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "教学班不存在或不属于你")
    if row["term_status"] != "CLOSED":
        raise HTTPException(409, "选课尚未正式关闭，最终名单和成绩暂不可用")
    if row["offering_status"] != "COMMITTED":
        raise HTTPException(409, "该教学班已取消，不能录入成绩")
    return row


def roster(user_id: int, term_code: str, offering_id: str) -> dict:
    with read_connection() as connection, connection.cursor() as cursor:
        professor_id = _professor_id(cursor, user_id)
        _owned_closed_offering(cursor, professor_id, term_code, offering_id)
        cursor.execute(
            "SELECT e.enrollment_id,s.student_id,p.full_name,e.status,e.letter_grade,e.graded_at "
            "FROM enrollment e JOIN student_schedule s ON s.schedule_id=e.schedule_id "
            "JOIN student_profile p ON p.student_id=s.student_id "
            "WHERE e.offering_id=%s AND s.term_code=%s AND s.status='FINALIZED' "
            "AND e.status IN ('COMMITTED','COMPLETED') ORDER BY s.student_id",
            (offering_id, term_code),
        )
        students = list(cursor.fetchall())
    return {"term_code": term_code, "offering_id": offering_id, "students": students}


def set_grade(user_id: int, term_code: str, offering_id: str, enrollment_id: int, grade: str) -> dict:
    with transaction() as connection, connection.cursor() as cursor:
        professor_id = _professor_id(cursor, user_id)
        # The same term lock is taken by the close operation, so grade entry cannot race it.
        cursor.execute("SELECT status FROM academic_term WHERE term_code=%s FOR UPDATE", (term_code,))
        term = cursor.fetchone()
        if not term:
            raise HTTPException(404, "学期不存在")
        _owned_closed_offering(cursor, professor_id, term_code, offering_id)
        cursor.execute(
            "SELECT e.enrollment_id,e.status,e.letter_grade,s.student_id "
            "FROM enrollment e JOIN student_schedule s ON s.schedule_id=e.schedule_id "
            "WHERE e.enrollment_id=%s AND e.offering_id=%s AND s.term_code=%s "
            "AND s.status='FINALIZED' FOR UPDATE",
            (enrollment_id, offering_id, term_code),
        )
        row = cursor.fetchone()
        if not row or row["status"] not in ("COMMITTED", "COMPLETED"):
            raise HTTPException(404, "学生不在该教学班的最终名单中")
        if row["letter_grade"] == grade and row["status"] == "COMPLETED":
            return {"enrollment_id": enrollment_id, "student_id": row["student_id"], "letter_grade": grade, "changed": False}
        cursor.execute(
            "UPDATE enrollment SET status='COMPLETED',letter_grade=%s,graded_by=%s,graded_at=NOW() "
            "WHERE enrollment_id=%s",
            (grade, professor_id, enrollment_id),
        )
        cursor.execute(
            "INSERT INTO grade_change_log (enrollment_id,professor_id,old_grade,new_grade) "
            "VALUES (%s,%s,%s,%s)",
            (enrollment_id, professor_id, row["letter_grade"], grade),
        )
        cursor.execute(
            "INSERT INTO audit_log (user_id,action,entity_type,entity_id) "
            "VALUES (%s,'SET_GRADE','ENROLLMENT',%s)",
            (user_id, str(enrollment_id)),
        )
    return {"enrollment_id": enrollment_id, "student_id": row["student_id"], "letter_grade": grade, "changed": True}


def report_card(user_id: int) -> dict:
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT student_id FROM student_profile WHERE user_id=%s", (user_id,))
        student = cursor.fetchone()
        if not student:
            raise HTTPException(403, "账号尚未绑定学生档案")
        term_code = _previous_completed_term(cursor)
        if not term_code:
            return {"student_id": student["student_id"], "term_code": None, "courses": []}
        cursor.execute(
            f"SELECT v.term_code,v.offering_id,o.course_id,c.title,c.credits,v.letter_grade,v.graded_at "
            f"FROM v_report_card v JOIN {CATALOG}.course_offering o ON o.offering_id=v.offering_id "
            f"JOIN {CATALOG}.course c ON c.course_id=o.course_id "
            "WHERE v.student_id=%s AND v.term_code=%s ORDER BY o.course_id,o.section_code",
            (student["student_id"], term_code),
        )
        courses = list(cursor.fetchall())
    return {"student_id": student["student_id"], "term_code": term_code, "courses": courses}
