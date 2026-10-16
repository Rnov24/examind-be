from typing import List, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_access_token
from app.core.exceptions import AppException
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise AppException(
            message="Token autentikasi tidak ditemukan. Silakan login terlebih dahulu.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="UNAUTHORIZED",
        )

    payload = decode_access_token(token)
    if not payload:
        raise AppException(
            message="Sesi login telah kedaluwarsa atau token tidak valid. Silakan login kembali.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="TOKEN_EXPIRED",
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise AppException(
            message="Payload token tidak valid.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="INVALID_TOKEN",
        )

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise AppException(
            message="Pengguna tidak ditemukan dalam sistem.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="USER_NOT_FOUND",
        )

    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise AppException(
            message="Akun pengguna telah dinonaktifkan. Hubungi administrator.",
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="ACCOUNT_INACTIVE",
        )
    return current_user


def require_roles(allowed_roles: List[str]):
    def role_checker(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role not in allowed_roles:
            raise AppException(
                message=f"Akses ditolak untuk peran Anda ({current_user.role}). Memerlukan salah satu dari: {', '.join(allowed_roles)}.",
                status_code=status.HTTP_403_FORBIDDEN,
                error_code="FORBIDDEN_ROLE",
            )
        return current_user

    return role_checker


# Convenient role dependency shortcuts
require_superadmin = require_roles(["superadmin"])
require_admin = require_roles(["admin", "superadmin"])
require_teacher = require_roles(["teacher", "admin", "superadmin"])
require_teacher_or_admin = require_roles(["teacher", "admin", "superadmin"])
require_student = require_roles(["student"])
require_any_authenticated = get_current_active_user

