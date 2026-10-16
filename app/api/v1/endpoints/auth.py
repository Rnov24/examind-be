from datetime import datetime, timedelta
import secrets
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.core.security import verify_password, create_access_token, get_password_hash
from app.core.exceptions import AppException
from app.core.dependencies import get_current_active_user
from typing import List, Optional
import logging
from app.models.user import User
from app.models.tenant import Tenant, TenantRegistrationCode
from app.models.verification import EmailVerification
from app.schemas.auth import (
    LoginRequest,
    TokenData,
    UserResponse,
    UserCreate,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    VerifyResetTokenRequest,
    VerifyResetTokenResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    SchoolOptionResponse,
    VerifyRegistrationCodeRequest,
    VerifyRegistrationCodeResponse,
    SchoolRegisterRequest,
)
from app.schemas.verification import SendOtpRequest, SendOtpResponse, VerifyOtpRequest, VerifyOtpResponse
from app.schemas.common import ApiResponse
from app.services.email.resend_service import (
    generate_otp,
    send_otp_email,
    send_password_reset_email,
    send_password_reset_success_email,
)

logger = logging.getLogger("examind.auth")

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


@router.get("/schools", response_model=ApiResponse[List[SchoolOptionResponse]])
def get_public_schools(db: Session = Depends(get_db)):
    """List available active school tenants for registration."""
    tenants = db.query(Tenant).filter(Tenant.is_active == True).order_by(Tenant.name.asc()).all()
    results = [
        SchoolOptionResponse(
            id=t.id,
            name=t.name,
            code=t.code,
            domain=t.domain,
        )
        for t in tenants
    ]
    return ApiResponse.ok(data=results, message="Daftar sekolah berhasil dimuat")


@router.post("/verify-registration-code", response_model=ApiResponse[VerifyRegistrationCodeResponse])
def verify_registration_code(request: VerifyRegistrationCodeRequest, db: Session = Depends(get_db)):
    """Verify that a specific registration code provided for a school role is valid."""
    clean_code = request.code.strip().upper() if request.code else ""
    if not clean_code:
        raise AppException(
            message="Kode pendaftaran wajib diisi.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="EMPTY_CODE",
        )

    now = datetime.utcnow()
    reg_code = (
        db.query(TenantRegistrationCode)
        .filter(
            TenantRegistrationCode.code == clean_code,
            TenantRegistrationCode.is_active == True,
        )
        .first()
    )

    if not reg_code:
        raise AppException(
            message=f"Kode pendaftaran '{clean_code}' tidak terdaftar atau telah dinonaktifkan.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_REGISTRATION_CODE",
        )

    if reg_code.expires_at and reg_code.expires_at < now:
        raise AppException(
            message="Kode pendaftaran telah kedaluwarsa.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="EXPIRED_REGISTRATION_CODE",
        )

    if reg_code.max_uses > 0 and reg_code.used_count >= reg_code.max_uses:
        raise AppException(
            message="Kode pendaftaran telah mencapai batas kuota pendaftaran maksimum.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="CODE_QUOTA_EXCEEDED",
        )

    # If role filter provided, verify match
    if request.role and request.role != reg_code.role:
        role_label = "Admin Sekolah" if reg_code.role == "admin" else "Guru" if reg_code.role == "teacher" else "Siswa"
        req_role_label = "Admin Sekolah" if request.role == "admin" else "Guru" if request.role == "teacher" else "Siswa"
        raise AppException(
            message=f"Kode '{clean_code}' khusus untuk peran {role_label}, tidak dapat digunakan untuk mendaftar sebagai {req_role_label}.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="ROLE_MISMATCH",
        )

    # If tenant_id provided, verify match
    if request.tenant_id and request.tenant_id != reg_code.tenant_id:
        raise AppException(
            message=f"Kode '{clean_code}' tidak sesuai dengan sekolah yang Anda pilih.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="TENANT_MISMATCH",
        )

    tenant = reg_code.tenant
    return ApiResponse.ok(
        data=VerifyRegistrationCodeResponse(
            valid=True,
            code=reg_code.code,
            role=reg_code.role,
            tenant_id=reg_code.tenant_id,
            tenant_name=tenant.name if tenant else "Sekolah Terdaftar",
            tenant_code=tenant.code if tenant else "",
            description=reg_code.description,
        ),
        message="Kode pendaftaran valid dan terverifikasi",
    )


@router.post("/register", response_model=ApiResponse[TokenData])
def register(request: SchoolRegisterRequest, db: Session = Depends(get_db)):
    """Register a new student, teacher, or school admin using a provider-issued role/school code."""
    clean_code = request.registration_code.strip().upper() if request.registration_code else ""
    if not clean_code:
        raise AppException(
            message="Kode pendaftaran khusus institusi sekolah wajib diisi.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="REGISTRATION_CODE_REQUIRED",
        )

    clean_identifier = request.identifier.strip()
    clean_email = request.email.strip().lower()

    if not clean_identifier or not clean_email:
        raise AppException(
            message="Identifier (NISN/NIP) dan email wajib diisi.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="MISSING_CREDENTIALS",
        )

    if len(request.password) < 6:
        raise AppException(
            message="Kata sandi minimal harus terdiri dari 6 karakter.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="PASSWORD_TOO_SHORT",
        )

    if request.confirm_password and request.password != request.confirm_password:
        raise AppException(
            message="Konfirmasi kata sandi tidak cocok dengan kata sandi yang dimasukkan.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="PASSWORD_MISMATCH",
        )

    # Validate registration code
    now = datetime.utcnow()
    reg_code = (
        db.query(TenantRegistrationCode)
        .filter(
            TenantRegistrationCode.code == clean_code,
            TenantRegistrationCode.is_active == True,
        )
        .first()
    )

    if not reg_code:
        raise AppException(
            message=f"Kode pendaftaran '{clean_code}' tidak valid atau telah dinonaktifkan.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_REGISTRATION_CODE",
        )

    if reg_code.expires_at and reg_code.expires_at < now:
        raise AppException(
            message="Kode pendaftaran ini telah kedaluwarsa.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="EXPIRED_REGISTRATION_CODE",
        )

    if reg_code.max_uses > 0 and reg_code.used_count >= reg_code.max_uses:
        raise AppException(
            message="Kode pendaftaran ini telah mencapai batas maksimum pengguna.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="CODE_QUOTA_EXCEEDED",
        )

    # Verify role match if specified
    if request.role and request.role != reg_code.role:
        role_map = {"admin": "Admin Sekolah", "teacher": "Guru", "student": "Siswa"}
        expected = role_map.get(reg_code.role, reg_code.role)
        actual = role_map.get(request.role, request.role)
        raise AppException(
            message=f"Kode pendaftaran ini dialokasikan untuk peran {expected}, bukan {actual}.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="ROLE_MISMATCH",
        )

    # Verify tenant match if specified
    if request.tenant_id and request.tenant_id != reg_code.tenant_id:
        raise AppException(
            message="Kode pendaftaran tidak cocok dengan sekolah yang Anda pilih.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="TENANT_MISMATCH",
        )

    # Check for duplicate identifier or email
    existing = (
        db.query(User)
        .filter((User.identifier == clean_identifier) | (User.email == clean_email))
        .first()
    )
    if existing:
        raise AppException(
            message=f"Identifier '{clean_identifier}' atau email '{clean_email}' sudah terdaftar dalam sistem.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="USER_ALREADY_EXISTS",
        )

    # Create new user associated with the tenant and role
    new_user = User(
        identifier=clean_identifier,
        email=clean_email,
        password_hash=get_password_hash(request.password),
        full_name=request.full_name.strip(),
        role=reg_code.role,
        tenant_id=reg_code.tenant_id,
        avatar_url=request.avatar_url,
        is_active=True,
        is_email_verified=True,
    )
    db.add(new_user)

    # Increment code usage
    reg_code.used_count += 1

    db.commit()
    db.refresh(new_user)

    # Issue JWT token for immediate login
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token_payload = {
        "sub": str(new_user.id),
        "identifier": new_user.identifier,
        "email": new_user.email,
        "role": new_user.role,
        "full_name": new_user.full_name,
    }
    access_token = create_access_token(token_payload, expires_delta=access_token_expires)

    token_data = TokenData(
        access_token=access_token,
        token_type="bearer",
        expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        user=UserResponse.model_validate(new_user),
    )

    role_label = "Admin Sekolah" if new_user.role == "admin" else "Guru" if new_user.role == "teacher" else "Siswa"
    return ApiResponse.ok(
        data=token_data,
        message=f"Pendaftaran sebagai {role_label} di {new_user.tenant_name} berhasil! Anda telah masuk.",
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


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return email
    parts = email.split("@", 1)
    name, domain = parts[0], parts[1]
    if len(name) <= 2:
        masked_name = name[0] + "***"
    else:
        masked_name = name[:2] + "***" + name[-1]
    return f"{masked_name}@{domain}"


@router.post("/forgot-password", response_model=ApiResponse[ForgotPasswordResponse])
async def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Handle forgot password requests:
    Generates a secure 32-byte reset token and a 6-digit OTP code,
    persists both in email_verifications table, and dispatches email via Resend API.
    """
    clean_identifier = request.identifier.strip()
    if not clean_identifier:
        raise AppException(
            message="Mohon masukkan email, NISN, atau NIP akun Anda.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="EMPTY_IDENTIFIER",
        )

    # Find user by email, identifier (NISN/NIP), or username
    user = (
        db.query(User)
        .filter((User.email == clean_identifier) | (User.identifier == clean_identifier))
        .first()
    )

    expires_in_minutes = 15
    cooldown_seconds = 60

    # If user doesn't exist, return a generic message to prevent account enumeration
    if not user or not user.email:
        return ApiResponse.ok(
            data=ForgotPasswordResponse(
                success=True,
                message="Jika akun dengan data tersebut terdaftar di sistem, instruksi reset kata sandi telah dikirimkan ke email Anda.",
                email=_mask_email(clean_identifier) if "@" in clean_identifier else "email terdaftar",
                expires_in_minutes=expires_in_minutes,
                cooldown_seconds=cooldown_seconds,
            ),
            message="Permintaan reset kata sandi diproses",
        )

    # Invalidate existing unused password reset tokens for this user
    db.query(EmailVerification).filter(
        EmailVerification.email == user.email,
        EmailVerification.purpose.in_(["password_reset", "password_reset_code"]),
        EmailVerification.is_used == False,
    ).update({"is_used": True})

    # Generate cryptographically secure tokens
    reset_token = secrets.token_urlsafe(32)
    short_code = generate_otp(6)
    expires_at = datetime.utcnow() + timedelta(minutes=expires_in_minutes)

    # Persist both URL token and 6-digit manual OTP code
    token_entry = EmailVerification(
        email=user.email,
        otp_code=reset_token,
        purpose="password_reset",
        expires_at=expires_at,
        is_used=False,
    )
    code_entry = EmailVerification(
        email=user.email,
        otp_code=short_code,
        purpose="password_reset_code",
        expires_at=expires_at,
        is_used=False,
    )
    db.add(token_entry)
    db.add(code_entry)
    db.commit()

    # Construct reset URL pointing to frontend reset-password route
    frontend_base = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
    reset_url = f"{frontend_base}/reset-password?token={reset_token}&email={user.email}"

    # Dispatch email via Resend API
    await send_password_reset_email(
        to_email=user.email,
        user_name=user.full_name,
        reset_url=reset_url,
        token_code=short_code,
        expires_in_minutes=expires_in_minutes,
    )

    # Provide development preview payload for local testing without physical inboxes
    dev_preview = None
    if settings.DEBUG or settings.ENVIRONMENT == "development":
        dev_preview = {
            "reset_url": reset_url,
            "token": reset_token,
            "short_code": short_code,
            "target_email": user.email,
        }

    response_data = ForgotPasswordResponse(
        success=True,
        message=f"Tautan dan kode verifikasi reset kata sandi telah dikirim ke {_mask_email(user.email)}.",
        email=_mask_email(user.email),
        expires_in_minutes=expires_in_minutes,
        cooldown_seconds=cooldown_seconds,
        dev_preview=dev_preview,
    )
    return ApiResponse.ok(data=response_data, message="Instruksi reset kata sandi berhasil dikirim")


@router.post("/verify-reset-token", response_model=ApiResponse[VerifyResetTokenResponse])
def verify_reset_token(request: VerifyResetTokenRequest, db: Session = Depends(get_db)):
    """Verify that a given reset token or 6-digit code is valid and not expired."""
    clean_token = request.token.strip()
    if not clean_token:
        raise AppException(
            message="Token reset kata sandi tidak boleh kosong.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="EMPTY_TOKEN",
        )

    now = datetime.utcnow()
    query = db.query(EmailVerification).filter(
        EmailVerification.otp_code == clean_token,
        EmailVerification.purpose.in_(["password_reset", "password_reset_code"]),
        EmailVerification.is_used == False,
        EmailVerification.expires_at > now,
    )

    if request.email:
        query = query.filter(EmailVerification.email == request.email.strip().lower())

    verification = query.order_by(EmailVerification.id.desc()).first()

    if not verification:
        raise AppException(
            message="Tautan atau kode reset kata sandi tidak valid atau telah kedaluwarsa. Silakan minta tautan baru.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_OR_EXPIRED_RESET_TOKEN",
        )

    user = db.query(User).filter(User.email == verification.email).first()

    return ApiResponse.ok(
        data=VerifyResetTokenResponse(
            valid=True,
            email=verification.email,
            user_name=user.full_name if user else None,
        ),
        message="Token reset kata sandi valid",
    )


@router.post("/reset-password", response_model=ApiResponse[ResetPasswordResponse])
async def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Reset the user password using a verified token or 6-digit code."""
    clean_token = request.token.strip()
    if not clean_token:
        raise AppException(
            message="Token reset kata sandi tidak boleh kosong.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="EMPTY_TOKEN",
        )

    if len(request.new_password) < 6:
        raise AppException(
            message="Kata sandi baru minimal harus terdiri dari 6 karakter.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="PASSWORD_TOO_SHORT",
        )

    if request.new_password != request.confirm_password:
        raise AppException(
            message="Konfirmasi kata sandi tidak sesuai dengan kata sandi baru.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="PASSWORD_MISMATCH",
        )

    now = datetime.utcnow()
    query = db.query(EmailVerification).filter(
        EmailVerification.otp_code == clean_token,
        EmailVerification.purpose.in_(["password_reset", "password_reset_code"]),
        EmailVerification.is_used == False,
        EmailVerification.expires_at > now,
    )

    if request.email:
        query = query.filter(EmailVerification.email == request.email.strip().lower())

    verification = query.order_by(EmailVerification.id.desc()).first()

    if not verification:
        raise AppException(
            message="Tautan atau kode reset kata sandi tidak valid atau sudah kedaluwarsa. Silakan minta instruksi baru.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_RESET_TOKEN",
        )

    user = db.query(User).filter(User.email == verification.email).first()
    if not user:
        raise AppException(
            message="Pengguna pemilik akun tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="USER_NOT_FOUND",
        )

    # Update password hash
    user.password_hash = get_password_hash(request.new_password)

    # Invalidate all reset tokens for this user email
    db.query(EmailVerification).filter(
        EmailVerification.email == user.email,
        EmailVerification.purpose.in_(["password_reset", "password_reset_code"]),
    ).update({"is_used": True})

    db.commit()

    # Send confirmation email
    try:
        await send_password_reset_success_email(to_email=user.email, user_name=user.full_name)
    except Exception as e:
        logger.warning(f"Could not send password change confirmation email: {e}")

    return ApiResponse.ok(
        data=ResetPasswordResponse(
            success=True,
            message="Kata sandi berhasil diperbarui! Silakan masuk dengan kata sandi baru Anda.",
        ),
        message="Kata sandi berhasil diperbarui",
    )


