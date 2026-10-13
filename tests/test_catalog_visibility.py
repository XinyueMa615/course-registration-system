"""学生课程目录的院系和年级范围。"""
import unittest
from unittest.mock import patch

from app.catalog import student_offerings_for_term
from app.main import catalog


class _Cursor:
    def __init__(self, row):
        self.row = row
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def execute(self, _query, params):
        self.params = params

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, row):
        self.query_cursor = _Cursor(row)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def cursor(self):
        return self.query_cursor


class CatalogVisibilityTest(unittest.TestCase):
    def test_student_sees_only_own_department_and_term_grade(self):
        row = {"department_id": "CS", "admission_year": 2026,
               "admission_semester": "SPRING", "target_year": 2026,
               "target_semester": "FALL"}
        sections = [
            {"course_id": "212003", "department_id": "CS"},
            {"course_id": "211012", "department_id": "CS"},
            {"course_id": "212002", "department_id": "CS"},
            {"course_id": "MA101", "department_id": "MATH"},
        ]
        connection = _Connection(row)
        with patch("app.catalog.read_connection", return_value=connection), \
             patch("app.catalog.offerings_for_term", return_value=sections):
            visible = student_offerings_for_term(23, "2026FA")
        self.assertEqual(connection.query_cursor.params, ("2026FA", 23))
        self.assertEqual([item["course_id"] for item in visible], ["212003", "211012"])

    def test_missing_curriculum_never_falls_back_to_full_catalog(self):
        row = {"department_id": "MATH", "admission_year": 2026,
               "admission_semester": "SPRING", "target_year": 2026,
               "target_semester": "FALL"}
        with patch("app.catalog.read_connection", return_value=_Connection(row)), \
             patch("app.catalog.offerings_for_term") as all_offerings:
            self.assertEqual(student_offerings_for_term(24, "2026FA"), [])
        all_offerings.assert_not_called()

    def test_other_roles_still_use_full_catalog(self):
        with patch("app.main.student_offerings_for_term", return_value=[{"course_id": "212003"}]) as student_list, \
             patch("app.main.offerings_for_term", return_value=[{"course_id": "MA101"}]) as all_list:
            self.assertEqual(catalog("2026FA", {"role": "STUDENT", "user_id": 23}),
                             [{"course_id": "212003"}])
            self.assertEqual(catalog("2026FA", {"role": "PROFESSOR", "user_id": 1}),
                             [{"course_id": "MA101"}])
            self.assertEqual(catalog("2026FA", {"role": "REGISTRAR", "user_id": 2}),
                             [{"course_id": "MA101"}])
        student_list.assert_called_once_with(23, "2026FA")
        self.assertEqual(all_list.call_count, 2)
