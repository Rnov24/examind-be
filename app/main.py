import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.rate_limit import limiter, get_client_ip
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    global_exception_handler,
)
from app.api.v1.router import api_router
from app.api.v1.endpoints.proctoring_ws import router as ws_router

app = FastAPI(
    title="EXAMIND API",
    description="AI-Powered Online Examination Platform API (FastAPI + MySQL)",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS for the frontend (origins come from CORS_ORIGINS env)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http(s)?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Custom & Global Exception Handlers
app.state.limiter = limiter


async def rate_limit_handler(request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "success": False,
            "data": None,
            "message": "Terlalu banyak permintaan. Tunggu sebentar lalu coba lagi.",
            "error": {"code": "RATE_LIMITED", "details": str(exc.detail)},
        },
        headers={"Retry-After": "60"},
    )


app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# Mount uploaded files directory for visual inspection of snapshots
uploads_path = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(uploads_path, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_path), name="uploads")

# Include Routers
app.include_router(api_router)
app.include_router(ws_router)


@app.get("/health", tags=["System"])
def health_check():
    return {
        "status": "healthy",
        "service": "EXAMIND Backend API",
        "version": "1.0.1",
        "environment": settings.ENVIRONMENT,
    }


@app.get("/debug/ratelimit", include_in_schema=False)
@limiter.limit("3/minute")
def debug_ratelimit(request: Request):
    from app.api.v1.endpoints import auth as auth_module

    return {
        "client_host": request.client.host if request.client else None,
        "xff": request.headers.get("x-forwarded-for"),
        "key_used": get_client_ip(request),
        "login_is_wrapped": hasattr(auth_module.login, "__wrapped__"),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
