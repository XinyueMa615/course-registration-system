"""课程目录读取；绝不对 course_catalog_demo 执行 INSERT/UPDATE/DELETE。"""
from fastapi import HTTPException

from .config import settings
from .db import read_connection


CATALOG = f"`{settings.catalog_db}`"


def offerings_for_term(term_code: str) -> list[dict]:
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT o.offering_id,o.course_id,o.term_code,o.section_code,o.capacity,
                   c.title,c.credits,c.department_id,d.name AS department_name,
                   a.professor_id,p.full_name AS professor_name,
                   m.weekday,m.start_period,m.end_period,m.building,m.room_number
            FROM {CATALOG}.course_offering o
            JOIN {CATALOG}.course c ON c.course_id=o.course_id
            JOIN {CATALOG}.department d ON d.department_id=c.department_id
            LEFT JOIN {CATALOG}.offering_meeting m ON m.offering_id=o.offering_id
            LEFT JOIN teaching_assignment a ON a.offering_id=o.offering_id
            LEFT JOIN professor_profile p ON p.professor_id=a.professor_id
            WHERE o.term_code=%s AND c.is_active=TRUE
            ORDER BY c.course_id,o.section_code,m.weekday,m.start_period
            """,
            (term_code,),
        )
        rows = cursor.fetchall()
        cursor.execute(
            f"""SELECT course_id,prerequisite_course_id,minimum_grade
                FROM {CATALOG}.course_prerequisite"""
        )
        prerequisites = cursor.fetchall()
        cursor.execute(
            "SELECT offering_id,enrolled_count,status FROM offering_registration_state WHERE term_code=%s",
            (term_code,),
        )
        state = {row["offering_id"]: row for row in cursor.fetchall()}

    prereq_by_course: dict[str, list[dict]] = {}
    for row in prerequisites:
        prereq_by_course.setdefault(row["course_id"], []).append(
            {"course_id": row["prerequisite_course_id"], "minimum_grade": row["minimum_grade"]}
        )
    offerings: dict[str, dict] = {}
    for row in rows:
        offering_id = row["offering_id"]
        if offering_id not in offerings:
            local = state.get(offering_id, {})
            offerings[offering_id] = {
                "offering_id": offering_id,
                "course_id": row["course_id"],
                "title": row["title"],
                "term_code": row["term_code"],
                "section_code": row["section_code"],
                "credits": float(row["credits"]),
                "department_id": row["department_id"],
                "department_name": row["department_name"],
                "professor_id": row["professor_id"],
                "professor_name": row["professor_name"],
                "capacity": row["capacity"],
                "enrolled_count": local.get("enrolled_count", 0),
                "status": local.get("status", "OPEN"),
                "prerequisites": prereq_by_course.get(row["course_id"], []),
                "meetings": [],
            }
        if row["weekday"] is not None:
            offerings[offering_id]["meetings"].append(
                {
                    "weekday": row["weekday"],
                    "start_period": row["start_period"],
                    "end_period": row["end_period"],
                    "building": row["building"],
                    "room_number": row["room_number"],
                }
            )
    return list(offerings.values())


def required_offerings(cursor, term_code: str, offering_ids: list[str]) -> dict[str, dict]:
    if not offering_ids:
        return {}
    placeholders = ",".join(["%s"] * len(offering_ids))
    cursor.execute(
        f"""
        SELECT o.offering_id,o.course_id,o.term_code,o.capacity,c.credits
        FROM {CATALOG}.course_offering o
        JOIN {CATALOG}.course c ON c.course_id=o.course_id
        WHERE o.offering_id IN ({placeholders}) AND o.term_code=%s AND c.is_active=TRUE
        """,
        (*offering_ids, term_code),
    )
    offerings = {row["offering_id"]: row for row in cursor.fetchall()}
    if len(offerings) != len(offering_ids):
        raise HTTPException(status_code=400, detail="课表中有不存在或不属于当前学期的教学班")
    invalid_capacity = [
        row["offering_id"] for row in offerings.values()
        if not 3 <= row["capacity"] <= 10
    ]
    if invalid_capacity:
        raise HTTPException(
            status_code=409,
            detail=f"课程目录中的教学班容量必须为 3–10 人：{', '.join(sorted(invalid_capacity))}",
        )
    if len({row["course_id"] for row in offerings.values()}) != len(offering_ids):
        raise HTTPException(status_code=400, detail="同一门课程不能同时选择多个教学班")
    return offerings


def meetings_for_offerings(cursor, offering_ids: list[str]) -> list[dict]:
    if not offering_ids:
        return []
    placeholders = ",".join(["%s"] * len(offering_ids))
    cursor.execute(
        f"""SELECT offering_id,weekday,start_period,end_period
            FROM {CATALOG}.offering_meeting WHERE offering_id IN ({placeholders})""",
        tuple(offering_ids),
    )
    return cursor.fetchall()


def availability_for_offerings(term_code: str, offering_ids: list[str]) -> list[dict]:
    """轻量读取所选班级的最新名额，不反复加载整个旧课程目录。"""
    ids = list(dict.fromkeys(offering_ids))
    if len(ids) > 6 or any(not item or len(item) > 40 for item in ids):
        raise HTTPException(400, "最多查询 6 个有效教学班")
    if not ids:
        return []
    placeholders = ",".join(["%s"] * len(ids))
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"SELECT o.offering_id,o.capacity,COALESCE(s.enrolled_count,0) AS enrolled_count,"
            f"COALESCE(s.status,'OPEN') AS status "
            f"FROM {CATALOG}.course_offering o "
            "LEFT JOIN offering_registration_state s "
            "ON s.offering_id=o.offering_id AND s.term_code=o.term_code "
            f"WHERE o.term_code=%s AND o.offering_id IN ({placeholders})",
            (term_code, *ids),
        )
        rows = cursor.fetchall()
    if len(rows) != len(ids):
        raise HTTPException(400, "有教学班不存在或不属于当前学期")
    by_id = {row["offering_id"]: row for row in rows}
    return [
        {**by_id[item], "is_full": by_id[item]["status"] != "OPEN" or
         by_id[item]["enrolled_count"] >= by_id[item]["capacity"]}
        for item in ids
    ]
