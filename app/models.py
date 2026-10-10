from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=256)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=128)


class ChoiceInput(BaseModel):
    offering_id: str = Field(min_length=1, max_length=40)
    choice_type: Literal["PRIMARY", "ALTERNATE"]
    priority: int


class ScheduleInput(BaseModel):
    choices: list[ChoiceInput] = Field(max_length=6)


class GradeInput(BaseModel):
    letter_grade: Literal["A", "B", "C", "D", "F", "I"]


class StudentCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    ssn: Optional[str] = None
    status: Literal["ACTIVE", "INACTIVE", "GRADUATED"] = "ACTIVE"
    graduation_date: Optional[date] = None


class StudentPatch(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    date_of_birth: Optional[date] = None
    status: Optional[Literal["ACTIVE", "INACTIVE", "GRADUATED"]] = None
    graduation_date: Optional[date] = None
    ssn: Optional[str] = None


class ProfessorCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    department_id: str = Field(min_length=1, max_length=20)
    ssn: Optional[str] = None
    status: Literal["ACTIVE", "INACTIVE"] = "ACTIVE"


class ProfessorPatch(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    date_of_birth: Optional[date] = None
    department_id: Optional[str] = Field(default=None, min_length=1, max_length=20)
    status: Optional[Literal["ACTIVE", "INACTIVE"]] = None
    ssn: Optional[str] = None


class TermCreate(BaseModel):
    term_code: str = Field(min_length=1, max_length=8, pattern=r"^[A-Za-z0-9_-]+$")
    year: int = Field(ge=2000, le=9999)
    semester: Literal["SPRING", "SUMMER", "FALL", "WINTER"]
    registration_opens_at: datetime
    registration_closes_at: datetime
    tuition_per_credit: Decimal = Field(default=Decimal("0"), ge=0, max_digits=10, decimal_places=2)


class TermPatch(BaseModel):
    registration_opens_at: Optional[datetime] = None
    registration_closes_at: Optional[datetime] = None
    tuition_per_credit: Optional[Decimal] = Field(default=None, ge=0, max_digits=10, decimal_places=2)
