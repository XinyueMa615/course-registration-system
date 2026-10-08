"""成绩权限和成绩单；数据库测试仅在隔离库显式开启。"""
from datetime import datetime, timedelta
import os
import unittest
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app.db import read_connection, transaction
from app.catalog import availability_for_offerings
from app.grades import grade_offerings, report_card, roster, set_grade
from app.professors import current_roster
from app.models import GradeInput


class GradeInputTest(unittest.TestCase):
    def test_only_supported_letter_grades(self):
        self.assertEqual(GradeInput(letter_grade="A").letter_grade, "A")
        with self.assertRaises(ValidationError):
            GradeInput(letter_grade="A+")


@unittest.skipUnless(os.getenv("RUN_DB_INTEGRATION") == "1", "需显式指定隔离测试库")
class GradeFlowTest(unittest.TestCase):
    def test_roster_grade_changes_and_student_scope(self):
        suffix = uuid4().hex[:7]
        term_code = f"G{suffix}"
        offering_id = f"{term_code}-CS101"
        professor_id = f"PG{suffix}"
        other_professor_id = f"PO{suffix}"
        student_id = f"SG{suffix}"
        other_student_id = f"SO{suffix}"
        # 同一个隔离测试实例可重复运行；新测试学期必须比旧测试学期更新。
        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT COALESCE(MAX(year),8999) AS latest FROM academic_term WHERE completed_at IS NOT NULL")
            unique_year = max(9000, cursor.fetchone()["latest"] + 1)
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO academic_term (term_code,year,semester,registration_opens_at,registration_closes_at,status) "
                "VALUES (%s,%s,'FALL',%s,%s,'OPEN')",
                (term_code, unique_year,
                 datetime.now() - timedelta(days=2), datetime.now() - timedelta(days=1)),
            )
            cursor.execute(
                "INSERT INTO course_catalog_demo.course_offering "
                "(offering_id,course_id,term_code,section_code,capacity) VALUES (%s,'CS101',%s,'01',10)",
                (offering_id, term_code),
            )
            cursor.execute(
                "INSERT INTO offering_registration_state (offering_id,term_code,capacity,status,enrolled_count) "
                "VALUES (%s,%s,10,'OPEN',1)", (offering_id, term_code),
            )
            teacher_users = []
            for pid in (professor_id, other_professor_id):
                cursor.execute(
                    "INSERT INTO user_account (username,password_hash,role) VALUES (%s,'test-only','PROFESSOR')",
                    (f"grade_{pid}",),
                )
                teacher_users.append(cursor.lastrowid)
                cursor.execute(
                    "INSERT INTO professor_profile (professor_id,user_id,full_name,date_of_birth,department_id) "
                    "VALUES (%s,%s,'测试教师','1980-01-01','CS')",
                    (pid, teacher_users[-1]),
                )
            cursor.execute(
                "INSERT INTO teaching_assignment (offering_id,professor_id) VALUES (%s,%s)",
                (offering_id, professor_id),
            )
            student_users = []
            for sid in (student_id, other_student_id):
                cursor.execute(
                    "INSERT INTO user_account (username,password_hash,role) VALUES (%s,'test-only','STUDENT')",
                    (f"grade_{sid}",),
                )
                student_users.append(cursor.lastrowid)
                cursor.execute(
                    "INSERT INTO student_profile (student_id,user_id,full_name,date_of_birth) "
                    "VALUES (%s,%s,'测试学生','2005-01-01')",
                    (sid, student_users[-1]),
                )
            cursor.execute(
                "INSERT INTO student_schedule (student_id,term_code,status) VALUES (%s,%s,'SUBMITTED')",
                (student_id, term_code),
            )
            schedule_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO schedule_choice (schedule_id,offering_id,term_code,choice_type,priority,status) "
                "VALUES (%s,%s,%s,'PRIMARY',1,'ENROLLED')",
                (schedule_id, offering_id, term_code),
            )
            choice_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO enrollment (schedule_id,choice_id,offering_id,status) "
                "VALUES (%s,%s,%s,'ENROLLED')", (schedule_id, choice_id, offering_id),
            )
            enrollment_id = cursor.lastrowid

        self.assertEqual([s["student_id"] for s in current_roster(teacher_users[0], term_code, offering_id)["students"]], [student_id])
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE offering_registration_state SET enrolled_count=10 WHERE offering_id=%s", (offering_id,))
        self.assertTrue(availability_for_offerings(term_code, [offering_id])[0]["is_full"])
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE offering_registration_state SET enrolled_count=1 WHERE offering_id=%s", (offering_id,))
        with self.assertRaises(HTTPException) as current_not_owner:
            current_roster(teacher_users[1], term_code, offering_id)
        self.assertEqual(current_not_owner.exception.status_code, 404)
        with self.assertRaises(HTTPException) as not_closed:
            roster(teacher_users[0], term_code, offering_id)
        self.assertEqual(not_closed.exception.status_code, 409)
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE student_schedule SET status='FINALIZED' WHERE schedule_id=%s", (schedule_id,))
            cursor.execute("UPDATE enrollment SET status='COMMITTED' WHERE enrollment_id=%s", (enrollment_id,))
            cursor.execute("UPDATE offering_registration_state SET status='COMMITTED' WHERE offering_id=%s", (offering_id,))
            cursor.execute("UPDATE academic_term SET status='CLOSED' WHERE term_code=%s", (term_code,))
        with self.assertRaises(HTTPException) as current_closed:
            current_roster(teacher_users[0], term_code, offering_id)
        self.assertEqual(current_closed.exception.status_code, 409)
        self.assertNotEqual(grade_offerings(teacher_users[0])["term_code"], term_code)
        with self.assertRaises(HTTPException) as teaching_not_done:
            roster(teacher_users[0], term_code, offering_id)
        self.assertEqual(teaching_not_done.exception.status_code, 409)
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE academic_term SET completed_at=NOW() WHERE term_code=%s", (term_code,))
        with self.assertRaises(HTTPException) as not_owner:
            roster(teacher_users[1], term_code, offering_id)
        self.assertEqual(not_owner.exception.status_code, 404)
        self.assertEqual([s["student_id"] for s in roster(teacher_users[0], term_code, offering_id)["students"]], [student_id])
        self.assertEqual(grade_offerings(teacher_users[0])["term_code"], term_code)
        with self.assertRaises(HTTPException):
            set_grade(teacher_users[1], term_code, offering_id, enrollment_id, "A")
        self.assertTrue(set_grade(teacher_users[0], term_code, offering_id, enrollment_id, "B")["changed"])
        self.assertFalse(set_grade(teacher_users[0], term_code, offering_id, enrollment_id, "B")["changed"])
        self.assertTrue(set_grade(teacher_users[0], term_code, offering_id, enrollment_id, "A")["changed"])
        self.assertEqual(report_card(student_users[0])["term_code"], term_code)
        self.assertEqual([c["letter_grade"] for c in report_card(student_users[0])["courses"]], ["A"])
        self.assertEqual(report_card(student_users[1])["courses"], [])
        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT old_grade,new_grade FROM grade_change_log WHERE enrollment_id=%s ORDER BY grade_change_id",
                (enrollment_id,),
            )
            self.assertEqual([(r["old_grade"], r["new_grade"]) for r in cursor.fetchall()], [(None, "B"), ("B", "A")])
