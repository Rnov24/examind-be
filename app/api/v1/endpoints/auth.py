from datetime import datetime, timedelta
import secrets
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.core.security import verify_password, create_access_token, get_password_hash
from app.core.exceptions import AppException
from app.core.dependencies import get_current_active_user
from app.models.user import User
from app.models.verification import EmailVerification
from app.schemas.auth import LoginRequest, TokenData, UserResponse, UserCreate
from app.schemas.verification import SendOtpRequest, SendOtpResponse, VerifyOtpRequest, VerifyOtpResponse
from app.schemas.common import ApiResponse
from app.services.email.resend_service import generate_otp, send_otp_email

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=ApiResponse[TokenData])
def login(request: LoginRequest, db: Session = Depends(get_db)):
    # Look up user by identifier (NISN/NIP/username) or email
    user = (
        db.query(User)
        .filter((User.identifier == request.identifier) | (User.email == request.identifier))
        .first()
    )

    if not user or not verify_password(request.password, user.password_hash):
        raise AppException(
            message="Identifier atau kata sandi tidak valid. Silakan coba lagi.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="INVALID_CREDENTIALS",
        )

    if not user.is_active:
        raise AppException(
            message="Akun Anda sedang dinonaktifkan. Hubungi administrator.",
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="ACCOUNT_INACTIVE",
        )

    # Issue JWT token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token_payload = {
        "sub": str(user.id),
        "identifier": user.identifier,
        "email": user.email,
        "role": user.role,
        "full_name": user.full_name,
    }
    access_token = create_access_token(token_payload, expires_delta=access_token_expires)

    token_data = TokenData(
        access_token=access_token,
        token_type="bearer",
        expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        user=UserResponse.model_validate(user),
    )

    return ApiResponse.ok(data=token_data, message="Login berhasil")


@router.get("/me", response_model=ApiResponse[UserResponse])
def get_current_user_profile(current_user: User = Depends(get_current_active_user)):
    return ApiResponse.ok(
        data=UserResponse.model_validate(current_user),
        message="Profil pengguna berhasil dimuat",
    )


@router.post("/refresh", response_model=ApiResponse[TokenData])
def refresh_token(current_user: User = Depends(get_current_active_user)):
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token_payload = {
        "sub": str(current_user.id),
        "identifier": current_user.identifier,
        "email": current_user.email,
        "role": current_user.role,
        "full_name": current_user.full_name,
    }
    access_token = create_access_token(token_payload, expires_delta=access_token_expires)

    token_data = TokenData(
        access_token=access_token,
        token_type="bearer",
        expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        user=UserResponse.model_validate(current_user),
    )
    return ApiResponse.ok(data=token_data, message="Token berhasil diperbarui")


@router.post("/register", response_model=ApiResponse[UserResponse])
def register(request: UserCreate, db: Session = Depends(get_db)):
    # Check duplicate identifier or email
    existing = (
        db.query(User)
        .filter((User.identifier == request.identifier) | (User.email == request.email))
        .first()
    )
    if existing:
        raise AppException(
            message="Identifier atau email sudah terdaftar dalam sistem.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="USER_ALREADY_EXISTS",
        )

    new_user = User(
        identifier=request.identifier,
        email=request.email,
        password_hash=get_password_hash(request.password),
        full_name=request.full_name,
        role=request.role,
        avatar_url=request.avatar_url,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return ApiResponse.ok(
        data=UserResponse.model_validate(new_user),
        message="Pendaftaran pengguna berhasil",
    )


@router.post("/otp/send", response_model=ApiResponse[SendOtpResponse])
async def send_otp(request: SendOtpRequest, db: Session = Depends(get_db)):
    """Generate a 6-digit OTP code, persist it, and send it via Resend API."""
    # Invalidate previous unused codes for the same email and purpose
    db.query(EmailVerification).filter(
        EmailVerification.email == request.email,
        EmailVerification.purpose == request.purpose,
        EmailVerification.is_used == False,
    ).update({"is_used": True})

    otp_code = generate_otp(6)
    expires_in_minutes = 10
    expires_at = datetime.utcnow() + timedelta(minutes=expires_in_minutes)

    verification = EmailVerification(
        email=str(request.email),
        otp_code=otp_code,
        purpose=request.purpose,
        expires_at=expires_at,
        is_used=False,
    )
    db.add(verification)
    db.commit()

    # Send email via Resend API (or mock fallback if unconfigured)
    await send_otp_email(
        to_email=str(request.email),
        otp_code=otp_code,
        purpose=request.purpose,
        expires_in_minutes=expires_in_minutes,
    )

    response_data = SendOtpResponse(
        success=True,
        message=f"Kode OTP berhasil dikirim ke {request.email}",
        email=str(request.email),
        expires_in_minutes=expires_in_minutes,
    )
    return ApiResponse.ok(data=response_data, message="Kode verifikasi OTP berhasil dikirim")


@router.post("/otp/verify", response_model=ApiResponse[VerifyOtpResponse])
def verify_otp(request: VerifyOtpRequest, db: Session = Depends(get_db)):
    """Validate 6-digit OTP and mark email as verified."""
    now = datetime.utcnow()

    # Query active verification records for email and purpose
    verification = (
        db.query(EmailVerification)
        .filter(
            EmailVerification.email == request.email,
            EmailVerification.purpose == request.purpose,
            EmailVerification.is_used == False,
            EmailVerification.expires_at > now,
        )
        .order_by(EmailVerification.id.desc())
        .first()
    )

    if not verification:
        raise AppException(
            message="Kode OTP tidak valid atau telah kedaluwarsa. Silakan minta kode baru.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_OR_EXPIRED_OTP",
        )

    # Timing-safe comparison of OTP codes
    if not secrets.compare_digest(verification.otp_code.strip(), request.otp_code.strip()):
        raise AppException(
            message="Kode OTP yang Anda masukkan salah.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_OTP",
        )

    # Mark OTP as used
    verification.is_used = True

    # If matching user exists in system, mark their email as verified
    user = db.query(User).filter(User.email == request.email).first()
    if user:
        user.is_email_verified = True

    db.commit()

    response_data = VerifyOtpResponse(
        success=True,
        message="Verifikasi email berhasil diverifikasi.",
        email=str(request.email),
        is_email_verified=True,
    )
    return ApiResponse.ok(data=response_data, message="Email berhasil diverifikasi")

