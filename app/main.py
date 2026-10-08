"""课程注册系统 API。"""
import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from .billing import billing_status, dispatch_due
from .catalog import availability_for_offerings, offerings_for_term
from .closing import close_registration, preview_close
from .config import ROOT
from .db import read_connection, transaction
from .grades import grade_offerings, report_card, roster, set_grade
from .models import (
    GradeInput, LoginRequest, PasswordChange, ProfessorCreate, ProfessorPatch, ScheduleInput, StudentCreate, StudentPatch,
    TermCreate, TermPatch,
)
from .professors import claim_offering, current_roster, release_offering, teacher_offerings
from .registrar import (
    add_qualification,
    catalog_options,
    create_professor,
    create_student,
    delete_professor,
    delete_student,
    professors,
    remove_qualification,
    students,
    update_professor,
    update_student,
)
from .schedules import delete_schedule, get_schedule, save_draft, submit_schedule
from .security import create_token, current_user, hash_password, require_role, verify_password
from .terms import complete_term, create_term, open_term, terms, update_term


logger = logging.getLogger(__name__)


async def _billing_worker() -> None:
    last_error = None
    while True:
        try:
            await asyncio.to_thread(dispatch_due, 20)
        except Exception as error:
            marker = (type(error).__name__, getattr(error, "status_code", None))
            if marker != last_error:
                logger.warning("模拟计费投递暂不可用：%s", marker[0])
            last_error = marker
        else:
            last_error = None
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_billing_worker())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="课程注册系统", version="0.5.0", lifespan=lifespan)


@app.get("/")
def index():
    return FileResponse(ROOT / "web" / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/assets/theme.css")
def theme():
    return FileResponse(ROOT / "web" / "theme.css", media_type="text/css", headers={"Cache-Control": "no-store"})


@app.get("/professor")
def professor_page():
    return FileResponse(ROOT / "web" / "professor.html", headers={"Cache-Control": "no-store"})


@app.get("/registrar")
def registrar_page():
    return FileResponse(ROOT / "web" / "registrar.html", headers={"Cache-Control": "no-store"})


@app.get("/health")
def health():
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 AS ok")
        cursor.fetchone()
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(body: LoginRequest):
    with read_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT user_id,username,password_hash,role,is_active,must_change_password FROM user_account WHERE username=%s",
            (body.username,),
        )
        user = cursor.fetchone()
    if not user or not user["is_active"] or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "账号或密码错误")
    return {
        "access_token": create_token(user["user_id"], user["role"]),
        "token_type": "bearer",
        "username": user["username"],
        "role": user["role"],
        "must_change_password": bool(user["must_change_password"]),
    }


@app.get("/api/auth/me")
def auth_me(user: dict = Depends(current_user)):
    return {"username": user["username"], "role": user["role"],
            "must_change_password": bool(user["must_change_password"])}


@app.post("/api/auth/change-password")
def change_password(body: PasswordChange, user: dict = Depends(current_user)):
    if body.current_password == body.new_password:
        raise HTTPException(400, "新密码不能与原密码相同")
    with transaction() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT password_hash FROM user_account WHERE user_id=%s FOR UPDATE", (user["user_id"],))
        row = cursor.fetchone()
        if not row or not verify_password(body.current_password, row["password_hash"]):
            raise HTTPException(400, "原密码不正确")
        cursor.execute(
            "UPDATE user_account SET password_hash=%s,must_change_password=FALSE WHERE user_id=%s",
            (hash_password(body.new_password), user["user_id"]),
        )
    return {"changed": True}


@app.get("/api/catalog/offerings")
def catalog(term_code: str, user: dict = Depends(require_role("STUDENT", "PROFESSOR", "REGISTRAR"))):
    return offerings_for_term(term_code)


@app.get("/api/students/me/schedules/{term_code}")
def schedule(term_code: str, user: dict = Depends(require_role("STUDENT"))):
    return get_schedule(user["user_id"], term_code)


@app.put("/api/students/me/schedules/{term_code}/draft")
def draft(term_code: str, body: ScheduleInput, user: dict = Depends(require_role("STUDENT"))):
    return save_draft(user["user_id"], term_code, body.choices)


@app.post("/api/students/me/schedules/{term_code}/submit")
def submit(term_code: str, user: dict = Depends(require_role("STUDENT"))):
    return submit_schedule(user["user_id"], term_code)


@app.delete("/api/students/me/schedules/{term_code}")
def student_delete_schedule(term_code: str, user: dict = Depends(require_role("STUDENT"))):
    return delete_schedule(user["user_id"], term_code)


@app.get("/api/students/me/availability/{term_code}")
def student_availability(
    term_code: str,
    offering_ids: list[str] = Query(default=[]),
    user: dict = Depends(require_role("STUDENT")),
):
    return availability_for_offerings(term_code, offering_ids)


@app.get("/api/students/me/report-card")
def student_report_card(user: dict = Depends(require_role("STUDENT"))):
    return report_card(user["user_id"])


@app.get("/api/professors/me/offerings/{term_code}")
def professor_offerings(term_code: str, user: dict = Depends(require_role("PROFESSOR"))):
    return teacher_offerings(user["user_id"], term_code)


@app.get("/api/professors/me/grade-offerings")
def professor_grade_offerings(user: dict = Depends(require_role("PROFESSOR"))):
    return grade_offerings(user["user_id"])


@app.post("/api/professors/me/offerings/{term_code}/{offering_id}")
def professor_claim(term_code: str, offering_id: str, user: dict = Depends(require_role("PROFESSOR"))):
    return claim_offering(user["user_id"], term_code, offering_id)


@app.delete("/api/professors/me/offerings/{term_code}/{offering_id}")
def professor_release(term_code: str, offering_id: str, user: dict = Depends(require_role("PROFESSOR"))):
    return release_offering(user["user_id"], term_code, offering_id)


@app.get("/api/professors/me/offerings/{term_code}/{offering_id}/current-roster")
def professor_current_roster(
    term_code: str, offering_id: str, user: dict = Depends(require_role("PROFESSOR")),
):
    return current_roster(user["user_id"], term_code, offering_id)


@app.get("/api/professors/me/offerings/{term_code}/{offering_id}/roster")
def professor_roster(term_code: str, offering_id: str, user: dict = Depends(require_role("PROFESSOR"))):
    return roster(user["user_id"], term_code, offering_id)


@app.put("/api/professors/me/offerings/{term_code}/{offering_id}/roster/{enrollment_id}/grade")
def professor_set_grade(
    term_code: str, offering_id: str, enrollment_id: int, body: GradeInput,
    user: dict = Depends(require_role("PROFESSOR")),
):
    return set_grade(user["user_id"], term_code, offering_id, enrollment_id, body.letter_grade)


@app.get("/api/registrar/catalog-options")
def registrar_catalog(user: dict = Depends(require_role("REGISTRAR"))):
    return catalog_options()


@app.get("/api/registrar/students")
def registrar_students(user: dict = Depends(require_role("REGISTRAR"))):
    return students()


@app.post("/api/registrar/students", status_code=201)
def registrar_create_student(body: StudentCreate, user: dict = Depends(require_role("REGISTRAR"))):
    return create_student(user["user_id"], body)


@app.patch("/api/registrar/students/{student_id}")
def registrar_update_student(student_id: str, body: StudentPatch, user: dict = Depends(require_role("REGISTRAR"))):
    return update_student(user["user_id"], student_id, body)


@app.delete("/api/registrar/students/{student_id}")
def registrar_delete_student(student_id: str, user: dict = Depends(require_role("REGISTRAR"))):
    return delete_student(user["user_id"], student_id)


@app.get("/api/registrar/professors")
def registrar_professors(user: dict = Depends(require_role("REGISTRAR"))):
    return professors()


@app.post("/api/registrar/professors", status_code=201)
def registrar_create_professor(body: ProfessorCreate, user: dict = Depends(require_role("REGISTRAR"))):
    return create_professor(user["user_id"], body)


@app.patch("/api/registrar/professors/{professor_id}")
def registrar_update_professor(professor_id: str, body: ProfessorPatch, user: dict = Depends(require_role("REGISTRAR"))):
    return update_professor(user["user_id"], professor_id, body)


@app.delete("/api/registrar/professors/{professor_id}")
def registrar_delete_professor(professor_id: str, user: dict = Depends(require_role("REGISTRAR"))):
    return delete_professor(user["user_id"], professor_id)


@app.post("/api/registrar/professors/{professor_id}/qualifications/{course_id}")
def registrar_add_qualification(professor_id: str, course_id: str, user: dict = Depends(require_role("REGISTRAR"))):
    return add_qualification(user["user_id"], professor_id, course_id)


@app.delete("/api/registrar/professors/{professor_id}/qualifications/{course_id}")
def registrar_remove_qualification(professor_id: str, course_id: str, user: dict = Depends(require_role("REGISTRAR"))):
    return remove_qualification(user["user_id"], professor_id, course_id)


@app.get("/api/registrar/terms")
def registrar_terms(user: dict = Depends(require_role("REGISTRAR"))):
    return terms()


@app.post("/api/registrar/terms", status_code=201)
def registrar_create_term(body: TermCreate, user: dict = Depends(require_role("REGISTRAR"))):
    return create_term(user["user_id"], body)


@app.patch("/api/registrar/terms/{term_code}")
def registrar_update_term(term_code: str, body: TermPatch, user: dict = Depends(require_role("REGISTRAR"))):
    return update_term(user["user_id"], term_code, body)


@app.post("/api/registrar/terms/{term_code}/open")
def registrar_open_term(term_code: str, user: dict = Depends(require_role("REGISTRAR"))):
    return open_term(user["user_id"], term_code)


@app.post("/api/registrar/terms/{term_code}/complete")
def registrar_complete_term(term_code: str, user: dict = Depends(require_role("REGISTRAR"))):
    return complete_term(user["user_id"], term_code)


@app.get("/api/registrar/terms/{term_code}/close-preview")
def registrar_close_preview(term_code: str, user: dict = Depends(require_role("REGISTRAR"))):
    return preview_close(term_code)


@app.post("/api/registrar/terms/{term_code}/close")
def registrar_close_term(term_code: str, user: dict = Depends(require_role("REGISTRAR"))):
    return close_registration(user["user_id"], term_code)


@app.post("/api/registrar/billing/dispatch-due")
def registrar_dispatch_billing(
    limit: int = Query(default=20, ge=1, le=100),
    term_code: str = Query(default=""),
    user: dict = Depends(require_role("REGISTRAR")),
):
    return dispatch_due(limit, term_code=term_code or None)


@app.get("/api/registrar/billing/{term_code}")
def registrar_billing_status(term_code: str, user: dict = Depends(require_role("REGISTRAR"))):
    return billing_status(term_code)
