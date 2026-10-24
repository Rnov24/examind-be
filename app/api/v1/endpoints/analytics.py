from fastapi import APIRouter, Depends, status, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.dependencies import require_teacher
from app.core.tenant_scope import require_exam
from app.models.user import User
from app.models.exam import Exam
from app.schemas.common import ApiResponse
from app.services.analytics.item_analysis import compute_exam_analytics
from app.services.reporting.excel_exporter import generate_excel_gradebook
from app.services.reporting.pdf_exporter import generate_pdf_berita_acara

router = APIRouter(prefix="/analytics", tags=["Class Analytics & Reporting"])


@router.get("/exam/{exam_id}/items", response_model=ApiResponse[dict])
def get_exam_item_analysis(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    # 404 when the exam belongs to another school or another teacher —
    # item analysis and both exports expose every student's scores.
    exam = require_exam(db, current_user, exam_id)

    analytics_data = compute_exam_analytics(db, exam_id)
    return ApiResponse.ok(data=analytics_data, message="Analisis butir soal dan statistik kelas berhasil dihitung")


@router.get("/exam/{exam_id}/export/excel")
def export_gradebook_excel(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    # 404 when the exam belongs to another school or another teacher —
    # item analysis and both exports expose every student's scores.
    exam = require_exam(db, current_user, exam_id)

    excel_buffer = generate_excel_gradebook(db, exam_id)
    filename = f"rekap_nilai_exam_{exam_id}.xlsx"
    return StreamingResponse(
        excel_buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/exam/{exam_id}/export/pdf")
def export_berita_acara_pdf(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    # 404 when the exam belongs to another school or another teacher —
    # item analysis and both exports expose every student's scores.
    exam = require_exam(db, current_user, exam_id)

    pdf_buffer = generate_pdf_berita_acara(db, exam_id)
    filename = f"berita_acara_exam_{exam_id}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
