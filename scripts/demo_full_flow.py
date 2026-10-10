"""在当前本地数据库创建一套明确标记的完整演示数据。

必须显式传入 --confirm-live-demo，并通过 DEMO_DB_ADMIN_PASSWORD 提供本机
MySQL 管理员密码。脚本不修改 2026FA，不删除用户数据。
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from decimal import Decimal
import json
import os

import pymysql
from fastapi import HTTPException

from app.billing import dispatch_due
from app.closing import close_registration, preview_close
from app.config import settings
from app.db import read_connection, transaction
from app.grades import grade_offerings, report_card, roster, set_grade
from app.main import change_password, login
from app.models import (
    ChoiceInput,
    LoginRequest,
    PasswordChange,
    ProfessorCreate,
    ScheduleInput,
    StudentCreate,
    TermCreate,
)
from app.professors import claim_offering, current_roster
from app.registrar import add_qualification, create_professor, create_student
from app.schedules import save_draft, submit_schedule
from app.security import hash_password
from app.terms import complete_term, create_term, open_term


TERM_CODE = "DEMO25"
REGISTRAR_USERNAME = "demo_registrar"
REGISTRAR_PASSWORD = "Course@2026"
TEACHER_PASSWORD = "TeacherDemo@2026"
STUDENT_PASSWORD = "StudentDemo@2026"


def _account_id(username: str) -> int:
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT user_id FROM user_account WHERE username=%s", (username,))
        row = cursor.fetchone()
    if not row:
        raise RuntimeError(f"账号 {username} 不存在")
    return row["user_id"]


def _ensure_absent() -> None:
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM academic_term WHERE term_code=%s", (TERM_CODE,))
        if cursor.fetchone():
            raise RuntimeError(f"演示学期 {TERM_CODE} 已存在，为避免覆盖数据已停止")


def _registrar() -> int:
    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT user_id FROM user_account WHERE username=%s FOR UPDATE", (REGISTRAR_USERNAME,))
        row = cursor.fetchone()
        if row:
            raise RuntimeError(f"演示账号 {REGISTRAR_USERNAME} 已存在，为避免覆盖已停止")
        cursor.execute(
            "INSERT INTO user_account (username,password_hash,role) VALUES (%s,%s,'REGISTRAR')",
            (REGISTRAR_USERNAME, hash_password(REGISTRAR_PASSWORD)),
        )
        return cursor.lastrowid


def _install_catalog(admin_password: str) -> dict[str, str]:
    offerings = {
        "CS101": f"{TERM_CODE}-CS101",
        "CS302": f"{TERM_CODE}-CS302",
        "MA101": f"{TERM_CODE}-MA101",
        "AR101": f"{TERM_CODE}-AR101",
        "AR102": f"{TERM_CODE}-AR102",
        "CS201": f"{TERM_CODE}-CS201",
    }
    connection = pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=os.getenv("DEMO_DB_ADMIN_USER", "root"),
        password=admin_password,
        database=settings.catalog_db,
        charset="utf8mb4",
        autocommit=False,
    )
    try:
        with connection.cursor() as cursor:
            for index, (course_id, offering_id) in enumerate(offerings.items(), start=1):
                cursor.execute(
                    "INSERT INTO course_offering "
                    "(offering_id,course_id,term_code,section_code,capacity) "
                    "VALUES (%s,%s,%s,'01',10)",
                    (offering_id, course_id, TERM_CODE),
                )
                cursor.execute(
                    "INSERT INTO offering_meeting "
                    "(offering_id,weekday,start_period,end_period,building,room_number) "
                    "VALUES (%s,%s,1,2,'演示楼',%s)",
                    (offering_id, index, str(100 + index)),
                )
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
    return offerings


def _change_initial_password(user_id: int, initial: str, new_password: str, username: str) -> None:
    before = login(LoginRequest(username=username, password=initial))
    if not before["must_change_password"]:
        raise RuntimeError(f"{username} 应使用必须修改的初始密码")
    change_password(
        PasswordChange(current_password=initial, new_password=new_password),
        {"user_id": user_id},
    )
    after = login(LoginRequest(username=username, password=new_password))
    if after["must_change_password"]:
        raise RuntimeError(f"{username} 修改密码后仍被标记为初始密码")


def run(admin_password: str) -> dict:
    _ensure_absent()
    registrar_id = _registrar()
    login(LoginRequest(username=REGISTRAR_USERNAME, password=REGISTRAR_PASSWORD))

    now = datetime.now()
    create_term(registrar_id, TermCreate(
        term_code=TERM_CODE,
        year=2025,
        semester="WINTER",
        registration_opens_at=now - timedelta(days=1),
        registration_closes_at=now + timedelta(days=1),
        tuition_per_credit=Decimal("500.00"),
    ))
    offerings = _install_catalog(admin_password)
    open_term(registrar_id, TERM_CODE)

    teacher = create_professor(registrar_id, ProfessorCreate(
        full_name="完整流程演示教师",
        date_of_birth=date(1985, 5, 20),
        department_id="CS",
        ssn="000-55-6001",
    ))
    teacher_id = _account_id(teacher["username"])
    _change_initial_password(
        teacher_id, teacher["temporary_password"], TEACHER_PASSWORD, teacher["username"]
    )
    for course_id in ("CS101", "CS302", "MA101", "AR102", "CS201"):
        add_qualification(registrar_id, teacher["professor_id"], course_id)
        claim_offering(teacher_id, TERM_CODE, offerings[course_id])
    # AR101 故意不分配教师，用于演示截止时取消和备选补位。

    students = []
    choices = [
        ChoiceInput(offering_id=offerings["CS101"], choice_type="PRIMARY", priority=1),
        ChoiceInput(offering_id=offerings["CS302"], choice_type="PRIMARY", priority=2),
        ChoiceInput(offering_id=offerings["MA101"], choice_type="PRIMARY", priority=3),
        ChoiceInput(offering_id=offerings["AR101"], choice_type="PRIMARY", priority=4),
        ChoiceInput(offering_id=offerings["AR102"], choice_type="ALTERNATE", priority=1),
        ChoiceInput(offering_id=offerings["CS201"], choice_type="ALTERNATE", priority=2),
    ]
    for index in range(1, 5):
        created = create_student(registrar_id, StudentCreate(
            full_name=f"完整流程演示学生{index}",
            date_of_birth=date(2005, index, 10),
            ssn=f"000-66-{7000 + index:04d}",
        ))
        user_id = _account_id(created["username"])
        _change_initial_password(
            user_id, created["temporary_password"], STUDENT_PASSWORD, created["username"]
        )
        save_draft(user_id, TERM_CODE, choices)
        submitted = submit_schedule(user_id, TERM_CODE)
        if submitted["status"] != "SUBMITTED":
            raise RuntimeError("课表未成功提交")
        students.append({**created, "user_id": user_id})

    roster_before_close = current_roster(teacher_id, TERM_CODE, offerings["CS101"])
    preview = preview_close(TERM_CODE)
    if len(roster_before_close["students"]) != 4 or preview["submitted_schedules"] != 4:
        raise RuntimeError("演示名单或截止预览不完整")

    # 仅对演示学期模拟“时间已到”，不修改 2026FA。
    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute(
            "UPDATE academic_term SET registration_closes_at=%s WHERE term_code=%s",
            (now - timedelta(seconds=1), TERM_CODE),
        )
    close_result = close_registration(registrar_id, TERM_CODE)
    billing = dispatch_due(limit=20, term_code=TERM_CODE)
    complete_term(registrar_id, TERM_CODE)

    grade_values = ["A", "B", "C", "D"]
    graded = 0
    for offering in grade_offerings(teacher_id)["offerings"]:
        class_roster = roster(teacher_id, TERM_CODE, offering["offering_id"])
        for index, enrollment in enumerate(class_roster["students"]):
            set_grade(
                teacher_id,
                TERM_CODE,
                offering["offering_id"],
                enrollment["enrollment_id"],
                grade_values[index % len(grade_values)],
            )
            graded += 1

    cards = [report_card(student["user_id"]) for student in students]
    if any(len(card["courses"]) != 4 for card in cards):
        raise RuntimeError("学生成绩单课程数不正确")

    return {
        "term": TERM_CODE,
        "registrar": {"username": REGISTRAR_USERNAME, "password": REGISTRAR_PASSWORD},
        "teacher": {
            "professor_id": teacher["professor_id"],
            "username": teacher["username"],
            "password": TEACHER_PASSWORD,
        },
        "students": [
            {"student_id": row["student_id"], "username": row["username"], "password": STUDENT_PASSWORD}
            for row in students
        ],
        "preview": preview,
        "close": close_result,
        "billing": billing,
        "grades_recorded": graded,
        "report_cards": cards,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="创建一套可在三个端口查看的完整演示流程")
    parser.add_argument("--confirm-live-demo", action="store_true")
    args = parser.parse_args()
    if not args.confirm_live_demo:
        parser.error("必须显式传入 --confirm-live-demo")
    admin_password = os.getenv("DEMO_DB_ADMIN_PASSWORD", "")
    if not admin_password:
        parser.error("请通过 DEMO_DB_ADMIN_PASSWORD 提供 MySQL 管理员密码")
    try:
        result = run(admin_password)
    except (HTTPException, RuntimeError) as error:
        detail = error.detail if isinstance(error, HTTPException) else str(error)
        raise SystemExit(f"演示创建失败：{detail}") from None
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
