"""在本机 v6 测试库准备「无人授课、少于三人、两个备选补位」演示。

仅用于隔离测试库。运行前必须已有 Git 忽略目录中的事前备份；
不会关闭选课，也不会修改课程目录。
"""

from datetime import datetime

from app.closing import preview_close
from app.config import ROOT, settings
from app.db import read_connection, transaction
from app.models import ChoiceInput
from app.professors import claim_offering
from app.schedules import get_schedule, save_draft, submit_schedule


TERM = "2026FA"
MATH_01 = "2026FA-211012-01"
MATH_02 = "2026FA-211012-02"
NO_TEACHER = "2026FA-931103-01"
ALTERNATE_2 = "2026FA-211011-01"
FULL_CLASS = "2026FA-213002-01"
SPRING_PRIMARY = (
    "2026SP-212002-01", "2026SP-211001-01",
    "2026SP-211002-01", "2026SP-941015-01",
)
SPRING_ALTERNATE = ("2026SP-213001-01", "2026SP-212002-02")
SPRING_GRADES = {"S004": ("B", "A", "B", "B"), "S005": ("B", "B", "A", "B")}


def preflight() -> dict[str, int]:
    if (settings.db_name, settings.catalog_db) != (
        "course_registration_v6_test", "course_catalog_v6_test"
    ):
        raise RuntimeError("只允许操作本机 v6 测试库")
    backup = ROOT / ".local-backups/pre-close-alternates-demo-20261013.sql"
    if not backup.is_file() or backup.stat().st_size < 30000:
        raise RuntimeError("缺少本次修改前的数据库备份")
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT status,registration_opens_at,registration_closes_at "
            "FROM academic_term WHERE term_code=%s", (TERM,)
        )
        term = cursor.fetchone()
        now = datetime.now()
        if not term or term["status"] != "OPEN" or not (
            term["registration_opens_at"] <= now <= term["registration_closes_at"]
        ):
            raise RuntimeError("2026FA 不在开放选课期")
        cursor.execute(
            "SELECT professor_id,user_id FROM professor_profile "
            "WHERE professor_id='P001' AND department_id='CS' AND status='ACTIVE'"
        )
        teacher = cursor.fetchone()
        if not teacher or not teacher["user_id"]:
            raise RuntimeError("缺少计算机系演示教师 P001")
        cursor.execute(
            "SELECT 1 FROM professor_qualification "
            "WHERE professor_id='P001' AND course_id='211012'"
        )
        if not cursor.fetchone():
            raise RuntimeError("教师一没有数学建模任教资格")
        cursor.execute(
            "SELECT offering_id,professor_id FROM teaching_assignment "
            "WHERE offering_id IN (%s,%s,%s)", (MATH_01, MATH_02, NO_TEACHER)
        )
        assigned = {row["offering_id"]: row["professor_id"] for row in cursor.fetchall()}
        if assigned.get(MATH_01) != "P001" or assigned.get(MATH_02) not in (None, "P001"):
            raise RuntimeError("数学建模教学班的教师归属已变化")
        if NO_TEACHER in assigned:
            raise RuntimeError("预留的无人授课教学班已被认领")
        cursor.execute(
            "SELECT offering_id,enrolled_count,capacity,status "
            "FROM offering_registration_state WHERE offering_id IN (%s,%s,%s,%s)",
            (MATH_01, MATH_02, NO_TEACHER, FULL_CLASS),
        )
        states = {row["offering_id"]: row for row in cursor.fetchall()}
        if any(states[offering_id]["status"] != "OPEN" for offering_id in states):
            raise RuntimeError("目标教学班已不开放")
        if states[MATH_01]["enrolled_count"] != 1 or states[FULL_CLASS]["enrolled_count"] != 10:
            raise RuntimeError("一人班或满额班的人数与预期不符")
        if states[MATH_02]["enrolled_count"] not in (0, 1, 2, 3, 4):
            raise RuntimeError("数学建模 02 班已有未知报名数据")
        cursor.execute(
            "SELECT student_id,user_id,full_name,department_id,admission_term_code "
            "FROM student_profile WHERE student_id IN ('S001','S002','S003','S004','S005')"
        )
        students = {row["student_id"]: row for row in cursor.fetchall()}
        if set(students) != {f"S{i:03d}" for i in range(1, 6)} or any(
            row["department_id"] != "CS" or row["admission_term_code"] != "2026SP"
            for row in students.values()
        ):
            raise RuntimeError("演示学生档案与预期不符")
        cursor.execute(
            "SELECT schedule_id,status FROM student_schedule "
            "WHERE student_id='S001' AND term_code=%s", (TERM,)
        )
        lead = cursor.fetchone()
        if not lead or lead["status"] != "SUBMITTED":
            raise RuntimeError("学生一的秋季课表尚未提交")
        cursor.execute(
            "SELECT choice_type,priority,offering_id FROM schedule_choice WHERE schedule_id=%s",
            (lead["schedule_id"],),
        )
        choices = {(r["choice_type"], r["priority"]): r["offering_id"] for r in cursor.fetchall()}
        if (choices.get(("PRIMARY", 2)), choices.get(("PRIMARY", 3)),
            choices.get(("ALTERNATE", 1)), choices.get(("ALTERNATE", 2))) != (
            MATH_01, NO_TEACHER, MATH_02, ALTERNATE_2
        ):
            raise RuntimeError("学生一的主选或备选志愿已变化")
        return {student_id: row["user_id"] for student_id, row in students.items()} | {
            "teacher": teacher["user_id"], "lead_schedule": lead["schedule_id"]
        }


def ensure_spring_history(student_id: str) -> None:
    """为原先只有秋季满额测试记录的陪同学生补真实结构的春季成绩。"""
    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT schedule_id,status FROM student_schedule "
            "WHERE student_id=%s AND term_code='2026SP' FOR UPDATE", (student_id,)
        )
        existing = cursor.fetchone()
        if existing:
            if existing["status"] != "FINALIZED":
                raise RuntimeError(f"{student_id} 的春季课表不是最终课表")
            cursor.execute(
                "SELECT COUNT(*) AS n FROM enrollment e "
                "JOIN schedule_choice c ON c.choice_id=e.choice_id "
                "WHERE e.schedule_id=%s AND c.choice_type='PRIMARY' "
                "AND e.status='COMPLETED' AND e.letter_grade IS NOT NULL",
                (existing["schedule_id"],),
            )
            if cursor.fetchone()["n"] != 4:
                raise RuntimeError(f"{student_id} 的春季成绩不完整")
            print(f"{student_id} 春季成绩已有，跳过")
            return
        cursor.execute(
            "INSERT INTO student_schedule "
            "(student_id,term_code,status,submitted_at,finalized_at) "
            "VALUES (%s,'2026SP','FINALIZED','2026-02-15 12:00:00','2026-03-02 12:00:00')",
            (student_id,),
        )
        schedule_id = cursor.lastrowid
        for priority, (offering_id, grade) in enumerate(
            zip(SPRING_PRIMARY, SPRING_GRADES[student_id]), 1
        ):
            cursor.execute(
                "SELECT status,capacity,enrolled_count FROM offering_registration_state "
                "WHERE offering_id=%s FOR UPDATE", (offering_id,)
            )
            state = cursor.fetchone()
            if not state or state["status"] != "COMMITTED" or state["enrolled_count"] >= state["capacity"]:
                raise RuntimeError(f"春季教学班 {offering_id} 无法补入演示学生")
            cursor.execute(
                "UPDATE offering_registration_state SET enrolled_count=enrolled_count+1 "
                "WHERE offering_id=%s", (offering_id,)
            )
            cursor.execute(
                "INSERT INTO schedule_choice "
                "(schedule_id,offering_id,term_code,choice_type,priority,status) "
                "VALUES (%s,%s,'2026SP','PRIMARY',%s,'ENROLLED')",
                (schedule_id, offering_id, priority),
            )
            cursor.execute(
                "INSERT INTO enrollment "
                "(schedule_id,choice_id,offering_id,status,letter_grade,graded_by,graded_at) "
                "VALUES (%s,%s,%s,'COMPLETED',%s,'P001','2026-06-30 12:00:00')",
                (schedule_id, cursor.lastrowid, offering_id, grade),
            )
        for priority, offering_id in enumerate(SPRING_ALTERNATE, 1):
            cursor.execute(
                "INSERT INTO schedule_choice "
                "(schedule_id,offering_id,term_code,choice_type,priority,status) "
                "VALUES (%s,%s,'2026SP','ALTERNATE',%s,'SELECTED')",
                (schedule_id, offering_id, priority),
            )
    print(f"{student_id} 春季演示课表与 4 门成绩已补齐")


def choices_for_existing(schedule: dict) -> list[ChoiceInput]:
    result = []
    for row in schedule["choices"]:
        offering_id = row["offering_id"]
        if row["choice_type"] == "PRIMARY" and row["priority"] == 4:
            if offering_id not in (NO_TEACHER, MATH_02):
                raise RuntimeError("陪同学生的第 4 主选已变化")
            offering_id = MATH_02
        result.append(ChoiceInput(
            offering_id=offering_id,
            choice_type=row["choice_type"],
            priority=row["priority"],
        ))
    return result


def choices_for_new() -> list[ChoiceInput]:
    primary = (MATH_02, "2026FA-211003-01", "2026FA-211004-01", "2026FA-211011-02")
    alternates = ("2026FA-211003-02", ALTERNATE_2)
    return [
        *(ChoiceInput(offering_id=o, choice_type="PRIMARY", priority=i)
          for i, o in enumerate(primary, 1)),
        *(ChoiceInput(offering_id=o, choice_type="ALTERNATE", priority=i)
          for i, o in enumerate(alternates, 1)),
    ]


def ensure_fall_schedule(student_id: str, user_id: int, desired: list[ChoiceInput]) -> None:
    current = get_schedule(user_id, TERM)
    wanted = {(c.choice_type, c.priority, c.offering_id) for c in desired}
    actual = {(c["choice_type"], c["priority"], c["offering_id"])
              for c in current["choices"]}
    if current["status"] == "SUBMITTED" and actual == wanted:
        print(f"{student_id} 秋季课表已提交，跳过")
        return
    if current["status"] not in ("EMPTY", "DRAFT", "SUBMITTED"):
        raise RuntimeError(f"{student_id} 秋季课表状态不适合修改：{current['status']}")
    save_draft(user_id, TERM, desired)
    submitted = submit_schedule(user_id, TERM)
    if submitted["status"] != "SUBMITTED":
        raise RuntimeError(f"{student_id} 秋季课表未成功提交")
    print(f"{student_id} 已提交数学建模 02 班")


def main() -> None:
    users = preflight()
    for student_id in SPRING_GRADES:
        ensure_spring_history(student_id)
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT professor_id FROM teaching_assignment WHERE offering_id=%s", (MATH_02,))
        assigned = cursor.fetchone()
    if not assigned:
        claim_offering(users["teacher"], TERM, MATH_02)
        print("教师一已认领数学建模 02 班")
    for student_id in ("S004", "S005"):
        schedule = get_schedule(users[student_id], TERM)
        ensure_fall_schedule(student_id, users[student_id], choices_for_existing(schedule))
    for student_id in ("S002", "S003"):
        ensure_fall_schedule(student_id, users[student_id], choices_for_new())

    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT offering_id,enrolled_count FROM offering_registration_state "
            "WHERE offering_id IN (%s,%s,%s)", (MATH_01, MATH_02, FULL_CLASS)
        )
        counts = {row["offering_id"]: row["enrolled_count"] for row in cursor.fetchall()}
        cursor.execute("SELECT status FROM academic_term WHERE term_code=%s", (TERM,))
        term_status = cursor.fetchone()["status"]
    if counts != {MATH_01: 1, MATH_02: 4, FULL_CLASS: 10} or term_status != "OPEN":
        raise RuntimeError(f"最终人数或学期状态不符：{counts}, {term_status}")
    preview = preview_close(TERM)
    reasons = {row["offering_id"]: row["reason"] for row in preview["cancelled_offerings"]}
    lead_alternates = [row for row in preview["alternate_placements"]
                       if row["schedule_id"] == users["lead_schedule"] and row["survived"]]
    if reasons.get(MATH_01) != "TOO_FEW_STUDENTS" or reasons.get(NO_TEACHER) != "NO_PROFESSOR":
        raise RuntimeError(f"截止预览的取消原因不符：{reasons}")
    if [row["offering_id"] for row in lead_alternates] != [MATH_02, ALTERNATE_2]:
        raise RuntimeError(f"学生一的两个备选未按顺序补位：{lead_alternates}")
    print("核对通过：数学建模 01 班 1 人、02 班 4 人；满额班仍 10 人")
    print("截止预览：01 班因不足 3 人取消；主选 3 因无人授课取消")
    print("截止预览：学生一备选 1（数学建模 02）与备选 2 均可补位")
    print("2026FA 仍为 OPEN；没有正式关闭选课")


if __name__ == "__main__":
    main()
