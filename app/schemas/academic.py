from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from app.schemas.auth import UserResponse


class ClassBase(BaseModel):
    name: str
    grade_level: str
    academic_year: str


class ClassCreate(ClassBase):
    pass


class ClassUpdate(BaseModel):
    name: Optional[str] = None
    grade_level: Optional[str] = None
    academic_year: Optional[str] = None


class ClassMemberResponse(BaseModel):
    id: int
    class_id: int
    user_id: int
    role: str
    joined_at: Optional[datetime] = None
    user: Optional[UserResponse] = None

    model_config = ConfigDict(from_attributes=True)


class ClassResponse(ClassBase):
    id: int
    created_by: int
    created_at: Optional[datetime] = None
    members_count: int = 0
    creator_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ClassDetailResponse(ClassResponse):
    members: List[ClassMemberResponse] = []


class ClassMemberAdd(BaseModel):
    user_id: int
    role: str = "student"
