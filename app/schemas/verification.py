from typing import Optional
from pydantic import BaseModel, Field, field_validator


class SendOtpRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=120, description="Target email address")
    purpose: str = Field(default="email_verification", description="Purpose of OTP: email_verification or password_reset")

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        clean = v.strip().lower()
        if "@" not in clean or "." not in clean.split("@")[-1]:
            raise ValueError("Format alamat email tidak valid")
        return clean


class SendOtpResponse(BaseModel):
    success: bool = True
    message: str
    email: str
    expires_in_minutes: int = 10


class VerifyOtpRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=120, description="Target email address")
    otp_code: str = Field(..., min_length=4, max_length=10, description="Verification OTP code")
    purpose: str = Field(default="email_verification", description="Purpose of OTP")

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        clean = v.strip().lower()
        if "@" not in clean or "." not in clean.split("@")[-1]:
            raise ValueError("Format alamat email tidak valid")
        return clean


class VerifyOtpResponse(BaseModel):
    success: bool = True
    message: str
    email: str
    is_email_verified: bool = True
