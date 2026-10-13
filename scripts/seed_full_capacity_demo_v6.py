"""只在本机 v6 测试库创建 S004–S013，并正常提交十份秋季课表。

先由管理员执行 database/20_expand_cs_curriculum_v6_test.sql；
本脚本使用现有建档、草稿、提交业务函数，绝不直接改名额计数。
"""

from datetime import date, datetime

from app.catalog import CATALOG
from app.config import ROOT, settings
from app.db import read_connection, transaction
from app.models import ChoiceInput, StudentCreate
from app.registrar import create_student
from app.schedules import get_schedule, save_draft, submit_schedule


TERM = "2026FA"
FULL_OFFERING = "2026FA-213002-01"
OTHER_PRIMARY = ("2026FA-211003-01", "2026FA-211004-01",
                 "2026FA-211011-01", "2026FA-931103-01")
ALTERNATE = ("2026FA-211003-02", "2026FA-211011-02")
NAMES = ("学生四", "学生五", "学生六", "学生七", "学生八", "学生九",
         "学生十", "学生十一", "学生十二", "学生十三")

def choices_for_student(number: int) -> list[ChoiceInput]:
    # 其他四门轮流略去一门，各班最终只有 7–8 人；只有测试班达到 10/10。
    other = [offering_id for index, offering_id in enumerate(OTHER_PRIMARY)
             if index != (number - 4) % len(OTHER_PRIMARY)]
    return [
        *(ChoiceInput(offering_id=offering_id, choice_type="PRIMARY", priority=index)
          for index, offering_id in enumerate((FULL_OFFERING, *other), 1)),
        *(ChoiceInput(offering_id=offering_id, choice_type="ALTERNATE", priority=index)
          for index, offering_id in enumerate(ALTERNATE, 1)),
    ]


def preflight() -> int:
    if (settings.db_name, settings.catalog_db) != (
        "course_registration_v6_test", "course_catalog_v6_test"
    ):
        raise RuntimeError("只允许对本机 v6 测试库添加满额演示数据")
    backup = ROOT / ".local-backups/pre-expanded-curriculum-full-capacity-20261013.sql"
    if not backup.is_file() or backup.stat().st_size < 10000:
        raise RuntimeError("没有找到完整的事前备份")
    if len(settings.initial_account_password) < 10:
        raise RuntimeError("本机 .env 需要至少 10 位统一初始密码")
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT user_id FROM user_account WHERE role='REGISTRAR' AND is_active=TRUE "
            "ORDER BY user_id LIMIT 1"
        )
        registrar = cursor.fetchone()
        if not registrar:
            raise RuntimeError("缺少可用教务账号")
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
            f"SELECT o.offering_id,o.capacity,c.department_id "
            f"FROM {CATALOG}.course_offering o "
            f"JOIN {CATALOG}.course c ON c.course_id=o.course_id "
            f"WHERE o.offering_id IN ({','.join(['%s'] * len((FULL_OFFERING, *OTHER_PRIMARY, *ALTERNATE)))}) "
            f"AND o.term_code=%s", (FULL_OFFERING, *OTHER_PRIMARY, *ALTERNATE, TERM)
        )
        offerings = {row["offering_id"]: row for row in cursor.fetchall()}
        if set(offerings) != set((FULL_OFFERING, *OTHER_PRIMARY, *ALTERNATE)) or any(
            row["capacity"] != 10 or row["department_id"] != "CS"
            for row in offerings.values()
        ):
            raise RuntimeError("目录教学班缺失、容量或院系不符")
        cursor.execute(
            "SELECT offering_id,enrolled_count,status FROM offering_registration_state "
            "WHERE offering_id IN (" + ",".join(["%s"] * len((FULL_OFFERING, *OTHER_PRIMARY, *ALTERNATE))) + ")",
            (FULL_OFFERING, *OTHER_PRIMARY, *ALTERNATE),
        )
        states = cursor.fetchall()
        if any(row["status"] != "OPEN" for row in states):
            raise RuntimeError("已有教学班关闭；不能继续准备满额数据")
        cursor.execute(
            "SELECT student_id,full_name,user_id,department_id,admission_term_code "
            "FROM student_profile WHERE student_id IN (" + ",".join(["%s"] * 10) + ")",
            tuple(f"S{number:03d}" for number in range(4, 14)),
        )
        existing = {row["student_id"]: row for row in cursor.fetchall()}
        for number, name in enumerate(NAMES, 4):
            row = existing.get(f"S{number:03d}")
            if row and (row["full_name"], row["department_id"], row["admission_term_code"]) != (
                name, "CS", "2026SP"
            ):
                raise RuntimeError(f"S{number:03d} 已属于其他演示数据，停止")
        if not existing and any(row["enrolled_count"] for row in states):
            raise RuntimeError("目标教学班已有其他人报名，停止以免覆盖演示场景")
        return registrar["user_id"]


def main() -> None:
    registrar_id = preflight()
    # 让演示教师可在开放的秋季认领新增课程；不自动替他认领。
    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM professor_profile WHERE professor_id='P001' "
            "AND department_id='CS' AND status='ACTIVE'"
        )
        if not cursor.fetchone():
            raise RuntimeError("缺少计算机系演示教师 P001")
        cursor.executemany(
            "INSERT IGNORE INTO professor_qualification (professor_id,course_id) "
            "VALUES ('P001',%s)",
            [(course_id,) for course_id in ("931102", "LD2001", "213002", "931103")],
        )
    for number, name in enumerate(NAMES, 4):
        student_id = f"S{number:03d}"
        with read_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT user_id FROM student_profile WHERE student_id=%s", (student_id,))
            row = cursor.fetchone()
        if row is None:
            created = create_student(
                registrar_id,
                StudentCreate(
                    full_name=name,
                    date_of_birth=date(2006, 1, number),
                    department_id="CS",
                    admission_term_code="2026SP",
                    ssn=f"90000{number:04d}",  # SSA 不分配 900 前缀；仅作虚构测试号。
                ),
            )
            if created["student_id"] != student_id:
                raise RuntimeError(f"新学号是 {created['student_id']}，预期 {student_id}")
            with read_connection() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT user_id FROM student_profile WHERE student_id=%s", (student_id,))
                row = cursor.fetchone()
        user_id = row["user_id"]
        schedule = get_schedule(user_id, TERM)
        choices = choices_for_student(number)
        wanted = {(choice.choice_type, choice.priority, choice.offering_id) for choice in choices}
        current = {(choice["choice_type"], choice["priority"], choice["offering_id"])
                   for choice in schedule["choices"]}
        if schedule["status"] == "SUBMITTED" and current == wanted:
            print(f"{student_id} 已提交，跳过")
            continue
        if schedule["status"] not in ("EMPTY", "DRAFT", "SUBMITTED"):
            raise RuntimeError(f"{student_id} 的课表状态 {schedule['status']} 不适合重试")
        save_draft(user_id, TERM, choices)
        submitted = submit_schedule(user_id, TERM)
        if submitted["status"] != "SUBMITTED":
            raise RuntimeError(f"{student_id} 提交后状态异常")
        print(f"{student_id} {name}：4 主选 + 2 备选，已提交")

    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT capacity,enrolled_count,status FROM offering_registration_state "
            "WHERE offering_id=%s", (FULL_OFFERING,)
        )
        state = cursor.fetchone()
        cursor.execute(
            "SELECT COUNT(*) AS n FROM enrollment WHERE offering_id=%s AND status='ENROLLED'",
            (FULL_OFFERING,),
        )
        count = cursor.fetchone()["n"]
    if not state or (state["capacity"], state["enrolled_count"], count) != (10, 10, 10):
        raise RuntimeError(f"满额计数不一致：{state}，实际报名 {count}")
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT offering_id,enrolled_count FROM offering_registration_state "
            "WHERE offering_id IN (" + ",".join(["%s"] * len(OTHER_PRIMARY)) + ")",
            OTHER_PRIMARY,
        )
        other_counts = {row["offering_id"]: row["enrolled_count"] for row in cursor.fetchall()}
    if set(other_counts) != set(OTHER_PRIMARY) or any(count >= 10 for count in other_counts.values()):
        raise RuntimeError(f"其他演示班意外满额：{other_counts}")
    print(f"{FULL_OFFERING}：容量 10，已报名 10，剩余 0")
    print(f"其他主选班：{other_counts}")


if __name__ == "__main__":
    main()
