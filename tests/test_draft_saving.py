"""草稿允许暂存未通过选课规则的志愿；正式提交仍由原校验流程处理。"""
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from app.models import ChoiceInput
from app.schedules import _ensure_states, save_draft


class _Cursor:
    lastrowid = 42

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def execute(self, *_args):
        pass

    def fetchone(self):
        return None  # 尚无该学期课表


@contextmanager
def _transaction():
    class Connection:
        def cursor(self):
            return _Cursor()

    yield Connection()


class DraftSavingTest(unittest.TestCase):
    def test_unmet_prerequisite_does_not_block_draft(self):
        choice = ChoiceInput(offering_id="2026FA-212003-01", choice_type="PRIMARY", priority=1)
        with patch("app.schedules.transaction", _transaction), \
             patch("app.schedules._open_term"), \
             patch("app.schedules.student_id_for_user", return_value="S001"), \
             patch("app.schedules.require_admitted_term"), \
             patch("app.schedules.required_offerings", return_value={
                 choice.offering_id: {"course_id": "212003", "capacity": 10}}), \
             patch("app.schedules.require_curriculum_choices"), \
             patch("app.schedules._ensure_states") as ensure_states, \
             patch("app.schedules._validate_choice_courses"), \
             patch("app.schedules._validate_prerequisites", side_effect=AssertionError("draft checked prerequisite")), \
             patch("app.schedules._validate_conflicts", side_effect=AssertionError("draft checked conflicts")), \
             patch("app.schedules._validate_choice_availability", side_effect=AssertionError("draft checked seats")), \
             patch("app.schedules.get_schedule", return_value={"status": "DRAFT"}):
            self.assertEqual(save_draft(23, "2026FA", [choice])["status"], "DRAFT")
        ensure_states.assert_called_once()
        self.assertFalse(ensure_states.call_args.kwargs["sync_capacity"])

    def test_draft_does_not_reject_changed_capacity_of_closed_class(self):
        class Cursor:
            def __init__(self):
                self.statements = []

            def execute(self, sql, _params):
                self.statements.append(sql)

            def fetchone(self):
                return {"term_code": "2026FA", "capacity": 10,
                        "enrolled_count": 10, "status": "CANCELLED"}

        cursor = Cursor()
        _ensure_states(cursor, "2026FA", {"2026FA-212003-01": {"capacity": 8}},
                       sync_capacity=False)
        self.assertEqual(len(cursor.statements), 2)


if __name__ == "__main__":
    unittest.main()
