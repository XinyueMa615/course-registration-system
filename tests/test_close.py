"""选课截止集成测试；仅在 RUN_DB_INTEGRATION=1 的隔离测试库运行。"""
from datetime import datetime, timedelta
from decimal import Decimal
import json
import os
import unittest
from uuid import uuid4

from fastapi import HTTPException

from app.closing import close_registration, preview_close
from app.db import read_connection, transaction
from app.models import TermCreate, TermPatch
from app.terms import create_term, open_term, update_term


@unittest.skipUnless(os.getenv("RUN_DB_INTEGRATION") == "1", "需显式指定隔离测试库")
class CloseFlowTest(unittest.TestCase):
    def test_close_order_and_atomicity(self):
        suffix = uuid4().hex[:7]
        term_code = f"T{suffix}"
        unique_year = 3000 + (int(suffix, 16) % 6000)
        custom_course = f"ZG{suffix}"
        courses = ["CS101", "CS302", "MA101", "AR101", "AR102", "CS201", custom_course]
        offerings = {course: f"{term_code}-{course}" for course in courses}
        unselected_offering = f"{term_code}-CS101-02"
        now = datetime.now().replace(microsecond=0)
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO user_account (username,password_hash,role) "
                "VALUES (%s,'test-only','REGISTRAR')",
                (f"closing_{suffix}",),
            )
            registrar_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO course_catalog_demo.course (course_id,title,department_id,credits) "
                "VALUES (%s,'补位测试课','ART',2)",
                (custom_course,),
            )
        created = create_term(registrar_id, TermCreate(
            term_code=term_code, year=unique_year, semester="FALL",
            registration_opens_at=now - timedelta(days=10),
            registration_closes_at=now + timedelta(days=1),
            tuition_per_credit=Decimal("500.00"),
        ))
        self.assertEqual(created["status"], "DRAFT")
        with transaction() as connection, connection.cursor() as cursor:
            for index, course in enumerate(courses):
                offering_id = offerings[course]
                cursor.execute(
                    "INSERT INTO course_catalog_demo.course_offering "
                    "(offering_id,course_id,term_code,section_code,capacity) "
                    "VALUES (%s,%s,%s,'01',10)",
                    (offering_id, course, term_code),
                )
                cursor.execute(
                    "INSERT INTO course_catalog_demo.offering_meeting "
                    "(offering_id,weekday,start_period,end_period) VALUES (%s,%s,5,6)",
                    (offering_id, index + 1),
                )
                cursor.execute(
                    "INSERT INTO offering_registration_state (offering_id,term_code,capacity) "
                    "VALUES (%s,%s,10)",
                    (offering_id, term_code),
                )
            # 未被选中的目录班没有业务状态行；正式关闭应补建并取消它。
            cursor.execute(
                "INSERT INTO course_catalog_demo.course_offering "
                "(offering_id,course_id,term_code,section_code,capacity) "
                "VALUES (%s,'CS101',%s,'02',10)",
                (unselected_offering, term_code),
            )
            for course, professor_id in (
                ("CS101", "P001"), ("CS302", "P001"), ("MA101", "P002"),
                ("AR102", "P003"), (custom_course, "P003"),
            ):
                cursor.execute(
                    "INSERT INTO teaching_assignment (offering_id,professor_id) VALUES (%s,%s)",
                    (offerings[course], professor_id),
                )
        self.assertEqual(open_term(registrar_id, term_code)["status"], "OPEN")
        update_term(registrar_id, term_code, TermPatch(tuition_per_credit=Decimal("500.00")))

        with transaction() as connection, connection.cursor() as cursor:
            for index in range(4):
                student_id = f"CL{suffix}{index}"
                cursor.execute(
                    "INSERT INTO student_profile (student_id,full_name,date_of_birth) "
                    "VALUES (%s,'截止测试学生','2005-01-01')",
                    (student_id,),
                )
                cursor.execute(
                    "INSERT INTO student_schedule (student_id,term_code,status) "
                    "VALUES (%s,%s,'SUBMITTED')",
                    (student_id, term_code),
                )
                schedule_id = cursor.lastrowid
                primary = ["CS101", "CS302", "MA101", "AR101" if index < 3 else custom_course]
                for priority, course in enumerate(primary, 1):
                    cursor.execute(
                        "INSERT INTO schedule_choice "
                        "(schedule_id,offering_id,term_code,choice_type,priority,status) "
                        "VALUES (%s,%s,%s,'PRIMARY',%s,'ENROLLED')",
                        (schedule_id, offerings[course], term_code, priority),
                    )
                    choice_id = cursor.lastrowid
                    cursor.execute(
                        "INSERT INTO enrollment (schedule_id,choice_id,offering_id,status) "
                        "VALUES (%s,%s,%s,'ENROLLED')",
                        (schedule_id, choice_id, offerings[course]),
                    )
                for priority, course in enumerate(("AR102", "CS201"), 1):
                    cursor.execute(
                        "INSERT INTO schedule_choice "
                        "(schedule_id,offering_id,term_code,choice_type,priority,status) "
                        "VALUES (%s,%s,%s,'ALTERNATE',%s,'SELECTED')",
                        (schedule_id, offerings[course], term_code, priority),
                    )
            for course, count in (("CS101", 4), ("CS302", 4), ("MA101", 4),
                                  ("AR101", 3), (custom_course, 1)):
                cursor.execute(
                    "UPDATE offering_registration_state SET enrolled_count=%s WHERE offering_id=%s",
                    (count, offerings[course]),
                )

        before = preview_close(term_code)
        self.assertFalse(before["can_close"])
        self.assertEqual(before["submitted_schedules"], 4)
        reasons = {r["offering_id"]: r["reason"] for r in before["cancelled_offerings"]}
        self.assertEqual(reasons[offerings["AR101"]], "NO_PROFESSOR")
        self.assertEqual(reasons[offerings[custom_course]], "TOO_FEW_STUDENTS")
        self.assertEqual(next(r for r in before["committed_offerings"]
                              if r["offering_id"] == offerings["AR102"])["students"], 4)
        self.assertEqual(len(before["alternate_placements"]), 4)
        with self.assertRaises(HTTPException) as failure:
            close_registration(registrar_id, term_code)
        self.assertEqual(failure.exception.status_code, 409)
        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT status FROM academic_term WHERE term_code=%s", (term_code,))
            self.assertEqual(cursor.fetchone()["status"], "OPEN")
            cursor.execute(
                "SELECT COUNT(*) AS n FROM billing_outbox b JOIN student_schedule s ON s.schedule_id=b.schedule_id "
                "WHERE s.term_code=%s",
                (term_code,),
            )
            self.assertEqual(cursor.fetchone()["n"], 0)
            cursor.execute(
                "SELECT enrolled_count FROM offering_registration_state WHERE offering_id=%s",
                (offerings["AR102"],),
            )
            self.assertEqual(cursor.fetchone()["enrolled_count"], 0)

        # 只在隔离测试库中模拟截止时间已过，不改用户的真实演示学期。
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE academic_term SET registration_closes_at=%s WHERE term_code=%s",
                (now - timedelta(seconds=1), term_code),
            )
        result = close_registration(registrar_id, term_code)
        self.assertFalse(result["preview_only"])
        self.assertEqual(result["billing_transactions"], 4)
        with self.assertRaises(HTTPException):
            close_registration(registrar_id, term_code)
        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT status FROM academic_term WHERE term_code=%s", (term_code,))
            self.assertEqual(cursor.fetchone()["status"], "CLOSED")
            cursor.execute(
                "SELECT offering_id,status,enrolled_count,cancellation_reason "
                "FROM offering_registration_state WHERE term_code=%s",
                (term_code,),
            )
            states = {r["offering_id"]: r for r in cursor.fetchall()}
            self.assertEqual(states[offerings["AR102"]]["status"], "COMMITTED")
            self.assertEqual(states[offerings["AR102"]]["enrolled_count"], 4)
            self.assertEqual(states[unselected_offering]["status"], "CANCELLED")
            self.assertEqual(states[offerings["AR101"]]["cancellation_reason"], "NO_PROFESSOR")
            self.assertEqual(states[offerings[custom_course]]["cancellation_reason"], "TOO_FEW_STUDENTS")
            cursor.execute(
                "SELECT status,COUNT(*) AS n FROM student_schedule WHERE term_code=%s GROUP BY status",
                (term_code,),
            )
            self.assertEqual(cursor.fetchall(), [{"status": "FINALIZED", "n": 4}])
            cursor.execute(
                "SELECT b.status,b.amount,b.final_schedule FROM billing_outbox b "
                "JOIN student_schedule s ON s.schedule_id=b.schedule_id WHERE s.term_code=%s",
                (term_code,),
            )
            bills = cursor.fetchall()
            self.assertEqual(len(bills), 4)
            self.assertTrue(all(b["status"] == "PENDING" for b in bills))
            self.assertEqual(sorted(b["amount"] for b in bills),
                             [Decimal("6500.00")] * 4)
            self.assertEqual(sorted(len(json.loads(b["final_schedule"])["offerings"]) for b in bills),
                             [4, 4, 4, 4])
            cursor.execute(
                "SELECT e.status,COUNT(*) AS n FROM enrollment e "
                "JOIN student_schedule s ON s.schedule_id=e.schedule_id "
                "WHERE s.term_code=%s GROUP BY e.status",
                (term_code,),
            )
            self.assertEqual({r["status"]: r["n"] for r in cursor.fetchall()},
                             {"COMMITTED": 16, "CANCELLED": 4})
