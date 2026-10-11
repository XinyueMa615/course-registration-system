"""Prepare a ready-to-close 2026SU grading demo in the isolated v6 databases.

Run database/14_grade_demo_catalog_v6_test.sql first with a catalog administrator.
This script never changes 2026FA and never closes or completes the demo term.
"""
from datetime import datetime, timedelta

from app.closing import preview_close
from app.config import settings
from app.db import read_connection, transaction


TERM = "2026SU"
PRIMARY = (
    ("2026SU-CS101-01", "P001"),
    ("2026SU-CS302-01", "P001"),
    ("2026SU-MA101-01", "P002"),
    ("2026SU-AR101-01", "P003"),
)
ALTERNATE = (
    ("2026SU-CS201-01", "P001"),
    ("2026SU-AR102-01", "P003"),
)
STUDENTS = ("S001", "S002", "S003")
OFFERINGS = PRIMARY + ALTERNATE


def main() -> None:
    if (settings.db_name, settings.catalog_db) != (
        "course_registration_v6_test", "course_catalog_v6_test"
    ):
        raise RuntimeError("此脚本只允许写入第六版隔离测试数据库")

    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM academic_term WHERE term_code=%s", (TERM,))
        if cursor.fetchone():
            raise RuntimeError(f"{TERM} 已存在；为保护已有数据，脚本不会重复执行")
        cursor.execute(
            f"SELECT offering_id,capacity FROM `{settings.catalog_db}`.course_offering "
            "WHERE term_code=%s", (TERM,)
        )
        catalog = {row["offering_id"]: row for row in cursor.fetchall()}
        expected = {offering_id for offering_id, _ in OFFERINGS}
        if set(catalog) != expected or any(row["capacity"] < 3 for row in catalog.values()):
            raise RuntimeError("演示课程目录不完整；请先执行 14_grade_demo_catalog_v6_test.sql")
        cursor.execute(
            "SELECT student_id FROM student_profile WHERE student_id IN (%s,%s,%s) AND status='ACTIVE'",
            STUDENTS,
        )
        if {row["student_id"] for row in cursor.fetchall()} != set(STUDENTS):
            raise RuntimeError("演示学生 S001、S002、S003 必须全部处于 ACTIVE 状态")
        cursor.execute(
            "SELECT professor_id FROM professor_profile "
            "WHERE professor_id IN (%s,%s,%s) AND status='ACTIVE'",
            ("P001", "P002", "P003"),
        )
        if {row["professor_id"] for row in cursor.fetchall()} != {"P001", "P002", "P003"}:
            raise RuntimeError("演示教师 P001、P002、P003 必须全部处于 ACTIVE 状态")
        cursor.execute(
            "SELECT professor_id,course_id FROM professor_qualification "
            "WHERE professor_id IN (%s,%s,%s)", ("P001", "P002", "P003")
        )
        qualified = {(row["professor_id"], row["course_id"]) for row in cursor.fetchall()}
        if any((professor_id, offering_id.split("-")[1]) not in qualified
               for offering_id, professor_id in OFFERINGS):
            raise RuntimeError("演示教师缺少对应课程的任教资格")

    now = datetime.now().replace(microsecond=0)
    opened_at = now - timedelta(days=30)
    closed_for_registration_at = now - timedelta(minutes=1)
    submitted_at = now - timedelta(days=2)

    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO academic_term "
            "(term_code,year,semester,registration_opens_at,registration_closes_at,status,tuition_per_credit) "
            "VALUES (%s,2026,'SUMMER',%s,%s,'OPEN',0)",
            (TERM, opened_at, closed_for_registration_at),
        )
        for offering_id, professor_id in OFFERINGS:
            cursor.execute(
                "INSERT INTO offering_registration_state "
                "(offering_id,term_code,capacity,enrolled_count) VALUES (%s,%s,%s,%s)",
                (offering_id, TERM, catalog[offering_id]["capacity"], 3 if (offering_id, professor_id) in PRIMARY else 0),
            )
            cursor.execute(
                "INSERT INTO teaching_assignment (offering_id,professor_id) VALUES (%s,%s)",
                (offering_id, professor_id),
            )
        for student_id in STUDENTS:
            cursor.execute(
                "INSERT INTO student_schedule (student_id,term_code,status,submitted_at) "
                "VALUES (%s,%s,'SUBMITTED',%s)",
                (student_id, TERM, submitted_at),
            )
            schedule_id = cursor.lastrowid
            for priority, (offering_id, _) in enumerate(PRIMARY, start=1):
                cursor.execute(
                    "INSERT INTO schedule_choice "
                    "(schedule_id,offering_id,term_code,choice_type,priority,status) "
                    "VALUES (%s,%s,%s,'PRIMARY',%s,'ENROLLED')",
                    (schedule_id, offering_id, TERM, priority),
                )
                choice_id = cursor.lastrowid
                cursor.execute(
                    "INSERT INTO enrollment "
                    "(schedule_id,choice_id,offering_id,status,enrolled_at) "
                    "VALUES (%s,%s,%s,'ENROLLED',%s)",
                    (schedule_id, choice_id, offering_id, submitted_at),
                )
            for priority, (offering_id, _) in enumerate(ALTERNATE, start=1):
                cursor.execute(
                    "INSERT INTO schedule_choice "
                    "(schedule_id,offering_id,term_code,choice_type,priority,status) "
                    "VALUES (%s,%s,%s,'ALTERNATE',%s,'SELECTED')",
                    (schedule_id, offering_id, TERM, priority),
                )

    preview = preview_close(TERM)
    if (not preview["can_close"] or preview["submitted_schedules"] != 3
            or len(preview["committed_offerings"]) != 4
            or preview["billing_transactions"] != 3):
        raise RuntimeError(f"演示学期已建立，但关闭预览不符合预期：{preview}")
    print("2026SU 成绩演示数据已准备：3 份已提交课表，4 个可保留教学班，每班 3 名学生。")
    print("请在教务页面先预览并正式关闭 2026SU，再确认教学结束；不要关闭 2026FA。")


if __name__ == "__main__":
    main()
