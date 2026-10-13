"""一次性重建本机 v6 测试库的计算机系演示记录。

先备份两个测试库，再运行本脚本；旧目录课程须随后按
database/18_remove_old_cs_catalog.sql 在管理员连接中删除。
本脚本故意拒绝对非 v6 测试库执行。
"""

from app.config import ROOT, settings
from app.db import transaction


OLD_COURSES = ("CS101", "CS102", "CS201", "CS202", "CS301", "CS302", "CS303")
NEW_COURSES = ("212002", "211001", "211002", "941015", "213001",
               "212003", "211003", "211004", "211011", "211012")
SPRING_PRIMARY = ("2026SP-212002-01", "2026SP-211001-01",
                  "2026SP-211002-01", "2026SP-941015-01")
SPRING_ALTERNATE = ("2026SP-213001-01", "2026SP-212002-02")
GRADES = {
    "S001": ("F", "B", "A", "B"),
    "S002": ("B", "A", "B", "B"),
    "S003": ("A", "B", "A", "C"),
}


def main() -> None:
    if (settings.db_name, settings.catalog_db) != (
        "course_registration_v6_test", "course_catalog_v6_test"
    ):
        raise SystemExit("拒绝执行：仅允许本机 v6 测试库")
    backup = ROOT / ".local-backups/pre-cs-curriculum-rebuild-20261013-complete.sql"
    if not backup.is_file() or backup.stat().st_size < 10000:
        raise SystemExit("拒绝执行：未找到完整的事前备份")

    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT student_id FROM student_profile ORDER BY student_id")
        if [row["student_id"] for row in cursor.fetchall()] != list(GRADES):
            raise RuntimeError("学生名单已变化，未执行清理")
        cursor.execute("SELECT professor_id FROM professor_profile WHERE professor_id='P001' AND status='ACTIVE'")
        if cursor.fetchone() is None:
            raise RuntimeError("P001 教师不存在或已停用")
        cursor.execute("SELECT term_code,status FROM academic_term WHERE term_code IN ('2026SP','2026FA')")
        if {r["term_code"]: r["status"] for r in cursor.fetchall()} != {"2026SP": "CLOSED", "2026FA": "OPEN"}:
            raise RuntimeError("学期状态已变化，未执行清理")

        catalog = f"`{settings.catalog_db}`"
        cursor.execute(
            f"SELECT offering_id FROM {catalog}.course_offering WHERE course_id IN ({','.join(['%s'] * len(OLD_COURSES))})",
            OLD_COURSES,
        )
        old_offerings = tuple(r["offering_id"] for r in cursor.fetchall())
        cursor.execute(
            f"SELECT offering_id,term_code,capacity FROM {catalog}.course_offering "
            f"WHERE course_id IN ({','.join(['%s'] * len(NEW_COURSES))}) AND term_code IN ('2026SP','2026FA')",
            NEW_COURSES,
        )
        new_offerings = cursor.fetchall()
        if len(new_offerings) != 17 or len(old_offerings) == 0:
            raise RuntimeError("目录教学班数量与预期不符，未执行清理")
        if not set(SPRING_PRIMARY + SPRING_ALTERNATE) <= {r["offering_id"] for r in new_offerings}:
            raise RuntimeError("春季演示教学班缺失")

        # 按外键的反向次序删除旧课表、成绩及相关计费测试快照。
        for table in ("grade_change_log", "billing_outbox", "mock_billing_receipt",
                      "enrollment", "schedule_choice", "student_schedule"):
            cursor.execute(f"DELETE FROM `{table}`")
        cursor.execute("DELETE FROM audit_log WHERE entity_type IN ('SCHEDULE','ENROLLMENT')")
        if old_offerings:
            marks = ",".join(["%s"] * len(old_offerings))
            cursor.execute(f"DELETE FROM teaching_assignment WHERE offering_id IN ({marks})", old_offerings)
            cursor.execute(f"DELETE FROM offering_registration_state WHERE offering_id IN ({marks})", old_offerings)
            cursor.execute(f"DELETE FROM audit_log WHERE entity_type='OFFERING' AND entity_id IN ({marks})", old_offerings)
        cursor.execute(
            f"DELETE FROM professor_qualification WHERE course_id IN ({','.join(['%s'] * len(OLD_COURSES))})",
            OLD_COURSES,
        )
        cursor.execute("UPDATE offering_registration_state SET enrolled_count=0 WHERE enrolled_count<>0")
        fall_offerings = tuple(r["offering_id"] for r in new_offerings if r["term_code"] == "2026FA")
        cursor.execute(
            f"DELETE FROM teaching_assignment WHERE offering_id IN ({','.join(['%s'] * len(fall_offerings))})",
            fall_offerings,
        )
        cursor.execute("UPDATE student_profile SET full_name='学生二' WHERE student_id='S002'")
        cursor.execute("UPDATE student_profile SET full_name='学生三' WHERE student_id='S003'")
        cursor.execute("UPDATE professor_profile SET full_name='教师一' WHERE professor_id='P001'")

        cursor.executemany(
            "INSERT IGNORE INTO professor_qualification (professor_id,course_id) VALUES ('P001',%s)",
            [(course_id,) for course_id in NEW_COURSES],
        )
        for offering in new_offerings:
            offering_id = offering["offering_id"]
            is_primary = offering_id in SPRING_PRIMARY
            is_spring = offering["term_code"] == "2026SP"
            status = "COMMITTED" if is_primary else ("CANCELLED" if is_spring else "OPEN")
            reason = "TOO_FEW_STUDENTS" if is_spring and not is_primary else None
            cursor.execute(
                "INSERT INTO offering_registration_state "
                "(offering_id,term_code,capacity,enrolled_count,status,cancellation_reason) "
                "VALUES (%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE capacity=VALUES(capacity), "
                "enrolled_count=VALUES(enrolled_count),status=VALUES(status), "
                "cancellation_reason=VALUES(cancellation_reason)",
                (offering_id, offering["term_code"], offering["capacity"],
                 3 if is_primary else 0, status, reason),
            )
        cursor.executemany(
            "INSERT INTO teaching_assignment (offering_id,professor_id) VALUES (%s,'P001') "
            "ON DUPLICATE KEY UPDATE professor_id=VALUES(professor_id)",
            [(offering_id,) for offering_id in SPRING_PRIMARY + SPRING_ALTERNATE],
        )

        for student_id, grades in GRADES.items():
            cursor.execute(
                "INSERT INTO student_schedule (student_id,term_code,status,submitted_at,finalized_at) "
                "VALUES (%s,'2026SP','FINALIZED','2026-02-15 12:00:00','2026-03-02 12:00:00')",
                (student_id,),
            )
            schedule_id = cursor.lastrowid
            for priority, (offering_id, grade) in enumerate(zip(SPRING_PRIMARY, grades), 1):
                cursor.execute(
                    "INSERT INTO schedule_choice "
                    "(schedule_id,offering_id,term_code,choice_type,priority,status) "
                    "VALUES (%s,%s,'2026SP','PRIMARY',%s,'ENROLLED')",
                    (schedule_id, offering_id, priority),
                )
                choice_id = cursor.lastrowid
                cursor.execute(
                    "INSERT INTO enrollment "
                    "(schedule_id,choice_id,offering_id,status,letter_grade,graded_by,graded_at) "
                    "VALUES (%s,%s,%s,'COMPLETED',%s,'P001','2026-06-30 12:00:00')",
                    (schedule_id, choice_id, offering_id, grade),
                )
            for priority, offering_id in enumerate(SPRING_ALTERNATE, 1):
                cursor.execute(
                    "INSERT INTO schedule_choice "
                    "(schedule_id,offering_id,term_code,choice_type,priority,status) "
                    "VALUES (%s,%s,'2026SP','ALTERNATE',%s,'SELECTED')",
                    (schedule_id, offering_id, priority),
                )
    print("已重建业务演示数据：3 个春季课表、18 个志愿、12 条成绩；旧秋季课表已清空。")


if __name__ == "__main__":
    main()
