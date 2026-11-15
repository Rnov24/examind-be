import logging
from typing import Any, Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# Generic 5xx body: raw exception text (SQL statements, DB driver errors)
# must never reach the client. The real exception is logged server-side.
GENERIC_500_MESSAGE = "Terjadi kesalahan internal pada server."


class AppException(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        error_code: str = "BAD_REQUEST",
        details: Optional[Any] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details
        super().__init__(message)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "data": None,
            "message": exc.message,
            "error": {
                "code": exc.error_code,
                "details": exc.details if exc.details is not None else exc.message,
            },
        },
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    error_code = "HTTP_ERROR"
    detail = str(exc.detail)
    if exc.status_code == 401:
        error_code = "UNAUTHORIZED"
    elif exc.status_code == 403:
        error_code = "FORBIDDEN"
    elif exc.status_code == 404:
        error_code = "NOT_FOUND"
    elif exc.status_code == 405:
        error_code = "METHOD_NOT_ALLOWED"
    elif exc.status_code >= 500:
        error_code = "INTERNAL_SERVER_ERROR"
        # 5xx detail is developer-supplied and could embed raw DB/driver
        # text; never echo it. Log it server-side instead.
        logger.exception(
            "HTTP %s on %s %s: %s", exc.status_code, request.method, request.url.path, exc.detail
        )
        detail = GENERIC_500_MESSAGE

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "data": None,
            "message": detail,
            "error": {
                "code": error_code,
                "details": detail,
            },
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Format validation errors cleanly
    details = []
    for err in exc.errors():
        loc = " -> ".join([str(l) for l in err.get("loc", [])])
        msg = err.get("msg", "Invalid value")
        details.append(f"{loc}: {msg}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "data": None,
            "message": "Validasi data request gagal. Mohon periksa kembali input Anda.",
            "error": {
                "code": "VALIDATION_ERROR",
                "details": "; ".join(details) if details else "Validasi data request gagal.",
            },
        },
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log the real exception server-side; the client only ever sees the
    # generic message (str(exc) used to leak raw SQL + DB driver text).
    logger.exception(
        "Unhandled exception on %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "data": None,
            "message": GENERIC_500_MESSAGE,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "details": GENERIC_500_MESSAGE,
            },
        },
    )
