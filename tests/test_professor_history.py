"""教师教学班历史筛选的只读规则。"""
import unittest
from contextlib import nullcontext
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi import HTTPException

from app.professors import teacher_offerings, teacher_terms
from app.schedules import _open_term


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor

    def cursor(self):
        return nullcontext(self.fake_cursor)


class ProfessorHistoryTest(unittest.TestCase):
    def test_closed_term_blocks_claim_and_release_guard(self):
        class Cursor:
            def execute(self, query, params):
                pass

            def fetchone(self):
                return {
                    "status": "CLOSED",
                    "registration_opens_at": datetime.now() - timedelta(days=20),
                    "registration_closes_at": datetime.now() - timedelta(days=10),
                }

        with self.assertRaises(HTTPException) as blocked:
            _open_term(Cursor(), "2026SP")
        self.assertEqual(blocked.exception.status_code, 409)

    def test_closed_term_only_lists_own_taught_sections(self):
        now = datetime.now()

        class Cursor:
            def execute(self, query, params):
                self.query = query

            def fetchone(self):
                if "FROM professor_profile" in self.query:
                    return {"professor_id": "P001"}
                return {
                    "status": "CLOSED",
                    "registration_opens_at": now - timedelta(days=20),
                    "registration_closes_at": now - timedelta(days=10),
                }

            def fetchall(self):
                return []  # 历史授课仍应显示，即使任教资格后来已移除。

        sections = [
            {"offering_id": "2026SP-CS101-01", "course_id": "CS101", "professor_id": "P001"},
            {"offering_id": "2026SP-CS101-02", "course_id": "CS101", "professor_id": "P002"},
        ]
        with patch("app.professors.read_connection", return_value=nullcontext(FakeConnection(Cursor()))), \
                patch("app.professors.offerings_for_term", return_value=sections):
            result = teacher_offerings(1, "2026SP")
        self.assertFalse(result["registration_open"])
        self.assertEqual([row["offering_id"] for row in result["offerings"]], ["2026SP-CS101-01"])

    def test_teacher_terms_are_limited_to_spring_and_fall_query(self):
        class Cursor:
            def execute(self, query, params=None):
                self.query = query

            def fetchone(self):
                return {"professor_id": "P001"}

            def fetchall(self):
                return [
                    {"term_code": "2026FA", "year": 2026, "semester": "FALL", "status": "OPEN"},
                    {"term_code": "2026SP", "year": 2026, "semester": "SPRING", "status": "CLOSED"},
                ]

        cursor = Cursor()
        with patch("app.professors.read_connection", return_value=nullcontext(FakeConnection(cursor))):
            result = teacher_terms(1)
        self.assertIn("semester IN ('SPRING','FALL')", cursor.query)
        self.assertEqual([term["term_code"] for term in result], ["2026FA", "2026SP"])


if __name__ == "__main__":
    unittest.main()
