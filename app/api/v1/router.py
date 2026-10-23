from fastapi import APIRouter
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.academic import router as academic_router
from app.api.v1.endpoints.questions import router as questions_router
from app.api.v1.endpoints.ai import router as ai_router
from app.api.v1.endpoints.exams import router as exams_router
from app.api.v1.endpoints.student_exam import router as student_router
from app.api.v1.endpoints.proctoring import router as proctoring_router
from app.api.v1.endpoints.grading import router as grading_router
from app.api.v1.endpoints.analytics import router as analytics_router
from app.api.v1.endpoints.admin import router as admin_router
from app.api.v1.endpoints.superadmin import router as superadmin_router
from app.api.v1.endpoints.public import router as public_router
from app.api.v1.endpoints.notifications import router as notifications_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(academic_router)
api_router.include_router(questions_router)
api_router.include_router(ai_router)
api_router.include_router(exams_router)
api_router.include_router(student_router)
api_router.include_router(proctoring_router)
api_router.include_router(grading_router)
api_router.include_router(analytics_router)
api_router.include_router(admin_router)
api_router.include_router(superadmin_router)
api_router.include_router(public_router)
api_router.include_router(notifications_router)

