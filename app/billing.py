"""本地模拟计费接收端 + 可重试 outbox 投递器。

接收端与发送端分别提交事务，模拟“已收到但确认丢失”的真实故障窗口。
"""
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json
from typing import Optional, Protocol
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastapi import HTTPException

from .config import settings
from .db import read_connection, transaction


class BillingReceiver(Protocol):
    def send(self, bill: dict) -> bool: ...


def _validated_payload(bill: dict) -> tuple[dict, Decimal, str]:
    payload = json.loads(bill["final_schedule"])
    amount = Decimal(bill["amount"])
    if payload.get("schedule_id") != bill["schedule_id"] or Decimal(payload.get("amount", "-1")) != amount:
        raise ValueError("账单快照与待发送记录不一致")
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return payload, amount, canonical


class MockBillingReceiver:
    def __init__(self, *, available: bool = True, lose_ack_once: bool = False):
        self.available = available
        self.lose_ack_once = lose_ack_once

    def send(self, bill: dict) -> bool:
        """返回 True 表示新接收，False 表示同一幂等键已接收过。"""
        if not self.available:
            raise ConnectionError("模拟计费系统不可用")
        _, amount, canonical = _validated_payload(bill)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO mock_billing_receipt "
                "(idempotency_key,schedule_id,amount,payload_sha256,final_schedule) "
                "VALUES (%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE idempotency_key=idempotency_key",
                (bill["idempotency_key"], bill["schedule_id"], amount, digest, canonical),
            )
            inserted = cursor.rowcount == 1
            cursor.execute(
                "SELECT schedule_id,amount,payload_sha256 FROM mock_billing_receipt "
                "WHERE idempotency_key=%s",
                (bill["idempotency_key"],),
            )
            receipt = cursor.fetchone()
            if (not receipt or receipt["schedule_id"] != bill["schedule_id"]
                    or receipt["amount"] != amount or receipt["payload_sha256"] != digest):
                raise ValueError("幂等键已被不同账单占用，已拒绝重复计费")
        if self.lose_ack_once:
            self.lose_ack_once = False
            raise ConnectionError("模拟网络故障：计费系统已接收，但确认消息丢失")
        return inserted


class HTTPBillingReceiver:
    """向真实计费 HTTP 接口投递账单；对方须按 Idempotency-Key 去重。"""

    def __init__(self, url: str, *, token: str = "", timeout_seconds: float = 10):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("BILLING_URL 必须是有效的 http/https 地址")
        if not 0 < timeout_seconds <= 120:
            raise ValueError("BILLING_TIMEOUT_SECONDS 必须在 0–120 秒之间")
        self.url = url
        self.token = token
        self.timeout_seconds = timeout_seconds

    def send(self, bill: dict) -> bool:
        _, _, canonical = _validated_payload(bill)
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "Idempotency-Key": bill["idempotency_key"],
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(self.url, data=canonical.encode("utf-8"), headers=headers, method="POST")
        with urlopen(request, timeout=self.timeout_seconds) as response:
            if not 200 <= response.status < 300:
                raise ConnectionError(f"计费接口返回 HTTP {response.status}")
            raw = response.read()
        if not raw:
            return True
        try:
            result = json.loads(raw)
        except (TypeError, ValueError):
            return True
        return not bool(result.get("duplicate", False))


def configured_receiver() -> BillingReceiver:
    if settings.billing_mode == "mock":
        return MockBillingReceiver()
    if settings.billing_mode == "http":
        if not settings.billing_url:
            raise RuntimeError("BILLING_MODE=http 时必须配置 BILLING_URL")
        return HTTPBillingReceiver(
            settings.billing_url,
            token=settings.billing_token,
            timeout_seconds=settings.billing_timeout_seconds,
        )
    raise RuntimeError("BILLING_MODE 只能是 mock 或 http")


def _require_mock_table() -> None:
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema=DATABASE() AND table_name='mock_billing_receipt'"
        )
        if not cursor.fetchone():
            raise HTTPException(503, "请先在 MySQL Workbench 执行 database/07_billing_mock.sql")


def _claim_due(term_code: Optional[str] = None) -> Optional[dict]:
    with transaction() as connection, connection.cursor() as cursor:
        term_filter = (
            " AND schedule_id IN (SELECT schedule_id FROM student_schedule WHERE term_code=%s)"
            if term_code else ""
        )
        cursor.execute(
            "SELECT billing_id,schedule_id,idempotency_key,amount,final_schedule,attempts "
            "FROM billing_outbox "
            "WHERE status IN ('PENDING','RETRYING') "
            "AND (next_attempt_at IS NULL OR next_attempt_at<=NOW()) "
            + term_filter + " ORDER BY billing_id LIMIT 1 FOR UPDATE SKIP LOCKED",
            (term_code,) if term_code else (),
        )
        row = cursor.fetchone()
        if not row:
            return None
        row["attempts"] += 1
        cursor.execute(
            "UPDATE billing_outbox SET status='RETRYING',attempts=%s,"
            "next_attempt_at=%s,last_error=NULL WHERE billing_id=%s",
            (row["attempts"], datetime.now() + timedelta(seconds=60), row["billing_id"]),
        )
        return row


def _succeed(bill: dict) -> bool:
    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute(
            "UPDATE billing_outbox SET status='SUCCEEDED',sent_at=NOW(),"
            "next_attempt_at=NULL,last_error=NULL "
            "WHERE billing_id=%s AND status='RETRYING' AND attempts=%s",
            (bill["billing_id"], bill["attempts"]),
        )
        # 旧租约可能已被另一个 worker 接管；接收端幂等，不能覆盖新尝试的状态。
        return cursor.rowcount == 1


def _fail(bill: dict, error: Exception) -> bool:
    delay = min(30 * (2 ** min(bill["attempts"] - 1, 5)), 600)
    description = f"{type(error).__name__}: {error}"[:450]
    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute(
            "UPDATE billing_outbox SET status='RETRYING',next_attempt_at=%s,last_error=%s "
            "WHERE billing_id=%s AND status='RETRYING' AND attempts=%s",
            (datetime.now() + timedelta(seconds=delay), description,
             bill["billing_id"], bill["attempts"]),
        )
        return cursor.rowcount == 1


def dispatch_due(
    limit: int = 20,
    receiver: Optional[BillingReceiver] = None,
    term_code: Optional[str] = None,
) -> dict:
    """处理到期记录；后台定时调用，也可由教务员手动触发。"""
    if not 1 <= limit <= 100:
        raise ValueError("limit 应为 1–100")
    receiver = receiver or configured_receiver()
    if isinstance(receiver, MockBillingReceiver):
        _require_mock_table()
    summary = {"processed": 0, "succeeded": 0, "retry_scheduled": 0, "new_receipts": 0}
    for _ in range(limit):
        bill = _claim_due(term_code)
        if bill is None:
            break
        summary["processed"] += 1
        try:
            inserted = receiver.send(bill)
        except Exception as error:
            summary["retry_scheduled"] += int(_fail(bill, error))
        else:
            summary["succeeded"] += int(_succeed(bill))
            summary["new_receipts"] += int(inserted)
    return summary


def billing_status(term_code: str) -> dict:
    if settings.billing_mode == "mock":
        _require_mock_table()
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT status FROM academic_term WHERE term_code=%s", (term_code,))
        term = cursor.fetchone()
        if not term:
            raise HTTPException(404, "学期不存在")
        receipt_join = (
            "LEFT JOIN mock_billing_receipt r ON r.idempotency_key=b.idempotency_key "
            if settings.billing_mode == "mock" else ""
        )
        received_column = "r.received_at" if settings.billing_mode == "mock" else "NULL AS received_at"
        cursor.execute(
            "SELECT b.billing_id,b.schedule_id,s.student_id,b.amount,b.status,b.attempts,"
            f"b.next_attempt_at,b.last_error,b.sent_at,{received_column} "
            "FROM billing_outbox b JOIN student_schedule s ON s.schedule_id=b.schedule_id "
            + receipt_join + "WHERE s.term_code=%s ORDER BY b.billing_id",
            (term_code,),
        )
        rows = cursor.fetchall()
    counts = {"PENDING": 0, "RETRYING": 0, "SUCCEEDED": 0}
    for row in rows:
        counts[row["status"]] += 1
    return {
        "term_code": term_code,
        "term_status": term["status"],
        "receiver_mode": settings.billing_mode,
        "counts": counts,
        "bills": rows,
    }
