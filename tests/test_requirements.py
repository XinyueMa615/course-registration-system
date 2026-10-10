"""原题功能补充验收：批量档案、会话注销、角色权限和选课原子性。

涉及数据库的用例只能在随机命名的隔离测试库中启用。
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
import os
import unittest
from uuid import uuid4

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pymysql.err import OperationalError

from app.config import settings
from app.db import read_connection, transaction
from app.main import database_unavailable, login, logout
from app.models import ChoiceInput, LoginRequest, ProfessorCreate, ProfessorPatch, StudentCreate, StudentPatch
from app.registrar import (
    add_qualification,
    create_professor,
    create_student,
    delete_professor,
    delete_student,
    professors,
    students,
    update_professor,
    update_student,
)
from app.schedules import get_schedule, save_draft, submit_schedule
from app.security import current_user, hash_password, require_role


class RequirementErrorHandlingTest(unittest.TestCase):
    def test_database_errors_are_safe_and_understandable(self):
        response = asyncio.run(database_unavailable(None, OperationalError(2003, "secret host detail")))
        self.assertEqual(response.status_code, 503)
        payload = json.loads(response.body)
        self.assertIn("暂时不可用", payload["detail"])
        self.assertNotIn("secret host detail", response.body.decode("utf-8"))

    def test_role_matrix_rejects_vertical_privilege_escalation(self):
        student_only = require_role("STUDENT")
        professor_only = require_role("PROFESSOR")
        registrar_only = require_role("REGISTRAR")
        student = {"role": "STUDENT", "must_change_password": False}
        professor = {"role": "PROFESSOR", "must_change_password": False}
        registrar = {"role": "REGISTRAR", "must_change_password": False}
        self.assertEqual(student_only(student)["role"], "STUDENT")
        for dependency, wrong_user in (
            (student_only, professor),
            (professor_only, student),
            (registrar_only, student),
            (registrar_only, professor),
            (professor_only, registrar),
        ):
            with self.assertRaises(HTTPException) as denied:
                dependency(wrong_user)
            self.assertEqual(denied.exception.status_code, 403)


@unittest.skipUnless(os.getenv("RUN_DB_INTEGRATION") == "1", "需显式指定隔离测试库")
class RequirementDatabaseTest(unittest.TestCase):
    def _registrar(self, suffix: str) -> int:
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO user_account (username,password_hash,role) VALUES (%s,%s,'REGISTRAR')",
                (f"bulk_registrar_{suffix}", hash_password("testing-password-123")),
            )
            return cursor.lastrowid

    def test_bulk_student_and_professor_crud(self):
        suffix = uuid4().hex[:7]
        registrar_id = self._registrar(suffix)

        def add_student(index: int):
            return create_student(registrar_id, StudentCreate(
                full_name=f"批量学生{index:02d}",
                date_of_birth=date(2004 + index % 3, 1 + index % 12, 1 + index % 20),
                ssn=f"000-12-{3000 + index:04d}",
            ))

        with ThreadPoolExecutor(max_workers=6) as executor:
            created_students = list(executor.map(add_student, range(12)))
        student_ids = [row["student_id"] for row in created_students]
        self.assertEqual(len(set(student_ids)), 12)
        self.assertTrue(all(row["username"] == row["student_id"].lower() for row in created_students))
        self.assertEqual(len(students("批量学生")), 12)

        graduated = update_student(
            registrar_id,
            student_ids[0],
            StudentPatch(status="GRADUATED", graduation_date=date(2026, 7, 1)),
        )
        self.assertEqual(graduated["status"], "GRADUATED")
        self.assertEqual(graduated["graduation_date"], date(2026, 7, 1))
        for student_id in student_ids:
            self.assertTrue(delete_student(registrar_id, student_id)["deleted"])
        self.assertEqual(len(students("批量学生")), 0)

        def add_professor(index: int):
            return create_professor(registrar_id, ProfessorCreate(
                full_name=f"批量教师{index:02d}",
                date_of_birth=date(1975 + index, 2, 1),
                department_id="CS",
                ssn=f"000-34-{5000 + index:04d}",
            ))

        with ThreadPoolExecutor(max_workers=5) as executor:
            created_professors = list(executor.map(add_professor, range(8)))
        professor_ids = [row["professor_id"] for row in created_professors]
        self.assertEqual(len(set(professor_ids)), 8)
        self.assertEqual(len(professors("批量教师")), 8)
        for professor_id in professor_ids:
            qualified = add_qualification(registrar_id, professor_id, "CS101")
            self.assertIn("CS101", qualified["qualifications"])
        changed = update_professor(
            registrar_id, professor_ids[0], ProfessorPatch(full_name="批量教师已修改")
        )
        self.assertEqual(changed["full_name"], "批量教师已修改")
        for professor_id in professor_ids:
            self.assertTrue(delete_professor(registrar_id, professor_id)["deleted"])
        self.assertEqual(len(professors("批量教师")), 0)

    def test_logout_invalidates_the_old_token(self):
        suffix = uuid4().hex[:8]
        username = f"logout_{suffix}"
        password = "testing-password-123"
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO user_account (username,password_hash,role) VALUES (%s,%s,'STUDENT')",
                (username, hash_password(password)),
            )
            user_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO student_profile (student_id,user_id,full_name,date_of_birth) "
                "VALUES (%s,%s,'注销测试学生','2005-01-01')",
                (f"LO{suffix}", user_id),
            )

        with self.assertRaises(HTTPException) as wrong_password:
            login(LoginRequest(username=username, password="incorrect-password"))
        self.assertEqual(wrong_password.exception.status_code, 401)

        signed_in = login(LoginRequest(username=username, password=password))
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=signed_in["access_token"]
        )
        user = current_user(credentials)
        self.assertEqual(user["user_id"], user_id)
        self.assertTrue(logout(user)["logged_out"])
        with self.assertRaises(HTTPException) as expired:
            current_user(credentials)
        self.assertEqual(expired.exception.status_code, 401)
        self.assertEqual(login(LoginRequest(username=username, password=password))["role"], "STUDENT")

        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE user_account SET is_active=FALSE WHERE user_id=%s", (user_id,))
        with self.assertRaises(HTTPException) as inactive:
            login(LoginRequest(username=username, password=password))
        self.assertEqual(inactive.exception.status_code, 401)

    def test_schedule_conflict_rolls_back_without_partial_enrollment(self):
        suffix = uuid4().hex[:6]
        course_id = f"TC{suffix}"
        offering_id = f"2026FA-{course_id}-01"
        student_id = f"TS{suffix}"
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO user_account (username,password_hash,role) VALUES (%s,%s,'STUDENT')",
                (f"conflict_{suffix}", hash_password("testing-password-123")),
            )
            user_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO student_profile (student_id,user_id,full_name,date_of_birth) "
                "VALUES (%s,%s,'冲突测试学生','2005-01-01')",
                (student_id, user_id),
            )
            cursor.execute(
                f"INSERT INTO `{settings.catalog_db}`.course "
                "(course_id,title,department_id,credits) VALUES (%s,'冲突测试课程','CS',2)",
                (course_id,),
            )
            cursor.execute(
                f"INSERT INTO `{settings.catalog_db}`.course_offering "
                "(offering_id,course_id,term_code,section_code,capacity) "
                "VALUES (%s,%s,'2026FA','01',10)",
                (offering_id, course_id),
            )
            cursor.execute(
                f"INSERT INTO `{settings.catalog_db}`.offering_meeting "
                "(offering_id,weekday,start_period,end_period) VALUES (%s,1,1,2)",
                (offering_id,),
            )

        choices = [
            ChoiceInput(offering_id="2026FA-CS101-01", choice_type="PRIMARY", priority=1),
            ChoiceInput(offering_id=offering_id, choice_type="PRIMARY", priority=2),
            ChoiceInput(offering_id="2026FA-MA101-01", choice_type="PRIMARY", priority=3),
            ChoiceInput(offering_id="2026FA-AR101-01", choice_type="PRIMARY", priority=4),
            ChoiceInput(offering_id="2026FA-CS302-01", choice_type="ALTERNATE", priority=1),
            ChoiceInput(offering_id="2026FA-AR102-01", choice_type="ALTERNATE", priority=2),
        ]
        self.assertEqual(save_draft(user_id, "2026FA", choices)["status"], "DRAFT")
        with self.assertRaises(HTTPException) as conflict:
            submit_schedule(user_id, "2026FA")
        self.assertIn("时间冲突", str(conflict.exception.detail))
        self.assertEqual(get_schedule(user_id, "2026FA")["status"], "DRAFT")
        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS n FROM enrollment e "
                "JOIN student_schedule s ON s.schedule_id=e.schedule_id WHERE s.student_id=%s",
                (student_id,),
            )
            self.assertEqual(cursor.fetchone()["n"], 0)
