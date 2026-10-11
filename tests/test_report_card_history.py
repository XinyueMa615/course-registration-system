"""历史成绩筛选和新学期学季限制，无需连接数据库。"""
import unittest
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.grades import report_card, report_card_history, report_card_terms
from app.models import TermCreate


class FakeCursor:
    def __init__(self):
        self.query = ""
        self.params = ()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        self.query = query
        self.params = params

    def fetchone(self):
        if "FROM student_profile" in self.query:
            return {"student_id": "S001"}
        if "SELECT 1 FROM academic_term" in self.query:
            return {"1": 1} if self.params == ("2026SU",) else None
        return None

    def fetchall(self):
        if "FROM academic_term t" in self.query:
            return [
                {"term_code": "2026SU", "year": 2026, "semester": "SUMMER"},
                {"term_code": "2025FA", "year": 2025, "semester": "FALL"},
                {"term_code": "2025SP", "year": 2025, "semester": "SPRING"},
            ]
        if "FROM v_report_card" in self.query and "JOIN academic_term" in self.query:
            return [
                {"term_code": "2026SU", "year": 2026, "semester": "SUMMER",
                 "offering_id": "2026SU-CS101-01", "course_id": "CS101", "title": "程序设计基础",
                 "credits": 4, "letter_grade": "A", "graded_at": None},
                {"term_code": "2026SU", "year": 2026, "semester": "SUMMER",
                 "offering_id": "2026SU-MA101-01", "course_id": "MA101", "title": "高等数学",
                 "credits": 4, "letter_grade": None, "graded_at": None},
                {"term_code": "2025FA", "year": 2025, "semester": "FALL",
                 "offering_id": "2025FA-CS101-01", "course_id": "CS101", "title": "程序设计基础",
                 "credits": 4, "letter_grade": "B", "graded_at": None},
            ]
        if "FROM v_report_card" in self.query:
            return [{"term_code": "2026SU", "offering_id": "2026SU-CS101-01", "letter_grade": "A"}]
        return []


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


class ReportCardHistoryTest(unittest.TestCase):
    def setUp(self):
        self.cursor = FakeCursor()

        @contextmanager
        def fake_read_connection():
            yield FakeConnection(self.cursor)

        self.patcher = patch("app.grades.read_connection", fake_read_connection)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_completed_terms_include_legacy_history(self):
        terms = report_card_terms(1)
        self.assertEqual([item["term_code"] for item in terms], ["2026SU", "2025FA", "2025SP"])
        self.assertIn("completed_at IS NOT NULL", self.cursor.query)
        self.assertEqual(self.cursor.params, ("S001",))

    def test_selected_term_is_scoped_to_logged_in_student(self):
        card = report_card(1, "2026SU")
        self.assertEqual(card["term_code"], "2026SU")
        self.assertEqual(card["courses"][0]["letter_grade"], "A")
        self.assertEqual(self.cursor.params, ("S001", "2026SU"))

    def test_all_history_is_grouped_newest_first_and_scoped_to_student(self):
        history = report_card_history(1)
        self.assertEqual([term["term_code"] for term in history["terms"]], ["2026SU", "2025FA", "2025SP"])
        self.assertEqual([len(term["courses"]) for term in history["terms"]], [2, 1, 0])
        self.assertIsNone(history["terms"][0]["courses"][1]["letter_grade"])
        self.assertEqual(self.cursor.params, ("S001",))
        self.assertIn("completed_at IS NOT NULL", self.cursor.query)

    def test_unfinished_or_unknown_term_rejected(self):
        with self.assertRaises(HTTPException) as error:
            report_card(1, "2026FA")
        self.assertEqual(error.exception.status_code, 404)


class AllowedSemesterTest(unittest.TestCase):
    def test_only_spring_and_fall_can_be_created(self):
        values = {
            "term_code": "2027SP",
            "year": 2027,
            "registration_opens_at": datetime(2027, 1, 1),
            "registration_closes_at": datetime(2027, 1, 31),
        }
        for semester in ("SPRING", "FALL"):
            self.assertEqual(TermCreate(**values, semester=semester).semester, semester)
        for semester in ("SUMMER", "WINTER"):
            with self.assertRaises(ValidationError):
                TermCreate(**values, semester=semester)


class ApiStartupTest(unittest.TestCase):
    def test_history_route_loads_under_project_python(self):
        from app.main import app

        self.assertIn("/api/students/me/report-card-history", {route.path for route in app.routes})


if __name__ == "__main__":
    unittest.main()
