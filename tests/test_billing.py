"""模拟计费故障与幂等重试；仅在隔离测试库启用。"""
from datetime import datetime, timedelta
from decimal import Decimal
import json
import os
import unittest
from uuid import uuid4

from app.billing import MockBillingReceiver, billing_status, dispatch_due
from app.db import read_connection, transaction


@unittest.skipUnless(os.getenv("RUN_DB_INTEGRATION") == "1", "需显式指定隔离测试库")
class BillingFlowTest(unittest.TestCase):
    def test_unavailable_then_lost_ack_then_idempotent_retry(self):
        suffix = uuid4().hex[:7]
        term_code = f"B{suffix}"
        year = 3000 + (int(suffix, 16) % 6000)
        student_id = f"BS{suffix}"
        payload = {
            "term_code": term_code,
            "student_id": student_id,
            "offerings": [{"course_id": "CS101", "offering_id": "mock-only"}],
            "amount": "100.00",
        }
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO academic_term "
                "(term_code,year,semester,registration_opens_at,registration_closes_at,status) "
                "VALUES (%s,%s,'WINTER',%s,%s,'CLOSED')",
                (term_code, year, datetime.now() - timedelta(days=2),
                 datetime.now() - timedelta(days=1)),
            )
            cursor.execute(
                "INSERT INTO student_profile (student_id,full_name,date_of_birth) "
                "VALUES (%s,'计费测试学生','2005-01-01')",
                (student_id,),
            )
            cursor.execute(
                "INSERT INTO student_schedule (student_id,term_code,status) "
                "VALUES (%s,%s,'FINALIZED')",
                (student_id, term_code),
            )
            schedule_id = cursor.lastrowid
            payload["schedule_id"] = schedule_id
            key = f"registration:{term_code}:{schedule_id}"
            cursor.execute(
                "INSERT INTO billing_outbox "
                "(schedule_id,idempotency_key,amount,final_schedule,status) "
                "VALUES (%s,%s,100.00,%s,'PENDING')",
                (schedule_id, key, json.dumps(payload, ensure_ascii=False)),
            )

        self.assertEqual(billing_status(term_code)["counts"]["PENDING"], 1)
        failed = dispatch_due(receiver=MockBillingReceiver(available=False), term_code=term_code)
        self.assertEqual(failed["retry_scheduled"], 1)
        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM mock_billing_receipt WHERE idempotency_key=%s", (key,))
            self.assertEqual(cursor.fetchone()["n"], 0)
        self._make_due(key)

        lost_ack = dispatch_due(receiver=MockBillingReceiver(lose_ack_once=True), term_code=term_code)
        self.assertEqual(lost_ack["retry_scheduled"], 1)
        status = billing_status(term_code)
        self.assertEqual(status["counts"]["RETRYING"], 1)
        self.assertIsNotNone(status["bills"][0]["received_at"])
        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM mock_billing_receipt WHERE idempotency_key=%s", (key,))
            self.assertEqual(cursor.fetchone()["n"], 1)
        self._make_due(key)

        retried = dispatch_due(term_code=term_code)
        self.assertEqual(retried["succeeded"], 1)
        self.assertEqual(retried["new_receipts"], 0)
        self.assertEqual(dispatch_due(term_code=term_code)["processed"], 0)
        status = billing_status(term_code)
        self.assertEqual(status["counts"]["SUCCEEDED"], 1)
        self.assertEqual(status["bills"][0]["attempts"], 3)
        self.assertIsNone(status["bills"][0]["last_error"])
        self.assertIsNotNone(status["bills"][0]["sent_at"])

        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT schedule_id,idempotency_key,amount,final_schedule "
                "FROM billing_outbox WHERE idempotency_key=%s",
                (key,),
            )
            original = cursor.fetchone()
        self.assertFalse(MockBillingReceiver().send(original))
        changed = dict(original)
        changed["amount"] = Decimal("200.00")
        wrong_payload = dict(payload)
        wrong_payload["amount"] = "200.00"
        changed["final_schedule"] = json.dumps(wrong_payload, ensure_ascii=False)
        with self.assertRaises(ValueError):
            MockBillingReceiver().send(changed)
        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT amount FROM mock_billing_receipt WHERE idempotency_key=%s", (key,))
            self.assertEqual(cursor.fetchone()["amount"], Decimal("100.00"))

    @staticmethod
    def _make_due(key: str) -> None:
        # 仅在隔离库推进重试时间，避免测试真的等待 30–60 秒。
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE billing_outbox SET next_attempt_at=NOW()-INTERVAL 1 SECOND "
                "WHERE idempotency_key=%s",
                (key,),
            )
