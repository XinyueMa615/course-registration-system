"""运行：python -m unittest discover -s tests -v。

设置 RUN_DB_INTEGRATION=1 时还会对隔离测试库执行完整选课流程。
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from app.models import ChoiceInput
from app.catalog import availability_for_offerings
from app.models import ProfessorCreate, ProfessorPatch, StudentCreate, StudentPatch
from app.professors import claim_offering, release_offering, teacher_offerings
from app.registrar import (
    _create_login, add_qualification, create_professor, create_student, delete_professor, delete_student,
    professor, remove_qualification, student, update_professor, update_student,
)
from app.ssn import encrypt_ssn
from app.schedules import _validate_positions, delete_schedule, get_schedule, save_draft, submit_schedule
from app.security import hash_password, require_role, verify_password


class PureRulesTest(unittest.TestCase):
    def test_ssn_is_validated_and_encrypted(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        with patch("app.ssn.settings", SimpleNamespace(app_secret="test-secret-that-is-long-enough-for-demo")):
            ciphertext = encrypt_ssn("000-12-3456")
            self.assertIsInstance(ciphertext, bytes)
            self.assertNotIn(b"000123456", ciphertext)
            with self.assertRaises(HTTPException):
                encrypt_ssn("not-an-ssn")

    def test_password_round_trip(self):
        digest = hash_password("testing-password-123")
        self.assertTrue(verify_password("testing-password-123", digest))
        self.assertFalse(verify_password("wrong-password", digest))

    def test_temporary_password_blocks_role_endpoints(self):
        student_access = require_role("STUDENT")
        with self.assertRaises(HTTPException) as blocked:
            student_access({"role": "STUDENT", "must_change_password": True})
        self.assertEqual(blocked.exception.status_code, 403)
        self.assertEqual(student_access({"role": "STUDENT", "must_change_password": False})["role"], "STUDENT")

    def test_new_accounts_use_configured_shared_initial_password(self):
        class Cursor:
            lastrowid = 42

            def execute(self, query, params):
                self.query, self.params = query, params

        cursor = Cursor()
        with patch("app.registrar.settings", SimpleNamespace(initial_account_password="Testing@2026")):
            account_id, username, password = _create_login(cursor, "SABC", "STUDENT")
        self.assertEqual((account_id, username, password), (42, "sabc", "Testing@2026"))
        self.assertTrue(verify_password(password, cursor.params[1]))
        self.assertIn("must_change_password", cursor.query)

    def test_submit_requires_exact_positions(self):
        with self.assertRaises(HTTPException):
            _validate_positions([ChoiceInput(offering_id="X", choice_type="PRIMARY", priority=1)], complete=True)

    def test_duplicate_offering_rejected(self):
        choices = [
            ChoiceInput(offering_id="X", choice_type="PRIMARY", priority=1),
            ChoiceInput(offering_id="X", choice_type="ALTERNATE", priority=1),
        ]
        with self.assertRaises(HTTPException):
            _validate_positions(choices, complete=False)

    def test_availability_query_limit(self):
        with self.assertRaises(HTTPException):
            availability_for_offerings("2026FA", [str(n) for n in range(7)])


@unittest.skipUnless(os.getenv("RUN_DB_INTEGRATION") == "1", "需显式指定隔离测试库")
class DatabaseFlowTest(unittest.TestCase):
    def test_registrar_flow(self):
        from datetime import date
        from app.db import transaction

        suffix = uuid4().hex[:8]
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO user_account (username,password_hash,role) VALUES (%s,%s,'REGISTRAR')",
                (f"registrar_{suffix}", hash_password("testing-password-123")),
            )
            user_id = cursor.lastrowid

        created = create_student(user_id, StudentCreate(
            full_name="  测试学生  ", date_of_birth=date(2005, 1, 1), ssn="000-12-3456",
        ))
        student_id = created["student_id"]
        self.assertTrue(student_id.startswith("S"))
        self.assertEqual(created["full_name"], "测试学生")
        self.assertTrue(created["has_ssn"])
        self.assertTrue(created["has_account"])
        self.assertEqual(created["username"], student_id.lower())
        self.assertGreaterEqual(len(created["temporary_password"]), 10)
        with self.assertRaises(HTTPException):
            update_student(user_id, student_id, StudentPatch(status="GRADUATED"))
        updated = update_student(user_id, student_id, StudentPatch(
            status="GRADUATED", graduation_date=date(2026, 6, 1), ssn=None,
        ))
        self.assertEqual(updated["status"], "GRADUATED")
        self.assertFalse(updated["has_ssn"])
        self.assertEqual(student(student_id)["graduation_date"], date(2026, 6, 1))
        self.assertTrue(delete_student(user_id, student_id)["deleted"])
        with self.assertRaises(HTTPException):
            student(student_id)

        with self.assertRaises(HTTPException):
            create_professor(user_id, ProfessorCreate(
                full_name="测试教师", date_of_birth=date(1980, 1, 1),
                department_id="NOT_A_DEPARTMENT",
            ))
        created_professor = create_professor(user_id, ProfessorCreate(
            full_name="测试教师", date_of_birth=date(1980, 1, 1),
            department_id="CS",
        ))
        professor_id = created_professor["professor_id"]
        self.assertTrue(professor_id.startswith("P"))
        self.assertEqual(created_professor["department_id"], "CS")
        self.assertTrue(created_professor["has_account"])
        self.assertEqual(created_professor["username"], professor_id.lower())
        self.assertIn("CS101", add_qualification(user_id, professor_id, "CS101")["qualifications"])
        self.assertNotIn("CS101", remove_qualification(user_id, professor_id, "CS101")["qualifications"])
        self.assertEqual(update_professor(user_id, professor_id, ProfessorPatch(status="INACTIVE"))["status"], "INACTIVE")
        self.assertEqual(professor(professor_id)["status"], "INACTIVE")
        self.assertTrue(delete_professor(user_id, professor_id)["deleted"])

    def test_teacher_flow(self):
        from app.db import transaction

        suffix = uuid4().hex[:8]
        professor_ids = [f"PT{suffix}", f"PU{suffix}"]
        user_ids = []
        offering_ids = [f"2026FA-CS101-{suffix}A", f"2026FA-CS101-{suffix}B"]
        with transaction() as connection, connection.cursor() as cursor:
            for index, professor_id in enumerate(professor_ids):
                cursor.execute(
                    "INSERT INTO user_account (username,password_hash,role) VALUES (%s,%s,'PROFESSOR')",
                    (f"teacher_{suffix}_{index}", hash_password("testing-password-123")),
                )
                user_id = cursor.lastrowid
                user_ids.append(user_id)
                cursor.execute(
                    "INSERT INTO professor_profile "
                    "(professor_id,user_id,full_name,date_of_birth,department_id) "
                    "VALUES (%s,%s,'测试专用教师','1980-01-01','CS')",
                    (professor_id, user_id),
                )
            cursor.execute(
                "INSERT INTO professor_qualification (professor_id,course_id) VALUES (%s,'CS101')",
                (professor_ids[0],),
            )
            for index, offering_id in enumerate(offering_ids):
                cursor.execute(
                    "INSERT INTO course_catalog_demo.course_offering "
                    "(offering_id,course_id,term_code,section_code,capacity) VALUES (%s,'CS101','2026FA',%s,10)",
                    (offering_id, f"{suffix}{index}"),
                )
                cursor.execute(
                    "INSERT INTO course_catalog_demo.offering_meeting "
                    "(offering_id,weekday,start_period,end_period) VALUES (%s,5,3,4)",
                    (offering_id,),
                )
                cursor.execute(
                    "INSERT INTO offering_registration_state (offering_id,term_code,capacity) "
                    "VALUES (%s,'2026FA',10)",
                    (offering_id,),
                )
            cursor.execute(
                "INSERT INTO user_account (username,password_hash,role) VALUES (%s,%s,'REGISTRAR')",
                (f"office_{suffix}", hash_password("testing-password-123")),
            )
            registrar_id = cursor.lastrowid
        self.assertIn(offering_ids[0], {o["offering_id"] for o in teacher_offerings(user_ids[0], "2026FA")["offerings"]})
        with self.assertRaises(HTTPException) as failure:
            claim_offering(user_ids[1], "2026FA", offering_ids[0])
        self.assertEqual(failure.exception.status_code, 403)
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO professor_qualification (professor_id,course_id) VALUES (%s,'CS101')",
                (professor_ids[1],),
            )
        self.assertTrue(next(o for o in claim_offering(user_ids[0], "2026FA", offering_ids[0])["offerings"] if o["offering_id"] == offering_ids[0])["is_mine"])
        with self.assertRaises(HTTPException) as failure:
            update_professor(registrar_id, professor_ids[0], ProfessorPatch(status="INACTIVE"))
        self.assertEqual(failure.exception.status_code, 409)
        with self.assertRaises(HTTPException) as failure:
            remove_qualification(registrar_id, professor_ids[0], "CS101")
        self.assertEqual(failure.exception.status_code, 409)
        with self.assertRaises(HTTPException) as failure:
            claim_offering(user_ids[1], "2026FA", offering_ids[0])
        self.assertEqual(failure.exception.status_code, 409)
        with self.assertRaises(HTTPException) as failure:
            claim_offering(user_ids[0], "2026FA", offering_ids[1])
        self.assertIn("时间冲突", str(failure.exception.detail))
        with self.assertRaises(HTTPException):
            release_offering(user_ids[1], "2026FA", offering_ids[0])
        release_offering(user_ids[0], "2026FA", offering_ids[0])
        self.assertTrue(next(o for o in claim_offering(user_ids[1], "2026FA", offering_ids[0])["offerings"] if o["offering_id"] == offering_ids[0])["is_mine"])

    def test_student_flow(self):
        from app.db import transaction, read_connection

        suffix = uuid4().hex[:8]
        student_id = f"T{suffix}"
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO user_account (username,password_hash,role) VALUES (%s,%s,'STUDENT')",
                (f"test_{suffix}", hash_password("testing-password-123")),
            )
            user_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO student_profile (student_id,user_id,full_name,date_of_birth) "
                "VALUES (%s,%s,'测试专用学生','2005-01-01')",
                (student_id, user_id),
            )

        term = "2026FA"
        self.assertEqual(get_schedule(user_id, term)["status"], "EMPTY")
        partial = [ChoiceInput(offering_id="2026FA-CS101-01", choice_type="PRIMARY", priority=1)]
        self.assertEqual(save_draft(user_id, term, partial)["status"], "DRAFT")
        with self.assertRaises(HTTPException):
            submit_schedule(user_id, term)

        choices = [
            ChoiceInput(offering_id="2026FA-CS101-01", choice_type="PRIMARY", priority=1),
            ChoiceInput(offering_id="2026FA-CS302-01", choice_type="PRIMARY", priority=2),
            ChoiceInput(offering_id="2026FA-MA101-01", choice_type="PRIMARY", priority=3),
            ChoiceInput(offering_id="2026FA-AR101-01", choice_type="PRIMARY", priority=4),
            ChoiceInput(offering_id="2026FA-CS201-01", choice_type="ALTERNATE", priority=1),
            ChoiceInput(offering_id="2026FA-AR102-01", choice_type="ALTERNATE", priority=2),
        ]
        self.assertEqual(save_draft(user_id, term, choices)["status"], "DRAFT")
        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT enrolled_count FROM offering_registration_state WHERE offering_id='2026FA-CS101-01'")
            before = cursor.fetchone()["enrolled_count"]
        self.assertEqual(submit_schedule(user_id, term)["status"], "SUBMITTED")
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO user_account (username,password_hash,role) VALUES (%s,%s,'REGISTRAR')",
                (f"office_{suffix}", hash_password("testing-password-123")),
            )
            registrar_id = cursor.lastrowid
        with self.assertRaises(HTTPException) as failure:
            update_student(registrar_id, student_id, StudentPatch(status="INACTIVE"))
        self.assertEqual(failure.exception.status_code, 409)
        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT enrolled_count FROM offering_registration_state WHERE offering_id='2026FA-CS101-01'")
            self.assertEqual(cursor.fetchone()["enrolled_count"], before + 1)
        self.assertEqual(save_draft(user_id, term, choices)["status"], "DRAFT")
        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT enrolled_count FROM offering_registration_state WHERE offering_id='2026FA-CS101-01'")
            self.assertEqual(cursor.fetchone()["enrolled_count"], before)

        choices[0] = ChoiceInput(offering_id="2026FA-CS201-01", choice_type="PRIMARY", priority=1)
        choices[4] = ChoiceInput(offering_id="2026FA-CS101-01", choice_type="ALTERNATE", priority=1)
        save_draft(user_id, term, choices)
        with self.assertRaises(HTTPException) as failure:
            submit_schedule(user_id, term)
        self.assertIn("先修课", str(failure.exception.detail))

        self.assertEqual(save_draft(user_id, term, choices[:1])["status"], "DRAFT")
        self.assertEqual(delete_schedule(user_id, term)["status"], "EMPTY")
        self.assertEqual(get_schedule(user_id, term)["choices"], [])
        with self.assertRaises(HTTPException) as failure:
            delete_schedule(user_id, term)
        self.assertEqual(failure.exception.status_code, 404)

        self.assertEqual(save_draft(user_id, term, [
            ChoiceInput(offering_id="2026FA-CS101-01", choice_type="PRIMARY", priority=1),
            ChoiceInput(offering_id="2026FA-CS302-01", choice_type="PRIMARY", priority=2),
            ChoiceInput(offering_id="2026FA-MA101-01", choice_type="PRIMARY", priority=3),
            ChoiceInput(offering_id="2026FA-AR101-01", choice_type="PRIMARY", priority=4),
            ChoiceInput(offering_id="2026FA-CS201-01", choice_type="ALTERNATE", priority=1),
            ChoiceInput(offering_id="2026FA-AR102-01", choice_type="ALTERNATE", priority=2),
        ])["status"], "DRAFT")
        self.assertEqual(submit_schedule(user_id, term)["status"], "SUBMITTED")
        self.assertEqual(delete_schedule(user_id, term)["status"], "EMPTY")
        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT enrolled_count FROM offering_registration_state WHERE offering_id='2026FA-CS101-01'")
            self.assertEqual(cursor.fetchone()["enrolled_count"], before)
            cursor.execute("SELECT COUNT(*) AS count FROM enrollment e JOIN student_schedule s "
                           "ON s.schedule_id=e.schedule_id WHERE s.student_id=%s AND s.term_code=%s",
                           (student_id, term))
            self.assertEqual(cursor.fetchone()["count"], 0)
        self.assertEqual(availability_for_offerings(term, ["2026FA-CS101-01"])[0]["is_full"], False)
