"""仅恢复本机 v6 演示库的一次 2026FA 截止处理，不影响其他学期。

本脚本必须在已完整备份「已关闭状态」后运行；仅适用于 2026-10-13
这次关闭且尚未录分、账单仅发往本地 mock 接收端的精确场景。
"""

from app.config import ROOT, settings
from app.db import transaction


TERM = "2026FA"
NEW_DEADLINE = "2026-10-15 23:59:59"
BACKUP = ROOT / ".local-backups/post-close-before-reopen-20261013.sql"


def main() -> None:
    if (settings.db_name, settings.catalog_db, settings.billing_mode) != (
        "course_registration_v6_test", "course_catalog_v6_test", "mock"
    ):
        raise RuntimeError("只允许恢复本机 v6 测试库，且计费必须是 mock 模式")
    if not BACKUP.is_file() or BACKUP.stat().st_size < 70000:
        raise RuntimeError("缺少本次恢复前的已关闭状态备份")

    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT status,registration_closes_at,completed_at,grade_entry_closed_at "
            "FROM academic_term WHERE term_code=%s FOR UPDATE", (TERM,)
        )
        term = cursor.fetchone()
        if not term or term["status"] != "CLOSED" or not term["completed_at"]:
            raise RuntimeError("2026FA 不是预期的已关闭、已确认完成状态")
        if term["grade_entry_closed_at"] is not None:
            raise RuntimeError("录分已关闭；当前恢复脚本不适用")
        cursor.execute(
            "SELECT close_run_id,status FROM registration_close_run "
            "WHERE term_code=%s FOR UPDATE", (TERM,)
        )
        runs = cursor.fetchall()
        if len(runs) != 1 or runs[0]["status"] != "SUCCEEDED":
            raise RuntimeError("截止处理记录已变化，停止恢复")
        run_id = runs[0]["close_run_id"]
        cursor.execute(
            "SELECT schedule_id,status FROM student_schedule "
            "WHERE term_code=%s ORDER BY schedule_id FOR UPDATE", (TERM,)
        )
        schedules = cursor.fetchall()
        if len(schedules) != 13 or any(row["status"] != "FINALIZED" for row in schedules):
            raise RuntimeError("秋季课表数量或状态已变化，停止恢复")
        schedule_ids = tuple(row["schedule_id"] for row in schedules)
        marks = ",".join(["%s"] * len(schedule_ids))
        cursor.execute(
            f"SELECT billing_id,schedule_id,idempotency_key,status,attempts "
            f"FROM billing_outbox WHERE schedule_id IN ({marks}) FOR UPDATE",
            schedule_ids,
        )
        bills = cursor.fetchall()
        if len(bills) != 13 or any(
            row["status"] != "SUCCEEDED" or row["attempts"] != 1 for row in bills
        ):
            raise RuntimeError("模拟账单已变化，停止恢复")
        keys = tuple(row["idempotency_key"] for row in bills)
        key_marks = ",".join(["%s"] * len(keys))
        cursor.execute(
            f"SELECT COUNT(*) AS n FROM mock_billing_receipt "
            f"WHERE idempotency_key IN ({key_marks})", keys,
        )
        if cursor.fetchone()["n"] != 13:
            raise RuntimeError("模拟计费收据与账单不一致，停止恢复")
        cursor.execute(
            "SELECT COUNT(*) AS n FROM enrollment e "
            "JOIN student_schedule s ON s.schedule_id=e.schedule_id "
            "WHERE s.term_code=%s AND (e.letter_grade IS NOT NULL OR e.status='COMPLETED')",
            (TERM,),
        )
        if cursor.fetchone()["n"]:
            raise RuntimeError("2026FA 已录入成绩，不能自动恢复")
        cursor.execute(
            "SELECT COUNT(*) AS n FROM grade_change_log g "
            "JOIN enrollment e ON e.enrollment_id=g.enrollment_id "
            "JOIN student_schedule s ON s.schedule_id=e.schedule_id "
            "WHERE s.term_code=%s", (TERM,),
        )
        if cursor.fetchone()["n"]:
            raise RuntimeError("2026FA 有成绩变更记录，不能自动恢复")
        cursor.execute(
            "SELECT c.choice_type,e.status,COUNT(*) AS n "
            "FROM enrollment e JOIN schedule_choice c ON c.choice_id=e.choice_id "
            "JOIN student_schedule s ON s.schedule_id=e.schedule_id "
            "WHERE s.term_code=%s GROUP BY c.choice_type,e.status", (TERM,),
        )
        enrollment_counts = {(r["choice_type"], r["status"]): r["n"]
                             for r in cursor.fetchall()}
        if sum(n for (kind, _status), n in enrollment_counts.items() if kind == "PRIMARY") != 52:
            raise RuntimeError("原主选报名记录不完整")
        if sum(n for (kind, _status), n in enrollment_counts.items() if kind == "ALTERNATE") != 8:
            raise RuntimeError("截止时生成的备选报名记录已变化")

        # 先清除本次截止处理产生的本地模拟计费副作用。
        cursor.execute(
            f"DELETE FROM mock_billing_receipt WHERE idempotency_key IN ({key_marks})",
            keys,
        )
        if cursor.rowcount != 13:
            raise RuntimeError("模拟计费收据删除数不符")
        cursor.execute(f"DELETE FROM billing_outbox WHERE schedule_id IN ({marks})", schedule_ids)
        if cursor.rowcount != 13:
            raise RuntimeError("模拟账单删除数不符")

        # 截止时创建的备选 enrollment 不存在于原先已提交的课表中。
        cursor.execute(
            "DELETE e FROM enrollment e "
            "JOIN schedule_choice c ON c.choice_id=e.choice_id "
            "JOIN student_schedule s ON s.schedule_id=e.schedule_id "
            "WHERE s.term_code=%s AND c.choice_type='ALTERNATE'", (TERM,),
        )
        if cursor.rowcount != 8:
            raise RuntimeError("备选补位报名删除数不符")
        cursor.execute(
            "UPDATE enrollment e JOIN schedule_choice c ON c.choice_id=e.choice_id "
            "JOIN student_schedule s ON s.schedule_id=e.schedule_id "
            "SET e.status='ENROLLED' "
            "WHERE s.term_code=%s AND c.choice_type='PRIMARY'", (TERM,),
        )
        cursor.execute(
            "UPDATE schedule_choice c JOIN student_schedule s ON s.schedule_id=c.schedule_id "
            "SET c.status=CASE WHEN c.choice_type='PRIMARY' THEN 'ENROLLED' ELSE 'SELECTED' END "
            "WHERE s.term_code=%s", (TERM,),
        )
        cursor.execute(
            "UPDATE student_schedule SET status='SUBMITTED',finalized_at=NULL "
            "WHERE term_code=%s AND status='FINALIZED'", (TERM,),
        )
        if cursor.rowcount != 13:
            raise RuntimeError("秋季课表恢复数量不符")
        cursor.execute(
            "UPDATE offering_registration_state r "
            "SET r.status='OPEN',r.cancellation_reason=NULL,"
            "r.enrolled_count=(SELECT COUNT(*) FROM enrollment e "
            "JOIN schedule_choice c ON c.choice_id=e.choice_id "
            "WHERE e.offering_id=r.offering_id AND e.status='ENROLLED' "
            "AND c.choice_type='PRIMARY') "
            "WHERE r.term_code=%s", (TERM,),
        )
        cursor.execute(
            "UPDATE academic_term SET status='OPEN',registration_closes_at=%s,"
            "closed_at=NULL,closed_by=NULL,completed_at=NULL,grade_entry_closed_at=NULL "
            "WHERE term_code=%s", (NEW_DEADLINE, TERM),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("学期未恢复开放")
        cursor.execute("DELETE FROM registration_close_run WHERE close_run_id=%s", (run_id,))
        if cursor.rowcount != 1:
            raise RuntimeError("截止运行记录未清除")

        cursor.execute(
            "SELECT status,registration_closes_at,completed_at FROM academic_term "
            "WHERE term_code=%s", (TERM,),
        )
        reopened = cursor.fetchone()
        if reopened["status"] != "OPEN" or reopened["completed_at"] is not None:
            raise RuntimeError("学期恢复后的状态不正确")
        cursor.execute(
            "SELECT COUNT(*) AS n FROM enrollment e "
            "JOIN student_schedule s ON s.schedule_id=e.schedule_id "
            "WHERE s.term_code=%s AND e.status='ENROLLED'", (TERM,),
        )
        if cursor.fetchone()["n"] != 52:
            raise RuntimeError("恢复后的主选报名数不正确")
        cursor.execute(
            "SELECT COUNT(*) AS n FROM offering_registration_state r "
            "WHERE r.term_code=%s AND (r.status<>'OPEN' OR r.cancellation_reason IS NOT NULL "
            "OR r.enrolled_count<>(SELECT COUNT(*) FROM enrollment e "
            "WHERE e.offering_id=r.offering_id AND e.status='ENROLLED'))", (TERM,),
        )
        if cursor.fetchone()["n"]:
            raise RuntimeError("恢复后的教学班状态或名额计数不一致")

    print("2026FA 已恢复 OPEN；截止时间恢复为", NEW_DEADLINE)
    print("13 份最终课表恢复为已提交，52 条主选报名恢复为 ENROLLED")
    print("8 条截止时生成的备选报名、13 笔 mock 账单和 13 条 mock 收据已撤销")
    print("2026FA 未录分；教师认领与其他学期数据未改动")


if __name__ == "__main__":
    main()
