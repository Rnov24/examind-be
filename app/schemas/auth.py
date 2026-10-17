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


class ForgotPasswordRequest(BaseModel):
    identifier: str


class ForgotPasswordResponse(BaseModel):
    success: bool = True
    message: str
    email: str
    expires_in_minutes: int = 15
    cooldown_seconds: int = 60
    dev_preview: Optional[dict] = None


class VerifyResetTokenRequest(BaseModel):
    token: str
    email: Optional[str] = None


class VerifyResetTokenResponse(BaseModel):
    valid: bool = True
    email: str
    user_name: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    token: str
    email: Optional[str] = None
    new_password: str
    confirm_password: str


class ResetPasswordResponse(BaseModel):
    success: bool = True
    message: str


class SchoolOptionResponse(BaseModel):
    id: int
    name: str
    code: str
    domain: Optional[str] = None


class VerifyRegistrationCodeRequest(BaseModel):
    code: str
    role: Optional[str] = None
    tenant_id: Optional[int] = None


class VerifyRegistrationCodeResponse(BaseModel):
    valid: bool = True
    code: str
    role: str
    tenant_id: int
    tenant_name: str
    tenant_code: str
    description: Optional[str] = None


class SchoolRegisterRequest(BaseModel):
    tenant_id: Optional[int] = None
    role: str
    registration_code: str
    full_name: str
    identifier: str
    email: str
    password: str
    confirm_password: Optional[str] = None
    avatar_url: Optional[str] = None


class RegisterResponse(BaseModel):
    requires_verification: bool = True
    email: str
    expires_in_minutes: int = 10


