"""PDF 第 9–12 页：在显式指定的隔离库中验证档案维护全流程。"""
from __future__ import annotations

import os
import unittest
from datetime import date
from uuid import uuid4

from fastapi import HTTPException

from app.config import settings
from app.db import read_connection
from app.models import ProfessorCreate, ProfessorPatch, StudentCreate, StudentPatch
from app.registrar import (
    create_professor, create_student, delete_professor, delete_student,
    professor, professors, student, students, update_professor, update_student,
)
from app.schedules import get_schedule, schedule_terms
from app.security import current_user, require_role


@unittest.skipUnless(os.getenv("RUN_DB_INTEGRATION") == "1", "需显式启用隔离库测试")
class RegistrarMaintenanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        expected = os.getenv("INTEGRATION_DB_NAME")
        if not expected or settings.db_name != expected or not expected.endswith("_autotest"):
            raise RuntimeError("档案维护集成测试只能连接显式指定的自动测试库")
        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT user_id FROM user_account WHERE username='registrar1' AND role='REGISTRAR'")
            row = cursor.fetchone()
        if not row:
            raise RuntimeError("隔离测试库缺少 registrar1 教务账号")
        cls.registrar_id = row["user_id"]

    def test_student_create_update_not_found_and_delete(self):
        marker = f"课设学生测试{uuid4().hex[:8]}"
        created = create_student(self.registrar_id, StudentCreate(
            full_name=marker, date_of_birth=date(2005, 1, 2),
            department_id="CS", admission_term_code="2026FA",
            ssn="000-12-3456", status="ACTIVE",
        ))
        student_id = created["student_id"]
        account_id = None
        try:
            self.assertTrue(student_id.startswith("S"))
            self.assertEqual(created["username"], student_id.lower())
            self.assertTrue(created["has_ssn"])
            self.assertEqual(created["department_id"], "CS")
            self.assertEqual(created["admission_term_code"], "2026FA")
            self.assertEqual([row["student_id"] for row in students(marker)], [student_id])
            with read_connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    "SELECT s.ssn_encrypted,u.user_id,u.role,u.must_change_password "
                    "FROM student_profile s JOIN user_account u ON u.user_id=s.user_id "
                    "WHERE s.student_id=%s", (student_id,),
                )
                row = cursor.fetchone()
            account_id = row["user_id"]
            self.assertEqual(row["role"], "STUDENT")
            self.assertTrue(row["must_change_password"])
            self.assertNotIn(b"000123456", row["ssn_encrypted"])
            self.assertIn("2026FA", [term["term_code"] for term in schedule_terms(account_id)])

            with self.assertRaises(HTTPException):
                update_student(self.registrar_id, student_id, StudentPatch(ssn=None))
            updated = update_student(self.registrar_id, student_id, StudentPatch(
                full_name=marker + "已修改", date_of_birth=date(2005, 2, 3),
                status="GRADUATED", graduation_date=date(2026, 6, 1),
            ))
            self.assertEqual(updated["full_name"], marker + "已修改")
            self.assertEqual(updated["date_of_birth"], date(2005, 2, 3))
            self.assertEqual(updated["status"], "GRADUATED")
            self.assertEqual(updated["graduation_date"], date(2026, 6, 1))
            self.assertTrue(updated["has_ssn"])
            self.assertEqual(student(student_id)["full_name"], marker + "已修改")

            missing_id = "S-NOT-FOUND-TEST"
            self.assertEqual(len(students(missing_id)), 0)
            for operation in (
                lambda: update_student(self.registrar_id, missing_id, StudentPatch(full_name="不存在")),
                lambda: delete_student(self.registrar_id, missing_id),
            ):
                with self.assertRaises(HTTPException) as error:
                    operation()
                self.assertEqual(error.exception.status_code, 404)
                self.assertEqual(error.exception.detail, "学生不存在")

            self.assertTrue(delete_student(self.registrar_id, student_id)["deleted"])
            self.assertEqual(len(students(student_id)), 0)
            with read_connection() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM user_account WHERE user_id=%s", (account_id,))
                self.assertIsNone(cursor.fetchone())
        finally:
            if any(row["full_name"].startswith(marker) for row in students(student_id)):
                delete_student(self.registrar_id, student_id)

    def test_professor_create_update_not_found_and_delete(self):
        marker = f"课设教师测试{uuid4().hex[:8]}"
        created = create_professor(self.registrar_id, ProfessorCreate(
            full_name=marker, date_of_birth=date(1980, 1, 2),
            ssn="000-23-4567", status="ACTIVE", department_id="CS",
        ))
        professor_id = created["professor_id"]
        account_id = None
        try:
            self.assertTrue(professor_id.startswith("P"))
            self.assertEqual(created["username"], professor_id.lower())
            self.assertTrue(created["has_ssn"])
            self.assertEqual([row["professor_id"] for row in professors(marker)], [professor_id])
            with read_connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    "SELECT p.ssn_encrypted,u.user_id,u.role,u.must_change_password "
                    "FROM professor_profile p JOIN user_account u ON u.user_id=p.user_id "
                    "WHERE p.professor_id=%s", (professor_id,),
                )
                row = cursor.fetchone()
            account_id = row["user_id"]
            self.assertEqual(row["role"], "PROFESSOR")
            self.assertTrue(row["must_change_password"])
            self.assertNotIn(b"000234567", row["ssn_encrypted"])

            with self.assertRaises(HTTPException):
                update_professor(self.registrar_id, professor_id, ProfessorPatch(ssn=None))
            updated = update_professor(self.registrar_id, professor_id, ProfessorPatch(
                full_name=marker + "已修改", date_of_birth=date(1981, 2, 3),
                status="INACTIVE", department_id="MATH",
            ))
            self.assertEqual(updated["full_name"], marker + "已修改")
            self.assertEqual(updated["date_of_birth"], date(1981, 2, 3))
            self.assertEqual(updated["status"], "INACTIVE")
            self.assertEqual(updated["department_id"], "MATH")
            self.assertTrue(updated["has_ssn"])
            self.assertEqual(professor(professor_id)["department_id"], "MATH")

            missing_id = "P-NOT-FOUND-TEST"
            self.assertEqual(len(professors(missing_id)), 0)
            for operation in (
                lambda: update_professor(self.registrar_id, missing_id, ProfessorPatch(full_name="不存在")),
                lambda: delete_professor(self.registrar_id, missing_id),
            ):
                with self.assertRaises(HTTPException) as error:
                    operation()
                self.assertEqual(error.exception.status_code, 404)
                self.assertEqual(error.exception.detail, "教师不存在")

            self.assertTrue(delete_professor(self.registrar_id, professor_id)["deleted"])
            self.assertEqual(len(professors(professor_id)), 0)
            with read_connection() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM user_account WHERE user_id=%s", (account_id,))
                self.assertIsNone(cursor.fetchone())
        finally:
            if any(row["full_name"].startswith(marker) for row in professors(professor_id)):
                delete_professor(self.registrar_id, professor_id)

    def test_student_cannot_select_before_admission(self):
        term_code = f"A{uuid4().hex[:7]}"
        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT year FROM academic_term WHERE semester='FALL' AND year>=2027")
            used_years = {row["year"] for row in cursor.fetchall()}
        year = next(year for year in range(2027, 9999) if year not in used_years)
        from app.db import transaction
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO academic_term "
                "(term_code,year,semester,registration_opens_at,registration_closes_at) "
                "VALUES (%s,%s,'FALL','2027-08-01','2027-10-01')",
                (term_code, year),
            )
        student_id = None
        try:
            created = create_student(self.registrar_id, StudentCreate(
                full_name="入学边界测试", date_of_birth=date(2005, 1, 1),
                department_id="CS", admission_term_code=term_code,
                ssn="000-12-3456",
            ))
            student_id = created["student_id"]
            with read_connection() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT user_id FROM student_profile WHERE student_id=%s", (student_id,))
                student_user_id = cursor.fetchone()["user_id"]
            with self.assertRaises(HTTPException) as error:
                get_schedule(student_user_id, "2026FA", require_existing=False)
            self.assertEqual(error.exception.status_code, 409)
            self.assertIn("早于你的入学学期", error.exception.detail)
            self.assertNotIn("2026FA", [term["term_code"] for term in schedule_terms(student_user_id)])
        finally:
            if student_id:
                delete_student(self.registrar_id, student_id)
            with transaction() as connection, connection.cursor() as cursor:
                cursor.execute("DELETE FROM academic_term WHERE term_code=%s", (term_code,))

    def test_registrar_role_checks_and_login_requirement(self):
        with self.assertRaises(HTTPException) as unauthenticated:
            current_user(None)
        self.assertEqual(unauthenticated.exception.status_code, 401)
        registrar_only = require_role("REGISTRAR")
        for role in ("STUDENT", "PROFESSOR"):
            with self.assertRaises(HTTPException) as forbidden:
                registrar_only({"role": role, "must_change_password": False})
            self.assertEqual(forbidden.exception.status_code, 403)
        self.assertEqual(
            registrar_only({"role": "REGISTRAR", "must_change_password": False})["role"],
            "REGISTRAR",
        )
