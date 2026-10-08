"""教务员配置学期；关闭学期由 closing 模块独立处理。"""
from datetime import datetime

from fastapi import HTTPException
from pymysql.err import IntegrityError

from .catalog import CATALOG
from .db import read_connection, transaction
from .models import TermCreate, TermPatch


def _dates(open_at: datetime, close_at: datetime) -> None:
    if open_at.tzinfo is not None or close_at.tzinfo is not None:
        raise HTTPException(400, "请输入本地日期时间，不要附加时区")
    if close_at <= open_at:
        raise HTTPException(400, "选课截止时间必须晚于开放时间")


def terms() -> list[dict]:
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT term_code,year,semester,registration_opens_at,registration_closes_at,"
            "status,tuition_per_credit,closed_at,completed_at FROM academic_term ORDER BY year DESC,term_code DESC"
        )
        return cursor.fetchall()


def term(term_code: str) -> dict:
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT term_code,year,semester,registration_opens_at,registration_closes_at,"
            "status,tuition_per_credit,closed_at,completed_at FROM academic_term WHERE term_code=%s",
            (term_code,),
        )
        row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "学期不存在")
    return row


def create_term(user_id: int, body: TermCreate) -> dict:
    _dates(body.registration_opens_at, body.registration_closes_at)
    try:
        with transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO academic_term "
                "(term_code,year,semester,registration_opens_at,registration_closes_at,tuition_per_credit,status) "
                "VALUES (%s,%s,%s,%s,%s,%s,'DRAFT')",
                (body.term_code, body.year, body.semester, body.registration_opens_at,
                 body.registration_closes_at, body.tuition_per_credit),
            )
            cursor.execute(
                "INSERT INTO audit_log (user_id,action,entity_type,entity_id) "
                "VALUES (%s,'CREATE_TERM','TERM',%s)",
                (user_id, body.term_code),
            )
    except IntegrityError:
        raise HTTPException(409, "学期代码或年份/学期已存在") from None
    return term(body.term_code)


def update_term(user_id: int, term_code: str, body: TermPatch) -> dict:
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "没有需要修改的字段")
    if any(value is None for value in updates.values()):
        raise HTTPException(400, "学期配置字段不能为空")
    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT status,registration_opens_at,registration_closes_at FROM academic_term "
            "WHERE term_code=%s FOR UPDATE",
            (term_code,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "学期不存在")
        if row["status"] not in ("DRAFT", "OPEN"):
            raise HTTPException(409, "正在关闭或已关闭的学期不能修改")
        open_at = updates.get("registration_opens_at", row["registration_opens_at"])
        close_at = updates.get("registration_closes_at", row["registration_closes_at"])
        _dates(open_at, close_at)
        if row["status"] == "OPEN" and close_at <= datetime.now():
            raise HTTPException(409, "不能将开放学期的截止时间修改为过去；请等待原截止时间")
        assignments = ",".join(f"{field}=%s" for field in updates)
        cursor.execute(
            f"UPDATE academic_term SET {assignments} WHERE term_code=%s",
            (*updates.values(), term_code),
        )
        cursor.execute(
            "INSERT INTO audit_log (user_id,action,entity_type,entity_id) "
            "VALUES (%s,'UPDATE_TERM','TERM',%s)",
            (user_id, term_code),
        )
    return term(term_code)


def open_term(user_id: int, term_code: str) -> dict:
    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT status,registration_closes_at FROM academic_term WHERE term_code=%s FOR UPDATE",
            (term_code,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "学期不存在")
        if row["status"] != "DRAFT":
            raise HTTPException(409, "只有草稿学期可以开放")
        if row["registration_closes_at"] <= datetime.now():
            raise HTTPException(409, "选课截止时间已过，不能开放")
        cursor.execute(
            f"SELECT 1 FROM {CATALOG}.course_offering WHERE term_code=%s LIMIT 1",
            (term_code,),
        )
        if not cursor.fetchone():
            raise HTTPException(409, "课程目录中没有该学期的教学班")
        cursor.execute("UPDATE academic_term SET status='OPEN' WHERE term_code=%s", (term_code,))
        cursor.execute(
            "INSERT INTO audit_log (user_id,action,entity_type,entity_id) "
            "VALUES (%s,'OPEN_TERM','TERM',%s)",
            (user_id, term_code),
        )
    return term(term_code)


def complete_term(user_id: int, term_code: str) -> dict:
    """教务确认整学期教学结束；选课关闭本身不开放录分。"""
    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT status,completed_at FROM academic_term WHERE term_code=%s FOR UPDATE",
            (term_code,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "学期不存在")
        if row["status"] != "CLOSED":
            raise HTTPException(409, "必须先正式关闭选课，才能确认学期教学结束")
        if row["completed_at"] is not None:
            raise HTTPException(409, "该学期已经确认完成")
        cursor.execute(
            "UPDATE academic_term SET completed_at=NOW() WHERE term_code=%s", (term_code,)
        )
        cursor.execute(
            "INSERT INTO audit_log (user_id,action,entity_type,entity_id) "
            "VALUES (%s,'COMPLETE_TERM','TERM',%s)",
            (user_id, term_code),
        )
    return term(term_code)
