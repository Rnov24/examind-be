from typing import Generic, TypeVar, Optional, Any
from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    details: Optional[Any] = None


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: Optional[T] = None
    message: str = "Sukses"
    error: Optional[ErrorDetail] = None

    @classmethod
    def ok(cls, data: Optional[T] = None, message: str = "Sukses"):
        return cls(success=True, data=data, message=message, error=None)

    @classmethod
    def created(cls, data: Optional[T] = None, message: str = "Berhasil dibuat"):
        return cls(success=True, data=data, message=message, error=None)

    @classmethod
    def fail(cls, message: str, code: str = "ERROR", details: Optional[Any] = None):
        return cls(
            success=False,
            data=None,
            message=message,
            error=ErrorDetail(code=code, details=details or message),
        )
