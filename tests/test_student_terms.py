"""入学学期决定年级和最早可选课学期。"""
import unittest
from datetime import date

from fastapi import HTTPException

from app.student_terms import (grade_in_term, grade_label, grade_year,
                               require_admitted_term, require_curriculum_choices)
from app.schedules import _validate_prerequisites


class AdmissionTermTest(unittest.TestCase):
    def test_prerequisite_error_contains_both_course_names(self):
        class Cursor:
            def __init__(self):
                self.calls = 0

            def execute(self, *_args):
                self.calls += 1

            def fetchall(self):
                if self.calls == 1:
                    return [{"course_id": "212003", "course_title": "数据结构",
                             "prerequisite_course_id": "212002",
                             "prerequisite_title": "面向对象程序设计", "minimum_grade": "D"}]
                return [{"course_id": "212002", "letter_grade": "F"}]

        with self.assertRaises(HTTPException) as error:
            _validate_prerequisites(Cursor(), "S001",
                                    {"2026FA-212003-01": {"course_id": "212003"}},
                                    ["2026FA-212003-01"])
        self.assertEqual(error.exception.status_code, 400)
        self.assertIn("数据结构", error.exception.detail)
        self.assertIn("面向对象程序设计", error.exception.detail)
        self.assertIn("最低成绩要求 D", error.exception.detail)

    def test_grade_changes_at_fall_academic_year(self):
        self.assertEqual(grade_year(2025, "FALL", today=date(2026, 10, 13)), 2)
        self.assertEqual(grade_year(2025, "FALL", today=date(2026, 3, 1)), 1)
        self.assertEqual(grade_year(2027, "SPRING", today=date(2026, 10, 13)), 0)
        self.assertEqual(grade_label(0), "尚未入学")
        self.assertEqual(grade_label(None), "待补录入学学期")
        self.assertEqual(grade_in_term(2026, "SPRING", 2026, "SPRING"), 1)
        self.assertEqual(grade_in_term(2026, "SPRING", 2026, "FALL"), 2)
        self.assertEqual(grade_in_term(2025, "FALL", 2026, "SPRING"), 1)

    def test_cs_student_cannot_choose_other_grade_or_unplanned_course(self):
        class Cursor:
            def execute(self, *_args):
                pass

            def fetchone(self):
                return {"department_id": "CS", "admission_year": 2026,
                        "admission_semester": "SPRING", "target_year": 2026,
                        "target_semester": "FALL"}

        cursor = Cursor()
        require_curriculum_choices(cursor, "S001", "2026FA",
                                   {"2026FA-212003-01": {"course_id": "212003"}})
        with self.assertRaises(HTTPException) as error:
            require_curriculum_choices(cursor, "S001", "2026FA",
                                       {"2026FA-CS101-01": {"course_id": "CS101"}})
        self.assertEqual(error.exception.status_code, 409)

    def test_rejects_term_before_admission(self):
        class Cursor:
            def execute(self, *_args):
                pass

            def fetchone(self):
                return {"admission_year": 2026, "admission_semester": "FALL",
                        "target_year": 2026, "target_semester": "SPRING"}

        with self.assertRaises(HTTPException) as error:
            require_admitted_term(Cursor(), "S001", "2026SP")
        self.assertEqual(error.exception.status_code, 409)

    def test_legacy_student_remains_usable(self):
        class Cursor:
            def execute(self, *_args):
                pass

            def fetchone(self):
                return {"admission_year": None, "admission_semester": None,
                        "target_year": 2026, "target_semester": "FALL"}

        require_admitted_term(Cursor(), "S001", "2026FA")
