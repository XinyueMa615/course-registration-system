"""仅在本机 v6 测试库准备两名计算机系教师及同班认领冲突场景。

使用现有教务建档、资格授权和教师认领业务函数；不修改课程目录。
"""

from datetime import date, datetime

from fastapi import HTTPException

from app.config import ROOT, settings
from app.db import read_connection
from app.models import ProfessorCreate
from app.professors import claim_offering
from app.registrar import add_qualification, create_professor


TERM = "2026FA"
TEACHERS = (
    ("P004", "教师二", "2026FA-211003-01"),
    ("P005", "教师三", "2026FA-211004-01"),
)
COURSES = ("211003", "211004")


def inspect() -> tuple[int, dict]:
    if (settings.db_name, settings.catalog_db) != (
        "course_registration_v6_test", "course_catalog_v6_test"
    ):
        raise RuntimeError("只允许操作本机 v6 演示测试库")
    backup = ROOT / ".local-backups/pre-two-cs-teachers-20261013.sql"
    if not backup.is_file() or backup.stat().st_size < 10000:
        raise RuntimeError("未找到建档前的数据库备份")
    if len(settings.initial_account_password) < 10:
        raise RuntimeError("本机 .env 未配置至少 10 位的统一初始密码")
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT user_id FROM user_account WHERE role='REGISTRAR' "
            "AND is_active=TRUE ORDER BY user_id LIMIT 1"
        )
        registrar = cursor.fetchone()
        if registrar is None:
            raise RuntimeError("没有可用教务账号")
        cursor.execute(
            "SELECT status,registration_opens_at,registration_closes_at "
            "FROM academic_term WHERE term_code=%s", (TERM,)
        )
        term = cursor.fetchone()
        now = datetime.now()
        if not term or term["status"] != "OPEN" or not (
            term["registration_opens_at"] <= now <= term["registration_closes_at"]
        ):
            raise RuntimeError("2026FA 已不在教师认领开放期")
        cursor.execute(
            "SELECT p.professor_id,p.full_name,p.department_id,p.status,p.user_id,u.username "
            "FROM professor_profile p LEFT JOIN user_account u ON u.user_id=p.user_id "
            "WHERE p.professor_id IN ('P004','P005')"
        )
        existing = {row["professor_id"]: row for row in cursor.fetchall()}
        for professor_id, name, _offering_id in TEACHERS:
            row = existing.get(professor_id)
            if row and (row["full_name"], row["department_id"], row["status"], row["username"]) != (
                name, "CS", "ACTIVE", professor_id.lower()
            ):
                raise RuntimeError(f"{professor_id} 已用于其他教师，停止")
        cursor.execute(
            "SELECT offering_id,professor_id FROM teaching_assignment "
            "WHERE offering_id IN ('2026FA-211003-01','2026FA-211004-01')"
        )
        assigned = {row["offering_id"]: row["professor_id"] for row in cursor.fetchall()}
        for professor_id, _name, offering_id in TEACHERS:
            if offering_id in assigned and assigned[offering_id] != professor_id:
                raise RuntimeError(f"{offering_id} 已被 {assigned[offering_id]} 认领，停止")
        return registrar["user_id"], existing


def main() -> None:
    registrar_id, existing = inspect()
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT professor_id,course_id FROM professor_qualification "
            "WHERE professor_id IN ('P004','P005') AND course_id IN ('211003','211004')"
        )
        qualifications = {(row["professor_id"], row["course_id"]) for row in cursor.fetchall()}
    for number, (professor_id, name, _offering_id) in enumerate(TEACHERS, 4):
        if professor_id not in existing:
            created = create_professor(
                registrar_id,
                ProfessorCreate(
                    full_name=name,
                    date_of_birth=date(1980 + number - 4, 1, number),
                    department_id="CS",
                    ssn=f"9000001{number:02d}",  # 虚构号码，900 前缀不用于真实 SSN。
                ),
            )
            if created["professor_id"] != professor_id:
                raise RuntimeError(f"新增编号 {created['professor_id']}，不是预期 {professor_id}")
            print(f"已建档：{professor_id} {name}，登录名 {created['username']}")
        else:
            print(f"已有档案：{professor_id} {name}")
        for course_id in COURSES:
            if (professor_id, course_id) not in qualifications:
                add_qualification(registrar_id, professor_id, course_id)

    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT professor_id,user_id FROM professor_profile WHERE professor_id IN ('P004','P005')"
        )
        user_ids = {row["professor_id"]: row["user_id"] for row in cursor.fetchall()}
        cursor.execute(
            "SELECT offering_id,professor_id FROM teaching_assignment "
            "WHERE offering_id IN ('2026FA-211003-01','2026FA-211004-01')"
        )
        assigned = {row["offering_id"]: row["professor_id"] for row in cursor.fetchall()}

    for professor_id, name, offering_id in TEACHERS:
        if offering_id not in assigned:
            claim_offering(user_ids[professor_id], TERM, offering_id)
            print(f"已认领：{name} → {offering_id}")
        else:
            print(f"已认领，跳过：{name} → {offering_id}")

    # 交叉认领应被明确拒绝，而且不能改变原先的授课教师。
    for professor_id, name, _own_offering in TEACHERS:
        other_offering = next(offering_id for owner_id, _n, offering_id in TEACHERS
                              if owner_id != professor_id)
        try:
            claim_offering(user_ids[professor_id], TERM, other_offering)
        except HTTPException as error:
            if error.status_code != 409 or error.detail != "该教学班已有教师认领":
                raise RuntimeError(f"{name} 的冲突提示不正确：{error.detail}") from error
            print(f"验证通过：{name} 认领 {other_offering} → {error.detail}")
        else:
            raise RuntimeError(f"错误：{name} 认领了另一教师的教学班")

    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT offering_id,professor_id FROM teaching_assignment "
            "WHERE offering_id IN ('2026FA-211003-01','2026FA-211004-01')"
        )
        final = {row["offering_id"]: row["professor_id"] for row in cursor.fetchall()}
    expected = {offering_id: professor_id for professor_id, _name, offering_id in TEACHERS}
    if final != expected:
        raise RuntimeError(f"认领归属异常：{final}")
    print("两个教学班的原认领教师均未被覆盖")


if __name__ == "__main__":
    main()
