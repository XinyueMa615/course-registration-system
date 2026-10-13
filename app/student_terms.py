"""学生入学学期、年级和选课学期边界。"""
from __future__ import annotations

from datetime import date

from fastapi import HTTPException

from .curriculum import allowed_courses


_SEASON_ORDER = {"SPRING": 0, "SUMMER": 1, "FALL": 2, "WINTER": 3}


def term_position(year: int, semester: str) -> tuple[int, int]:
    return year, _SEASON_ORDER[semester]


def grade_year(admission_year: int | None, admission_semester: str | None,
               *, today: date | None = None) -> int | None:
    """秋季开始新学年；春季入学属于此前秋季开始的学年。"""
    if admission_year is None or admission_semester is None:
        return None
    today = today or date.today()
    if today.year < admission_year or (
        today.year == admission_year and admission_semester == "FALL" and today.month < 8
    ):
        return 0
    current_school_year = today.year if today.month >= 8 else today.year - 1
    admission_school_year = admission_year if admission_semester in ("FALL", "WINTER") else admission_year - 1
    return max(0, current_school_year - admission_school_year + 1)


def grade_label(year: int | None) -> str:
    if year is None:
        return "待补录入学学期"
    if year == 0:
        return "尚未入学"
    return f"{year}年级"


def grade_in_term(admission_year: int | None, admission_semester: str | None,
                  target_year: int, target_semester: str) -> int | None:
    """按目标学期计算年级；春季属于上一年秋季开始的学年。"""
    if admission_year is None or admission_semester is None:
        return None
    start = admission_year - (admission_semester in ("SPRING", "SUMMER"))
    target = target_year - (target_semester in ("SPRING", "SUMMER"))
    return max(0, target - start + 1)


def require_curriculum_choices(cursor, student_id: str, term_code: str,
                               offerings: dict[str, dict]) -> None:
    """新选课必须属于学生院系在目标学期的年级计划；历史课表只读不受影响。"""
    if not offerings:
        return
    cursor.execute(
        "SELECT s.department_id,a.year AS admission_year,a.semester AS admission_semester,"
        "t.year AS target_year,t.semester AS target_semester "
        "FROM student_profile s "
        "LEFT JOIN academic_term a ON a.term_code=s.admission_term_code "
        "JOIN academic_term t ON t.term_code=%s WHERE s.student_id=%s",
        (term_code, student_id),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(403, "学生档案或选课学期不存在")
    year = grade_in_term(row["admission_year"], row["admission_semester"],
                         row["target_year"], row["target_semester"])
    allowed = allowed_courses(term_code, row["department_id"], year)
    if allowed is None:
        return
    for offering_id, offering in offerings.items():
        if offering["course_id"] not in allowed:
            raise HTTPException(409, f"{offering_id} 不属于你在 {term_code} 的{grade_label(year)}培养方案，不能选课")


def require_admitted_term(cursor, student_id: str, term_code: str) -> None:
    """旧学生未补录入学学期时保持原行为；新学生禁止提前选课。"""
    cursor.execute(
        "SELECT start.year AS admission_year,start.semester AS admission_semester,"
        "target.year AS target_year,target.semester AS target_semester "
        "FROM student_profile s "
        "LEFT JOIN academic_term start ON start.term_code=s.admission_term_code "
        "JOIN academic_term target ON target.term_code=%s "
        "WHERE s.student_id=%s",
        (term_code, student_id),
    )
    row = cursor.fetchone()
    if row and row["admission_year"] is not None and term_position(
        row["target_year"], row["target_semester"]
    ) < term_position(row["admission_year"], row["admission_semester"]):
        raise HTTPException(409, "该学期早于你的入学学期，不能选课")
