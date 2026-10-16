from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    identifier: str
    password: str


class UserResponse(BaseModel):
    id: int
    identifier: str
    email: str
    full_name: str
    role: str
    tenant_id: Optional[int] = None
    tenant_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool = True
    is_email_verified: bool = False
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TokenData(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserResponse


class UserCreate(BaseModel):
    identifier: str
    email: str
    password: str
    full_name: str
    role: str
    avatar_url: Optional[str] = None
