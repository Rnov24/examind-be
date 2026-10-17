from typing import Generic, TypeVar, Optional, Any, List
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


class PaginatedResponse(BaseModel, Generic[T]):
    success: bool = True
    data: List[T] = []
    page: int = 1
    page_size: int = 20
    total: int = 0
    total_pages: int = 0
    message: str = "Sukses"
    error: Optional[ErrorDetail] = None

    @classmethod
    def ok(
        cls,
        data: List[T],
        page: int = 1,
        page_size: int = 20,
        total: int = 0,
        message: str = "Sukses",
    ):
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(
            success=True,
            data=data,
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            message=message,
            error=None,
        )

