"""计算机系 2026 年演示培养方案；仅覆盖春、秋两个演示学期。

课程和建议学期参考《计算机科学与技术学院本科培养方案2022版（2023年修订）》；
先修课规则另由课程目录演示数据定义，并非培养方案原文要求。
"""
from __future__ import annotations

# 学期 -> 院系 -> 年级 -> 课程 ID。计算机系演示目录只保留这些计划课程。
DEMO_PLAN = {
    "2026SP": {"CS": {1: ("212002", "211001", "211002", "941015", "213001", "931102", "LD2001")}},
    "2026FA": {"CS": {2: ("212003", "211003", "211004", "211011", "211012", "213002", "931103")}},
}


def planned_grade(term_code: str, department_id: str, course_id: str) -> int | None:
    for year, courses in DEMO_PLAN.get(term_code, {}).get(department_id, {}).items():
        if course_id in courses:
            return year
    return None


def allowed_courses(term_code: str, department_id: str, grade: int | None) -> tuple[str, ...] | None:
    plan = DEMO_PLAN.get(term_code, {}).get(department_id)
    if plan is None:
        return None  # 其他院系尚未配置演示培养方案，保留旧选课行为。
    return plan.get(grade, ())
