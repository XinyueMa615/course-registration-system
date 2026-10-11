"""Teacher-claim integration checks against the isolated sixth-version databases only.

Run: RUN_DB_INTEGRATION=1 .venv/bin/python3 -m unittest tests.test_teacher_claims -v
"""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier
from uuid import uuid4

from fastapi import HTTPException

from app.catalog import offerings_for_term
from app.config import settings
from app.db import read_connection, transaction
from app.professors import claim_offering, release_offering
from app.security import hash_password


@unittest.skipUnless(os.getenv("RUN_DB_INTEGRATION") == "1", "需显式启用隔离库测试")
class TeacherClaimIntegrationTest(unittest.TestCase):
    TERM = "2026FA"
    SAME_A = "2026FA-CS101-02"       # Monday, periods 3-4
    SAME_B = "2026FA-CS101-03"       # Tuesday, periods 5-6
    CONFLICT = "2026FA-AR103-01"     # Tuesday, periods 5-6
    OFFERINGS = (SAME_A, SAME_B, CONFLICT)

    @classmethod
    def setUpClass(cls):
        if settings.db_name != "course_registration_v6_test" or settings.catalog_db != "course_catalog_v6_test":
            raise RuntimeError("认领测试只允许连接第六版隔离测试库")
        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT status,registration_opens_at,registration_closes_at "
                "FROM academic_term WHERE term_code=%s", (cls.TERM,)
            )
            term = cursor.fetchone()
            if not term or term["status"] != "OPEN" or not (
                term["registration_opens_at"] <= datetime.now() <= term["registration_closes_at"]
            ):
                raise RuntimeError("测试学期不在开放期；不更改现有学期状态")
            cursor.execute(
                "SELECT offering_id FROM teaching_assignment WHERE offering_id IN (%s,%s,%s)", cls.OFFERINGS
            )
            if cursor.fetchall():
                raise RuntimeError("测试教学班已有教师；不覆盖现有认领")
            cursor.execute(
                "SELECT offering_id FROM offering_registration_state WHERE offering_id IN (%s,%s,%s)", cls.OFFERINGS
            )
            cls.preexisting_states = {row["offering_id"] for row in cursor.fetchall()}
        offerings = {row["offering_id"]: row for row in offerings_for_term(cls.TERM)}
        if not all(offering_id in offerings for offering_id in cls.OFFERINGS):
            raise RuntimeError("测试目录缺少预期的教学班")
        first, second, conflict = (offerings[id] for id in cls.OFFERINGS)
        if first["course_id"] != second["course_id"] or first["course_id"] == conflict["course_id"]:
            raise RuntimeError("测试课程关系不符合预期")
        if not any(
            a["weekday"] == b["weekday"]
            and a["start_period"] <= b["end_period"]
            and b["start_period"] <= a["end_period"]
            for a in second["meetings"] for b in conflict["meetings"]
        ):
            raise RuntimeError("测试课程实际上没有时间冲突")
        suffix = uuid4().hex[:10]
        cls.professor_ids = (f"TC{suffix}A", f"TC{suffix}B")
        cls.user_ids = []
        with transaction() as connection, connection.cursor() as cursor:
            for index, professor_id in enumerate(cls.professor_ids):
                cursor.execute(
                    "INSERT INTO user_account (username,password_hash,role) VALUES (%s,%s,'PROFESSOR')",
                    (f"claim_test_{suffix}_{index}", hash_password("test-only-password-long")),
                )
                cls.user_ids.append(cursor.lastrowid)
                cursor.execute(
                    "INSERT INTO professor_profile "
                    "(professor_id,user_id,full_name,date_of_birth,department_id) "
                    "VALUES (%s,%s,%s,'1980-01-01','CS')",
                    (professor_id, cls.user_ids[-1], f"认领测试教师{index + 1}"),
                )
                cursor.execute(
                    "INSERT INTO professor_qualification (professor_id,course_id) VALUES (%s,'CS101')",
                    (professor_id,),
                )
            cursor.execute(
                "INSERT INTO professor_qualification (professor_id,course_id) VALUES (%s,'AR103')",
                (cls.professor_ids[0],),
            )

    @classmethod
    def tearDownClass(cls):
        if not getattr(cls, "user_ids", None):
            return
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM teaching_assignment WHERE professor_id IN (%s,%s)", cls.professor_ids
            )
            cursor.execute("DELETE FROM audit_log WHERE user_id IN (%s,%s)", cls.user_ids)
            cursor.execute(
                "DELETE FROM professor_qualification WHERE professor_id IN (%s,%s)", cls.professor_ids
            )
            cursor.execute(
                "DELETE FROM professor_profile WHERE professor_id IN (%s,%s)", cls.professor_ids
            )
            cursor.execute("DELETE FROM user_account WHERE user_id IN (%s,%s)", cls.user_ids)
            for offering_id in cls.OFFERINGS:
                if offering_id not in cls.preexisting_states:
                    cursor.execute(
                        "DELETE FROM offering_registration_state WHERE offering_id=%s "
                        "AND enrolled_count=0 AND NOT EXISTS "
                        "(SELECT 1 FROM schedule_choice WHERE offering_id=%s)",
                        (offering_id, offering_id),
                    )

    def tearDown(self):
        # Each case starts with unclaimed sections; account cleanup is in tearDownClass.
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM teaching_assignment WHERE professor_id IN (%s,%s)", self.professor_ids
            )

    def assert_rejected(self, action, status, text):
        with self.assertRaises(HTTPException) as caught:
            action()
        self.assertEqual(caught.exception.status_code, status)
        self.assertIn(text, str(caught.exception.detail))

    def test_01_two_teachers_simultaneously_claim_same_section(self):
        for _ in range(10):
            barrier = Barrier(2)

            def attempt(user_id):
                barrier.wait(timeout=5)
                try:
                    claim_offering(user_id, self.TERM, self.SAME_A)
                    return ("claimed", None)
                except HTTPException as exc:
                    return (exc.status_code, str(exc.detail))

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(attempt, user_id) for user_id in self.user_ids]
                results = [future.result(timeout=20) for future in futures]
            self.assertEqual([item[0] for item in results].count("claimed"), 1)
            self.assertEqual([item[0] for item in results].count(409), 1)
            self.assertIn("已有教师认领", next(item[1] for item in results if item[0] == 409))
            with transaction() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT professor_id FROM teaching_assignment WHERE offering_id=%s", (self.SAME_A,))
                rows = cursor.fetchall()
                self.assertEqual(len(rows), 1)
                self.assertIn(rows[0]["professor_id"], self.professor_ids)
                cursor.execute(
                    "DELETE FROM teaching_assignment WHERE offering_id=%s AND professor_id=%s",
                    (self.SAME_A, rows[0]["professor_id"]),
                )

    def test_02_different_sections_of_same_course_are_allowed(self):
        barrier = Barrier(2)

        def attempt(user_id, offering_id):
            barrier.wait(timeout=5)
            return claim_offering(user_id, self.TERM, offering_id)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(attempt, self.user_ids[0], self.SAME_A),
                pool.submit(attempt, self.user_ids[1], self.SAME_B),
            ]
            for future in futures:
                future.result(timeout=20)
        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT offering_id,professor_id FROM teaching_assignment "
                "WHERE offering_id IN (%s,%s) ORDER BY offering_id", (self.SAME_A, self.SAME_B)
            )
            rows = cursor.fetchall()
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]["professor_id"], rows[1]["professor_id"])

    def test_03_same_teacher_conflicting_courses_are_rejected(self):
        claim_offering(self.user_ids[0], self.TERM, self.SAME_B)
        self.assert_rejected(
            lambda: claim_offering(self.user_ids[0], self.TERM, self.CONFLICT),
            409, f"与已认领的教学班 {self.SAME_B} 上课时间冲突",
        )
        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM teaching_assignment WHERE offering_id=%s", (self.CONFLICT,))
            self.assertIsNone(cursor.fetchone())

    def test_04_nonconflicting_sections_are_allowed(self):
        claim_offering(self.user_ids[0], self.TERM, self.SAME_A)
        claim_offering(self.user_ids[0], self.TERM, self.SAME_B)
        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM teaching_assignment WHERE professor_id=%s "
                "AND offering_id IN (%s,%s)", (self.professor_ids[0], self.SAME_A, self.SAME_B)
            )
            self.assertEqual(cursor.fetchone()["count"], 2)

    def test_05_qualification_duplicate_claim_and_nonowner_release(self):
        self.assert_rejected(
            lambda: claim_offering(self.user_ids[1], self.TERM, self.CONFLICT),
            403, "没有教授这门课程的资格",
        )
        claim_offering(self.user_ids[0], self.TERM, self.SAME_A)
        self.assert_rejected(
            lambda: claim_offering(self.user_ids[0], self.TERM, self.SAME_A),
            409, "你已经认领了该教学班",
        )
        self.assert_rejected(
            lambda: release_offering(self.user_ids[1], self.TERM, self.SAME_A),
            409, "该教学班不是由你认领的",
        )
        release_offering(self.user_ids[0], self.TERM, self.SAME_A)
        claim_offering(self.user_ids[1], self.TERM, self.SAME_A)

    def test_06_missing_term_and_offering(self):
        self.assert_rejected(
            lambda: claim_offering(self.user_ids[0], "NO-TERM", self.SAME_A),
            404, "学期不存在",
        )
        self.assert_rejected(
            lambda: claim_offering(self.user_ids[0], self.TERM, "NO-OFFERING"),
            400, "课表中有不存在或不属于当前学期的教学班",
        )

    def test_07_conflicting_course_times_are_allowed_for_different_teachers(self):
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO professor_qualification (professor_id,course_id) VALUES (%s,'AR103')",
                (self.professor_ids[1],),
            )
        claim_offering(self.user_ids[0], self.TERM, self.SAME_B)
        claim_offering(self.user_ids[1], self.TERM, self.CONFLICT)
        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT offering_id,professor_id FROM teaching_assignment "
                "WHERE offering_id IN (%s,%s)", (self.SAME_B, self.CONFLICT)
            )
            self.assertEqual(len(cursor.fetchall()), 2)
