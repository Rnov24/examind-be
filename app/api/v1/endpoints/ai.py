import logging
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, status
from app.core.exceptions import AppException
from app.core.dependencies import require_teacher
from app.models.user import User
from app.schemas.question import AIGenerateRequest, AIGenerateData
from app.schemas.common import ApiResponse
from app.services.ai import get_ai_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI Engine & Generation"])


@router.post("/generate-questions", response_model=ApiResponse[AIGenerateData])
def generate_questions(
    request: AIGenerateRequest,
    current_user: User = Depends(require_teacher),
):
    ai_service = get_ai_service()
    data = ai_service.generate_questions(request)
    return ApiResponse.ok(data=data, message="Draft soal berhasil di-generate oleh AI")


@router.post("/extract-and-generate", response_model=ApiResponse[AIGenerateData])
async def extract_and_generate(
    file: UploadFile = File(...),
    subject: str = Form("Umum"),
    grade_level: str = Form("12"),
    mcq_count: int = Form(5),
    essay_count: int = Form(2),
    difficulty: str = Form("medium"),
    current_user: User = Depends(require_teacher),
):
    contents = await file.read()
    extracted_text = ""
    filename = file.filename.lower() if file.filename else ""

    if filename.endswith(".pdf"):
        try:
            import io
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(contents))
            for page in reader.pages:
                extracted_text += page.extract_text() or ""
        except Exception:
            extracted_text = contents.decode("utf-8", errors="ignore")
    else:
        extracted_text = contents.decode("utf-8", errors="ignore")

    topic_summary = extracted_text[:2000] if extracted_text else "Materi Terunggah"

    req = AIGenerateRequest(
        subject=subject,
        topic_content=topic_summary,
        grade_level=grade_level,
        mcq_count=mcq_count,
        essay_count=essay_count,
        difficulty=difficulty,
    )
    ai_service = get_ai_service()
    data = ai_service.generate_questions(req)
    return ApiResponse.ok(data=data, message="Soal berhasil diekstrak dan di-generate dari dokumen")


from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.core.config import settings
from app.services.ai.retrieval import build_scoped_user_context, build_question_explanation_context
from app.services.ai.safety import check_safety_guardrails


class AssistantChatRequest(BaseModel):
    message: str = Field(..., description="Pesan pertanyaan dari pengguna ke AI Assistant")
    history: Optional[List[Dict[str, str]]] = Field(default=[], description="Riwayat percakapan sebelumnya")
    context: Optional[str] = Field(None, description="Konteks halaman atau materi terkait")
    api_key: Optional[str] = Field(None, description="Google Gemini API key opsional dari client")


class AssistantChatResponse(BaseModel):
    reply: str
    provider: str


@router.post("/assistant/chat", response_model=ApiResponse[AssistantChatResponse])
def chat_with_assistant(
    request: AssistantChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Safety Guardrail Check
    is_safe, refusal = check_safety_guardrails(request.message)
    if not is_safe:
        return ApiResponse.ok(
            data=AssistantChatResponse(reply=refusal or "", provider="safety_guardrail"),
            message="Permintaan dicegah oleh kebijakan keamanan EXAMIND",
        )

    try:
        ai_service = get_ai_service()
        scoped_context = build_scoped_user_context(user=current_user, db=db, query=request.message)

        if hasattr(ai_service, "chat_assistant"):
            reply = ai_service.chat_assistant(
                message=request.message,
                history=request.history,
                context=request.context,
                scoped_context=scoped_context,
                api_key=request.api_key,
            )
        else:
            reply = "Halo! Saya siap membantu Anda dalam penyusunan soal dan evaluasi pembelajaran."
    except Exception as e:
        logger.error(f"[chat_with_assistant] Exception occurred: {e}", exc_info=True)
        reply = (
            f"Halo {current_user.full_name or 'Pengguna'}! Saya asisten pintar EXAMIND. "
            f"Sistem sedang menyinkronkan data Anda. Silakan tanyakan seputar materi ujian atau panduan belajar."
        )

    return ApiResponse.ok(
        data=AssistantChatResponse(reply=reply, provider=settings.AI_PROVIDER),
        message="Respon AI Assistant berhasil didapatkan",
    )


class QuestionExplanationChatRequest(BaseModel):
    exam_id: int = Field(..., description="ID Ujian terkait")
    question_id: int = Field(..., description="ID Butir Soal terkait")
    message: str = Field(..., description="Pertanyaan siswa mengenai butir soal")
    history: Optional[List[Dict[str, str]]] = Field(default=[], description="Riwayat percakapan tutor sebelumnya")
    api_key: Optional[str] = Field(None, description="Google Gemini API key opsional")


class QuestionExplanationChatResponse(BaseModel):
    reply: str
    question_id: int
    exam_id: int
    provider: str


@router.post("/question-explanation/chat", response_model=ApiResponse[QuestionExplanationChatResponse])
def chat_question_explanation(
    request: QuestionExplanationChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Safety Guardrail Check
    is_safe, refusal = check_safety_guardrails(request.message)
    if not is_safe:
        return ApiResponse.ok(
            data=QuestionExplanationChatResponse(
                reply=refusal or "",
                question_id=request.question_id,
                exam_id=request.exam_id,
                provider="safety_guardrail",
            ),
            message="Permintaan dicegah oleh kebijakan keamanan EXAMIND",
        )

    try:
        question_context = build_question_explanation_context(
            exam_id=request.exam_id,
            question_id=request.question_id,
            user=current_user,
            db=db,
        )

        ai_service = get_ai_service()
        if hasattr(ai_service, "chat_question_explanation"):
            reply = ai_service.chat_question_explanation(
                question_context=question_context,
                message=request.message,
                history=request.history,
                api_key=request.api_key,
            )
        else:
            reply = f"Kunci jawaban resmi untuk butir soal ini adalah '{question_context.get('correct_answer')}'. {question_context.get('explanation') or ''}"
    except AppException as ae:
        raise ae
    except Exception as e:
        logger.error(f"[chat_question_explanation] Exception occurred: {e}", exc_info=True)
        reply = "Tutor AI sedang menelaah butir soal ini. Pastikan Anda telah menyelesaikan sesi ujian untuk meninjau seluruh pembahasan konsep."

    return ApiResponse.ok(
        data=QuestionExplanationChatResponse(
            reply=reply,
            question_id=request.question_id,
            exam_id=request.exam_id,
            provider=settings.AI_PROVIDER,
        ),
        message="Penjelasan tutor AI untuk butir soal berhasil didapatkan",
    )


class DecisionGradePreviewRequest(BaseModel):
    prompt: str = Field(..., description="Pertanyaan soal")
    student_answer: str = Field(..., description="Jawaban siswa yang akan dinilai")
    ideal_answer: Optional[str] = Field(None, description="Kunci jawaban atau acuan ideal")
    ref_points: Optional[List[Dict[str, Any]]] = Field(None, description="Daftar kriteria acuan atomik")
    allocated_points: float = Field(10.0, description="Bobot poin maksimal butir soal")
    api_key: Optional[str] = Field(None, description="OpenRouter API Key opsional")


DecisionGradePreviewRequest.model_rebuild()


@router.post("/decisions/grade-preview")
def preview_decision_grading(
    request: DecisionGradePreviewRequest,
    current_user: User = Depends(get_current_active_user),
):
    from app.services.ai.respan_grader import get_respan_grader

    grader = get_respan_grader()
    rubric = {"ref_points": request.ref_points} if request.ref_points else {}

    res = grader.grade_short_answer(
        prompt=request.prompt,
        rubric=rubric,
        ideal_answer=request.ideal_answer or "",
        student_answer=request.student_answer,
        allocated_points=request.allocated_points,
        custom_key=request.api_key,
    )

    return ApiResponse.ok(
        data=res,
        message="Evaluasi Respan Span-01 Lite berhasil diproses (Output: 0 tokens)",
    )


