import base64
import hashlib
import logging
from typing import Optional
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import SessionLocal

logger = logging.getLogger("examind.secret_manager")


def _get_fernet_cipher() -> Fernet:
    """Derive a deterministic 32-byte URL-safe base64 encryption key from SECRET_KEY."""
    derived_key = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    urlsafe_b64_key = base64.urlsafe_b64encode(derived_key)
    return Fernet(urlsafe_b64_key)


def encrypt_secret(plain_text: str) -> str:
    """Encrypt a secret plaintext string using Fernet/AES at rest."""
    if not plain_text:
        return ""
    cipher = _get_fernet_cipher()
    return cipher.encrypt(plain_text.strip().encode("utf-8")).decode("utf-8")


def decrypt_secret(cipher_text: str) -> str:
    """Decrypt an encrypted secret ciphertext back to plaintext string."""
    if not cipher_text:
        return ""
    cipher = _get_fernet_cipher()
    try:
        return cipher.decrypt(cipher_text.strip().encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to decrypt secret: {e}")
        return ""


def mask_secret(plain_text: str) -> str:
    """Mask a secret string for safe display in UI/API responses."""
    if not plain_text:
        return ""
    val = plain_text.strip()
    if len(val) <= 8:
        return "********"
    return f"{val[:4]}********{val[-4:]}"


def get_secret(key_name: str, db: Optional[Session] = None, default: str = "") -> str:
    """
    Resolve secret key dynamically:
    1. Check MySQL system_secrets table for an active secret (case-insensitive).
    2. Fallback to settings / environment variable.
    3. Return default if neither exists.
    """
    from app.models.secret import SystemSecret

    clean_key = key_name.strip().upper() if key_name else ""
    if not clean_key:
        return default

    close_db_after = False
    if db is None:
        db = SessionLocal()
        close_db_after = True

    try:
        record = (
            db.query(SystemSecret)
            .filter(SystemSecret.key_name == clean_key, SystemSecret.is_active == True)
            .first()
        )
        if record and record.encrypted_value:
            decrypted = decrypt_secret(record.encrypted_value)
            if decrypted:
                return decrypted

        # Fallback to application settings / environment variable
        fallback_val = getattr(settings, clean_key, getattr(settings, key_name, ""))
        if fallback_val:
            return str(fallback_val).strip()

        return default
    except Exception as e:
        logger.warning(f"Error querying secret '{key_name}': {e}. Falling back to settings.")
        fallback_val = getattr(settings, clean_key, getattr(settings, key_name, ""))
        return str(fallback_val).strip() if fallback_val else default
    finally:
        if close_db_after:
            db.close()
