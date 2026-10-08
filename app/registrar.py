"""教务员维护学生、教师档案与教师任教资格；不写课程目录库。"""
from __future__ import annotations

from datetime import date
import secrets

from fastapi import HTTPException
from pymysql.err import IntegrityError

from .catalog import CATALOG
from .db import read_connection, transaction
from .models import ProfessorCreate, ProfessorPatch, StudentCreate, StudentPatch
from .ssn import encrypt_ssn


def _audit(cursor, user_id: int, action: str, entity_type: str, entity_id: str) -> None:
    cursor.execute(
        "INSERT INTO audit_log (user_id,action,entity_type,entity_id) VALUES (%s,%s,%s,%s)",
        (user_id, action, entity_type, entity_id),
    )


def _name(value: str) -> str:
    value = value.strip()
    if not value:
        raise HTTPException(400, "姓名不能为空")
    return value


def _birth_date(value: date) -> date:
    if value > date.today():
        raise HTTPException(400, "出生日期不能晚于今天")
    return value


def _graduation(status: str, graduation_date: date | None) -> None:
    if status == "GRADUATED":
        if not graduation_date or graduation_date > date.today():
            raise HTTPException(400, "毕业状态需要填写不晚于今天的毕业日期")
    elif graduation_date is not None:
        raise HTTPException(400, "只有毕业状态才能填写毕业日期")


def _new_id(prefix: str) -> str:
    """随机编号由系统产生，数据库主键负责最终唯一性约束。"""
    return prefix + secrets.token_hex(7).upper()


def _department_exists(cursor, department_id: str) -> None:
    cursor.execute(f"SELECT 1 FROM {CATALOG}.department WHERE department_id=%s", (department_id,))
    if not cursor.fetchone():
        raise HTTPException(400, "系别不存在于课程目录")


def catalog_options() -> dict:
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT department_id,name FROM {CATALOG}.department ORDER BY department_id")
        departments = cursor.fetchall()
        cursor.execute(
            f"SELECT course_id,title,department_id FROM {CATALOG}.course WHERE is_active=TRUE ORDER BY course_id"
        )
        courses = cursor.fetchall()
    return {"departments": departments, "courses": courses}


def students() -> list[dict]:
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT student_id,full_name,date_of_birth,status,graduation_date,"
            "ssn_encrypted IS NOT NULL AS has_ssn,"
            "user_id IS NOT NULL AS has_account FROM student_profile ORDER BY student_id LIMIT 200"
        )
        return cursor.fetchall()


def create_student(user_id: int, body: StudentCreate) -> dict:
    name = _name(body.full_name)
    birth = _birth_date(body.date_of_birth)
    _graduation(body.status, body.graduation_date)
    encrypted = encrypt_ssn(body.ssn)
    for _ in range(3):
        student_id = _new_id("S")
        try:
            with transaction() as connection, connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO student_profile "
                    "(student_id,full_name,date_of_birth,ssn_encrypted,status,graduation_date) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (student_id, name, birth, encrypted, body.status, body.graduation_date),
                )
                _audit(cursor, user_id, "CREATE_STUDENT", "STUDENT", student_id)
        except IntegrityError as error:
            if error.args[0] == 1062:
                continue
            raise
        return student(student_id)
    raise HTTPException(503, "暂时无法生成唯一学号，请重试")


def student(student_id: str) -> dict:
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT student_id,full_name,date_of_birth,status,graduation_date,"
            "ssn_encrypted IS NOT NULL AS has_ssn,"
            "user_id IS NOT NULL AS has_account FROM student_profile WHERE student_id=%s",
            (student_id,),
        )
        row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "学生不存在")
    return row


def update_student(user_id: int, student_id: str, body: StudentPatch) -> dict:
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "没有需要修改的字段")
    for required in ("full_name", "date_of_birth", "status"):
        if required in updates and updates[required] is None:
            raise HTTPException(400, f"{required} 不能为空")
    if "full_name" in updates:
        updates["full_name"] = _name(updates["full_name"])
    if "date_of_birth" in updates:
        updates["date_of_birth"] = _birth_date(updates["date_of_birth"])
    if "ssn" in updates:
        updates["ssn_encrypted"] = encrypt_ssn(updates.pop("ssn"))
    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT status,graduation_date FROM student_profile WHERE student_id=%s FOR UPDATE",
            (student_id,),
        )
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(404, "学生不存在")
        final_status = updates.get("status", existing["status"])
        final_graduation = updates.get("graduation_date", existing["graduation_date"])
        _graduation(final_status, final_graduation)
        if existing["status"] == "ACTIVE" and final_status != "ACTIVE":
            cursor.execute(
                "SELECT 1 FROM student_schedule s JOIN academic_term t ON t.term_code=s.term_code "
                "WHERE s.student_id=%s AND s.status='SUBMITTED' AND t.status='OPEN' LIMIT 1",
                (student_id,),
            )
            if cursor.fetchone():
                raise HTTPException(409, "该学生有开放学期的已提交课表，请先处理课表")
        assignments = ",".join(f"{field}=%s" for field in updates)
        cursor.execute(
            f"UPDATE student_profile SET {assignments} WHERE student_id=%s",
            (*updates.values(), student_id),
        )
        _audit(cursor, user_id, "UPDATE_STUDENT", "STUDENT", student_id)
    return student(student_id)


def delete_student(user_id: int, student_id: str) -> dict:
    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT user_id FROM student_profile WHERE student_id=%s FOR UPDATE", (student_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "学生不存在")
        if row["user_id"] is not None:
            raise HTTPException(409, "该学生已绑定登录账号，请保留档案并改为停用")
        cursor.execute("SELECT 1 FROM student_schedule WHERE student_id=%s LIMIT 1", (student_id,))
        if cursor.fetchone():
            raise HTTPException(409, "该学生已有课表历史，不能删除；请改为停用")
        cursor.execute("DELETE FROM student_profile WHERE student_id=%s", (student_id,))
        _audit(cursor, user_id, "DELETE_STUDENT", "STUDENT", student_id)
    return {"deleted": True, "student_id": student_id}


def professors() -> list[dict]:
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT professor_id,full_name,date_of_birth,department_id,status,"
            "ssn_encrypted IS NOT NULL AS has_ssn,"
            "user_id IS NOT NULL AS has_account FROM professor_profile ORDER BY professor_id LIMIT 200"
        )
        rows = cursor.fetchall()
        cursor.execute(
            "SELECT professor_id,course_id FROM professor_qualification ORDER BY professor_id,course_id"
        )
        qualifications = cursor.fetchall()
    by_professor: dict[str, list[str]] = {}
    for qualification in qualifications:
        by_professor.setdefault(qualification["professor_id"], []).append(qualification["course_id"])
    return [{**row, "qualifications": by_professor.get(row["professor_id"], [])} for row in rows]


def professor(professor_id: str) -> dict:
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT professor_id,full_name,date_of_birth,department_id,status,"
            "ssn_encrypted IS NOT NULL AS has_ssn,"
            "user_id IS NOT NULL AS has_account FROM professor_profile WHERE professor_id=%s",
            (professor_id,),
        )
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "SELECT course_id FROM professor_qualification WHERE professor_id=%s ORDER BY course_id",
                (professor_id,),
            )
            row["qualifications"] = [r["course_id"] for r in cursor.fetchall()]
    if not row:
        raise HTTPException(404, "教师不存在")
    return row


def create_professor(user_id: int, body: ProfessorCreate) -> dict:
    name = _name(body.full_name)
    birth = _birth_date(body.date_of_birth)
    encrypted = encrypt_ssn(body.ssn)
    for _ in range(3):
        professor_id = _new_id("P")
        try:
            with transaction() as connection, connection.cursor() as cursor:
                _department_exists(cursor, body.department_id)
                cursor.execute(
                    "INSERT INTO professor_profile "
                    "(professor_id,full_name,date_of_birth,ssn_encrypted,status,department_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (professor_id, name, birth, encrypted, body.status, body.department_id),
                )
                _audit(cursor, user_id, "CREATE_PROFESSOR", "PROFESSOR", professor_id)
        except IntegrityError as error:
            if error.args[0] == 1062:
                continue
            raise
        return professor(professor_id)
    raise HTTPException(503, "暂时无法生成唯一教师编号，请重试")


def update_professor(user_id: int, professor_id: str, body: ProfessorPatch) -> dict:
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "没有需要修改的字段")
    if any(value is None for field, value in updates.items() if field != "ssn"):
        raise HTTPException(400, "教师字段不能为空")
    if "full_name" in updates:
        updates["full_name"] = _name(updates["full_name"])
    if "date_of_birth" in updates:
        updates["date_of_birth"] = _birth_date(updates["date_of_birth"])
    if "ssn" in updates:
        updates["ssn_encrypted"] = encrypt_ssn(updates.pop("ssn"))
    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT status FROM professor_profile WHERE professor_id=%s FOR UPDATE",
            (professor_id,),
        )
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(404, "教师不存在")
        if "department_id" in updates:
            _department_exists(cursor, updates["department_id"])
        if existing["status"] == "ACTIVE" and updates.get("status") == "INACTIVE":
            cursor.execute(
                "SELECT 1 FROM teaching_assignment a "
                "JOIN offering_registration_state s ON s.offering_id=a.offering_id "
                "JOIN academic_term t ON t.term_code=s.term_code "
                "WHERE a.professor_id=%s AND t.status IN ('DRAFT','OPEN','CLOSING') LIMIT 1",
                (professor_id,),
            )
            if cursor.fetchone():
                raise HTTPException(409, "教师仍认领着未结束学期的教学班，请先退出认领")
        assignments = ",".join(f"{field}=%s" for field in updates)
        cursor.execute(
            f"UPDATE professor_profile SET {assignments} WHERE professor_id=%s",
            (*updates.values(), professor_id),
        )
        _audit(cursor, user_id, "UPDATE_PROFESSOR", "PROFESSOR", professor_id)
    return professor(professor_id)


def delete_professor(user_id: int, professor_id: str) -> dict:
    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT user_id FROM professor_profile WHERE professor_id=%s FOR UPDATE", (professor_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "教师不存在")
        if row["user_id"] is not None:
            raise HTTPException(409, "该教师已绑定登录账号，请保留档案并改为停用")
        cursor.execute("SELECT 1 FROM teaching_assignment WHERE professor_id=%s LIMIT 1", (professor_id,))
        if cursor.fetchone():
            raise HTTPException(409, "该教师有任教记录，不能删除；请改为停用")
        cursor.execute("SELECT 1 FROM grade_change_log WHERE professor_id=%s LIMIT 1", (professor_id,))
        if cursor.fetchone():
            raise HTTPException(409, "该教师有成绩修改记录，不能删除；请改为停用")
        cursor.execute("SELECT 1 FROM enrollment WHERE graded_by=%s LIMIT 1", (professor_id,))
        if cursor.fetchone():
            raise HTTPException(409, "该教师有成绩记录，不能删除；请改为停用")
        cursor.execute("DELETE FROM professor_qualification WHERE professor_id=%s", (professor_id,))
        cursor.execute("DELETE FROM professor_profile WHERE professor_id=%s", (professor_id,))
        _audit(cursor, user_id, "DELETE_PROFESSOR", "PROFESSOR", professor_id)
    return {"deleted": True, "professor_id": professor_id}


def add_qualification(user_id: int, professor_id: str, course_id: str) -> dict:
    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM professor_profile WHERE professor_id=%s FOR UPDATE",
            (professor_id,),
        )
        if not cursor.fetchone():
            raise HTTPException(404, "教师不存在")
        cursor.execute(f"SELECT 1 FROM {CATALOG}.course WHERE course_id=%s AND is_active=TRUE", (course_id,))
        if not cursor.fetchone():
            raise HTTPException(400, "课程不存在或已停用")
        cursor.execute(
            "INSERT INTO professor_qualification (professor_id,course_id) "
            "VALUES (%s,%s) ON DUPLICATE KEY UPDATE course_id=course_id",
            (professor_id, course_id),
        )
        _audit(cursor, user_id, "ADD_QUALIFICATION", "PROFESSOR", professor_id)
    return professor(professor_id)


def remove_qualification(user_id: int, professor_id: str, course_id: str) -> dict:
    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM professor_profile WHERE professor_id=%s FOR UPDATE",
            (professor_id,),
        )
        if not cursor.fetchone():
            raise HTTPException(404, "教师不存在")
        cursor.execute(
            f"SELECT 1 FROM teaching_assignment a "
            f"JOIN offering_registration_state s ON s.offering_id=a.offering_id "
            f"JOIN academic_term t ON t.term_code=s.term_code "
            f"JOIN {CATALOG}.course_offering o ON o.offering_id=a.offering_id "
            "WHERE a.professor_id=%s AND o.course_id=%s "
            "AND t.status IN ('DRAFT','OPEN','CLOSING') LIMIT 1",
            (professor_id, course_id),
        )
        if cursor.fetchone():
            raise HTTPException(409, "教师仍在教授该课程的教学班，不能移除资格")
        cursor.execute(
            "DELETE FROM professor_qualification WHERE professor_id=%s AND course_id=%s",
            (professor_id, course_id),
        )
        if cursor.rowcount != 1:
            raise HTTPException(404, "任教资格不存在")
        _audit(cursor, user_id, "REMOVE_QUALIFICATION", "PROFESSOR", professor_id)
    return professor(professor_id)
