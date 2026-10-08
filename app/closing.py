"""按题目给定顺序模拟并原子执行选课截止。

预览只读；正式截止重新计算，锁住学期行，所有变更在单个事务中提交。
"""
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import json

from fastapi import HTTPException

from .catalog import CATALOG
from .db import read_connection, transaction


GRADE_VALUE = {"A": 4, "B": 3, "C": 2, "D": 1}


def _term(cursor, term_code: str, *, lock: bool) -> dict:
    cursor.execute(
        "SELECT term_code,status,registration_opens_at,registration_closes_at,tuition_per_credit "
        "FROM academic_term WHERE term_code=%s" + (" FOR UPDATE" if lock else ""),
        (term_code,),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "学期不存在")
    if row["status"] != "OPEN":
        raise HTTPException(409, "只有开放状态的学期可以预览或关闭")
    return row


def _load_plan(cursor, term: dict) -> dict:
    term_code = term["term_code"]
    cursor.execute(
        f"SELECT o.offering_id,o.course_id,o.capacity,c.title,c.credits "
        f"FROM {CATALOG}.course_offering o JOIN {CATALOG}.course c ON c.course_id=o.course_id "
        "WHERE o.term_code=%s ORDER BY o.offering_id",
        (term_code,),
    )
    offerings = {row["offering_id"]: row for row in cursor.fetchall()}
    if not offerings:
        raise HTTPException(409, "课程目录中没有该学期的教学班")
    cursor.execute(
        "SELECT offering_id,capacity,enrolled_count,status FROM offering_registration_state WHERE term_code=%s",
        (term_code,),
    )
    states = {row["offering_id"]: row for row in cursor.fetchall()}
    if set(states) - set(offerings):
        raise HTTPException(409, "业务库含有目录中已不存在的教学班，不能安全关闭")
    for offering_id, state in states.items():
        if state["status"] != "OPEN" or state["capacity"] != offerings[offering_id]["capacity"]:
            raise HTTPException(409, f"教学班 {offering_id} 的状态或容量与目录不一致")
    counts = {
        offering_id: states[offering_id]["enrolled_count"] if offering_id in states else 0
        for offering_id in offerings
    }
    cursor.execute(
        "SELECT a.offering_id FROM teaching_assignment a "
        "JOIN offering_registration_state s ON s.offering_id=a.offering_id "
        "JOIN professor_profile p ON p.professor_id=a.professor_id "
        "WHERE s.term_code=%s AND p.status='ACTIVE'",
        (term_code,),
    )
    taught = {row["offering_id"] for row in cursor.fetchall()}
    cursor.execute(
        "SELECT schedule_id,student_id FROM student_schedule "
        "WHERE term_code=%s AND status='SUBMITTED' ORDER BY schedule_id",
        (term_code,),
    )
    schedules = cursor.fetchall()
    schedule_ids = {row["schedule_id"] for row in schedules}
    cursor.execute(
        "SELECT c.choice_id,c.schedule_id,c.offering_id,c.choice_type,c.priority,c.status,"
        "e.enrollment_id,e.status AS enrollment_status "
        "FROM schedule_choice c JOIN student_schedule s ON s.schedule_id=c.schedule_id "
        "LEFT JOIN enrollment e ON e.choice_id=c.choice_id "
        "WHERE s.term_code=%s AND s.status='SUBMITTED' "
        "ORDER BY c.schedule_id,FIELD(c.choice_type,'PRIMARY','ALTERNATE'),c.priority",
        (term_code,),
    )
    choice_rows = cursor.fetchall()
    choices = defaultdict(list)
    for row in choice_rows:
        if row["offering_id"] not in offerings:
            raise HTTPException(409, "已提交课表引用了目录中不存在的教学班")
        choices[row["schedule_id"]].append(row)
    for schedule in schedules:
        rows = choices[schedule["schedule_id"]]
        primary = [r for r in rows if r["choice_type"] == "PRIMARY"]
        alternates = [r for r in rows if r["choice_type"] == "ALTERNATE"]
        if (len(primary) != 4 or len(alternates) != 2
                or {r["priority"] for r in primary} != {1, 2, 3, 4}
                or {r["priority"] for r in alternates} != {1, 2}):
            raise HTTPException(409, f"课表 {schedule['schedule_id']} 的志愿数量不完整")
        if any(r["enrollment_id"] is None or r["enrollment_status"] != "ENROLLED" or r["status"] != "ENROLLED" for r in primary):
            raise HTTPException(409, f"课表 {schedule['schedule_id']} 的主选记录不一致")
        if any(r["enrollment_id"] is not None or r["status"] != "SELECTED" for r in alternates):
            raise HTTPException(409, f"课表 {schedule['schedule_id']} 的备选记录不一致")
    cursor.execute(
        "SELECT e.offering_id,COUNT(*) AS n,SUM(s.status <> 'SUBMITTED') AS invalid_schedule "
        "FROM enrollment e JOIN student_schedule s ON s.schedule_id=e.schedule_id "
        "WHERE s.term_code=%s AND e.status='ENROLLED' GROUP BY e.offering_id",
        (term_code,),
    )
    actual_counts = {row["offering_id"]: row for row in cursor.fetchall()}
    if any(row["invalid_schedule"] for row in actual_counts.values()):
        raise HTTPException(409, "存在不属于已提交课表的占位记录")
    if any(counts[offering_id] != actual_counts.get(offering_id, {}).get("n", 0) for offering_id in offerings):
        raise HTTPException(409, "教学班名额计数与选课记录不一致")
    cursor.execute(
        "SELECT 1 FROM billing_outbox b JOIN student_schedule s ON s.schedule_id=b.schedule_id "
        "WHERE s.term_code=%s LIMIT 1",
        (term_code,),
    )
    if cursor.fetchone():
        raise HTTPException(409, "该学期已有计费记录，不能重复关闭")

    cursor.execute(
        f"SELECT m.offering_id,m.weekday,m.start_period,m.end_period "
        f"FROM {CATALOG}.offering_meeting m "
        f"JOIN {CATALOG}.course_offering o ON o.offering_id=m.offering_id WHERE o.term_code=%s",
        (term_code,),
    )
    meetings = defaultdict(list)
    for row in cursor.fetchall():
        meetings[row["offering_id"]].append(row)
    cursor.execute(
        f"SELECT DISTINCT p.course_id,p.prerequisite_course_id,p.minimum_grade "
        f"FROM {CATALOG}.course_prerequisite p "
        f"JOIN {CATALOG}.course_offering o ON o.course_id=p.course_id WHERE o.term_code=%s",
        (term_code,),
    )
    prerequisites = defaultdict(list)
    for row in cursor.fetchall():
        prerequisites[row["course_id"]].append(row)
    passed = defaultdict(lambda: defaultdict(int))
    if schedules:
        placeholders = ",".join(["%s"] * len(schedules))
        cursor.execute(
            f"SELECT s.student_id,o.course_id,e.letter_grade "
            f"FROM enrollment e JOIN student_schedule s ON s.schedule_id=e.schedule_id "
            f"JOIN {CATALOG}.course_offering o ON o.offering_id=e.offering_id "
            f"WHERE e.status='COMPLETED' AND e.letter_grade IS NOT NULL "
            f"AND s.student_id IN ({placeholders})",
            tuple(row["student_id"] for row in schedules),
        )
        for row in cursor.fetchall():
            passed[row["student_id"]][row["course_id"]] = max(
                passed[row["student_id"]][row["course_id"]], GRADE_VALUE.get(row["letter_grade"], 0)
            )

    # 第 2 步：无教师的班直接取消；低于 3 人的班暂留，等待第 3 步备选补位。
    cancellations = {offering_id: "NO_PROFESSOR" for offering_id in offerings if offering_id not in taught}
    active = {}
    for schedule in schedules:
        schedule_id = schedule["schedule_id"]
        active[schedule_id] = {
            row["offering_id"] for row in choices[schedule_id]
            if row["choice_type"] == "PRIMARY" and row["offering_id"] not in cancellations
        }
    for offering_id in cancellations:
        counts[offering_id] = 0

    def available(candidate: str, current: set[str], student_id: str) -> bool:
        if candidate in cancellations or candidate not in taught or counts[candidate] >= offerings[candidate]["capacity"]:
            return False
        course_id = offerings[candidate]["course_id"]
        if any(offerings[chosen]["course_id"] == course_id for chosen in current):
            return False
        for req in prerequisites[course_id]:
            if passed[student_id][req["prerequisite_course_id"]] < GRADE_VALUE[req["minimum_grade"]]:
                return False
        for a in meetings[candidate]:
            for chosen in current:
                for b in meetings[chosen]:
                    if a["weekday"] == b["weekday"] and a["start_period"] <= b["end_period"] and b["start_period"] <= a["end_period"]:
                        return False
        return True

    # 第 3 步：按课表创建顺序处理学生，每人按备选优先级挑第一个可用班。
    selected_alternates = defaultdict(list)
    for schedule in schedules:
        schedule_id = schedule["schedule_id"]
        current = active[schedule_id]
        for row in choices[schedule_id]:
            if row["choice_type"] != "ALTERNATE" or len(current) >= 4:
                continue
            candidate = row["offering_id"]
            if available(candidate, current, schedule["student_id"]):
                current.add(candidate)
                counts[candidate] += 1
                selected_alternates[schedule_id].append(row)

    # 第 4 步：补位后的最终人数仍不足 3 人，则取消；题目未要求再次补位。
    for offering_id in offerings:
        if offering_id not in cancellations and counts[offering_id] < 3:
            cancellations[offering_id] = "TOO_FEW_STUDENTS"
            counts[offering_id] = 0
    for current in active.values():
        current.difference_update(cancellations)

    bills = []
    tuition = Decimal(term["tuition_per_credit"])
    for schedule in schedules:
        schedule_id = schedule["schedule_id"]
        final_offerings = sorted(active[schedule_id])
        credits = sum((Decimal(offerings[offering_id]["credits"]) for offering_id in final_offerings), Decimal("0"))
        amount = (credits * tuition).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        bills.append({
            "schedule_id": schedule_id,
            "student_id": schedule["student_id"],
            "offering_ids": final_offerings,
            "credits": str(credits),
            "amount": str(amount),
        })
    return {
        "term_code": term_code,
        "offerings": offerings,
        "states": states,
        "counts": counts,
        "cancellations": cancellations,
        "schedules": schedules,
        "choices": choices,
        "selected_alternates": selected_alternates,
        "active": active,
        "bills": bills,
    }


def _public(plan: dict, term: dict) -> dict:
    return {
        "term_code": plan["term_code"],
        "can_close": datetime.now() > term["registration_closes_at"],
        "registration_closes_at": term["registration_closes_at"],
        "submitted_schedules": len(plan["schedules"]),
        "cancelled_offerings": [
            {"offering_id": offering_id, "reason": reason}
            for offering_id, reason in sorted(plan["cancellations"].items())
        ],
        "committed_offerings": [
            {"offering_id": offering_id, "students": plan["counts"][offering_id]}
            for offering_id in sorted(plan["offerings"]) if offering_id not in plan["cancellations"]
        ],
        "alternate_placements": [
            {"schedule_id": schedule_id, "offering_id": row["offering_id"],
             "survived": row["offering_id"] not in plan["cancellations"]}
            for schedule_id, rows in sorted(plan["selected_alternates"].items()) for row in rows
        ],
        "billing_transactions": len(plan["bills"]),
        "billing_total": str(sum((Decimal(b["amount"]) for b in plan["bills"]), Decimal("0"))),
        "preview_only": True,
    }


def preview_close(term_code: str) -> dict:
    with read_connection() as connection, connection.cursor() as cursor:
        term = _term(cursor, term_code, lock=False)
        plan = _load_plan(cursor, term)
        return _public(plan, term)


def close_registration(user_id: int, term_code: str) -> dict:
    with transaction() as connection, connection.cursor() as cursor:
        term = _term(cursor, term_code, lock=True)
        if datetime.now() <= term["registration_closes_at"]:
            raise HTTPException(409, "选课仍在进行，截止时间到了之后才能正式关闭")
        # 有些目录教学班尚未被学生选中，业务库可能没有对应状态行。
        cursor.execute(
            f"SELECT offering_id,capacity FROM {CATALOG}.course_offering WHERE term_code=%s",
            (term_code,),
        )
        for row in cursor.fetchall():
            cursor.execute(
                "INSERT INTO offering_registration_state (offering_id,term_code,capacity) "
                "VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE offering_id=offering_id",
                (row["offering_id"], term_code, row["capacity"]),
            )
        plan = _load_plan(cursor, term)
        cursor.execute(
            "INSERT INTO registration_close_run (term_code,started_by,status) VALUES (%s,%s,'RUNNING')",
            (term_code, user_id),
        )
        close_run_id = cursor.lastrowid
        for offering_id in sorted(plan["offerings"]):
            reason = plan["cancellations"].get(offering_id)
            cursor.execute(
                "UPDATE offering_registration_state "
                "SET status=%s,cancellation_reason=%s,enrolled_count=%s WHERE offering_id=%s",
                ("CANCELLED" if reason else "COMMITTED", reason, plan["counts"][offering_id], offering_id),
            )
        for schedule in plan["schedules"]:
            schedule_id = schedule["schedule_id"]
            for row in plan["choices"][schedule_id]:
                if row["choice_type"] == "PRIMARY":
                    survived = row["offering_id"] not in plan["cancellations"]
                    cursor.execute(
                        "UPDATE enrollment SET status=%s WHERE enrollment_id=%s",
                        ("COMMITTED" if survived else "CANCELLED", row["enrollment_id"]),
                    )
                    cursor.execute(
                        "UPDATE schedule_choice SET status=%s WHERE choice_id=%s",
                        ("ENROLLED" if survived else "CANCELLED", row["choice_id"]),
                    )
            for row in plan["selected_alternates"][schedule_id]:
                survived = row["offering_id"] not in plan["cancellations"]
                cursor.execute(
                    "INSERT INTO enrollment (schedule_id,choice_id,offering_id,status) VALUES (%s,%s,%s,%s)",
                    (schedule_id, row["choice_id"], row["offering_id"],
                     "COMMITTED" if survived else "CANCELLED"),
                )
                cursor.execute(
                    "UPDATE schedule_choice SET status=%s WHERE choice_id=%s",
                    ("ENROLLED" if survived else "CANCELLED", row["choice_id"]),
                )
            cursor.execute(
                "UPDATE student_schedule SET status='FINALIZED',finalized_at=NOW() WHERE schedule_id=%s",
                (schedule_id,),
            )
        for bill in plan["bills"]:
            snapshot = {
                "term_code": term_code,
                "student_id": bill["student_id"],
                "schedule_id": bill["schedule_id"],
                "offerings": [
                    {"offering_id": offering_id,
                     "course_id": plan["offerings"][offering_id]["course_id"],
                     "title": plan["offerings"][offering_id]["title"],
                     "credits": str(plan["offerings"][offering_id]["credits"])}
                    for offering_id in bill["offering_ids"]
                ],
                "credits": bill["credits"],
                "amount": bill["amount"],
            }
            cursor.execute(
                "INSERT INTO billing_outbox "
                "(schedule_id,idempotency_key,amount,final_schedule,status) "
                "VALUES (%s,%s,%s,%s,'PENDING')",
                (bill["schedule_id"], f"registration:{term_code}:{bill['schedule_id']}",
                 bill["amount"], json.dumps(snapshot, ensure_ascii=False)),
            )
        cursor.execute(
            "UPDATE academic_term SET status='CLOSED',closed_at=NOW(),closed_by=%s WHERE term_code=%s",
            (user_id, term_code),
        )
        cursor.execute(
            "UPDATE registration_close_run SET status='SUCCEEDED',finished_at=NOW() WHERE close_run_id=%s",
            (close_run_id,),
        )
        cursor.execute(
            "INSERT INTO audit_log (user_id,action,entity_type,entity_id) "
            "VALUES (%s,'CLOSE_REGISTRATION','TERM',%s)",
            (user_id, term_code),
        )
        result = _public(plan, term)
        result["preview_only"] = False
        result["close_run_id"] = close_run_id
    return result
