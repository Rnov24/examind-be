import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from sqlalchemy.orm import Session
from app.models.exam import Exam
from app.models.session import ExamSession, StudentAnswer


def generate_pdf_berita_acara(db: Session, exam_id: int) -> io.BytesIO:
    """Generates official PDF 'Berita Acara Pelaksanaan Ujian' with ReportLab."""
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    sessions = (
        db.query(ExamSession)
        .filter(ExamSession.exam_id == exam_id)
        .all()
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )
    story = []
    styles = getSampleStyleSheet()

    # Header title
    title_style = ParagraphStyle(
        name="HeaderTitle",
        parent=styles["Heading1"],
        fontSize=16,
        leading=20,
        alignment=1,  # Center
        textColor=colors.HexColor("#1E3A8A"),
    )
    story.append(Paragraph("BERITA ACARA PELAKSANAAN UJIAN ONLINE", title_style))
    story.append(Paragraph("SISTEM INFORMASI EVALUASI AKADEMIK (EXAMIND)", ParagraphStyle(name="Sub", alignment=1, fontSize=10, textColor=colors.gray)))
    story.append(Spacer(1, 15))

    # Meta table
    now_str = datetime.utcnow().strftime("%d %B %Y")
    meta_data = [
        ["Mata Pelajaran:", exam.title if exam else "-", "Tanggal Ujian:", exam.start_time.strftime("%d %B %Y") if exam else "-"],
        ["Kelas / Rombel:", exam.class_.name if exam and exam.class_ else "-", "Guru Penguji:", exam.teacher.full_name if exam and exam.teacher else "-"],
        ["Jumlah Peserta:", f"{len(sessions)} Siswa", "Tingkat Pengawasan:", exam.proctoring_level.upper() if exam else "-"],
    ]
    meta_table = Table(meta_data, colWidths=[100, 160, 110, 145])
    meta_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor("#1F2937")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 15))

    # Student Table
    table_rows = [["No", "NISN", "Nama Siswa", "Status", "Nilai Akhir", "Integritas"]]
    for idx, s in enumerate(sessions, start=1):
        table_rows.append([
            str(idx),
            s.student.identifier if s.student else "-",
            s.student.full_name if s.student else "Siswa",
            s.status.capitalize(),
            f"{float(s.total_score or 0.0):.1f}",
            f"{s.integrity_score}%",
        ])

    student_table = Table(table_rows, colWidths=[30, 85, 180, 80, 70, 70])
    student_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E40AF")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('ALIGN', (0, 1), (1, -1), 'CENTER'),
        ('ALIGN', (4, 1), (5, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(student_table)
    story.append(Spacer(1, 25))

    # Signature Block
    sig_data = [
        ["", "Mengetahui,\nGuru Pengampu / Pengawas", "", "Kepala Sekolah / Kurikulum\n"],
        ["", "\n\n______________________\n" + (exam.teacher.full_name if exam and exam.teacher else "Guru"), "", "\n\n______________________\nNIP. ........................."]
    ]
    sig_table = Table(sig_data, colWidths=[40, 200, 35, 240])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ]))
    story.append(sig_table)

    doc.build(story)
    buffer.seek(0)
    return buffer


def generate_pdf_student_result(db: Session, session_id: int) -> io.BytesIO:
    """Generates official student transcript / result sheet PDF with ReportLab."""
    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if not session:
        return io.BytesIO()

    exam = session.exam
    student = session.student

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )
    story = []
    styles = getSampleStyleSheet()

    # Header title
    title_style = ParagraphStyle(
        name="HeaderTitleStudent",
        parent=styles["Heading1"],
        fontSize=15,
        leading=18,
        alignment=1,  # Center
        textColor=colors.HexColor("#1E3A8A"),
    )
    story.append(Paragraph("LEMBAR HASIL EVALUASI UJIAN SISWA", title_style))
    story.append(Paragraph("SISTEM INFORMASI EVALUASI AKADEMIK (EXAMIND)", ParagraphStyle(name="SubStudent", alignment=1, fontSize=9, textColor=colors.gray)))
    story.append(Spacer(1, 15))

    # Meta table
    now_str = datetime.utcnow().strftime("%d %B %Y")
    submit_str = session.submit_time.strftime("%d %B %Y %H:%M") if session.submit_time else "-"
    meta_data = [
        ["Nama Siswa:", student.full_name if student else "-", "Mata Pelajaran:", exam.title if exam else "-"],
        ["NISN / ID:", student.identifier if student else "-", "Kelas:", exam.class_.name if exam and exam.class_ else "-"],
        ["Waktu Selesai:", submit_str, "Guru Pengampu:", exam.teacher.full_name if exam and exam.teacher else "-"],
    ]
    meta_table = Table(meta_data, colWidths=[90, 170, 95, 160])
    meta_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor("#1F2937")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # Status Summary Card
    total_score = float(session.total_score or 0.0)
    is_aborted = session.status == "aborted"
    status_label = "GUGUR (DISKUALIFIKASI)" if is_aborted else ("TUNTAS (KKM)" if total_score >= 75.0 else "BELUM TUNTAS")
    bg_color = colors.HexColor("#FEE2E2") if is_aborted else (colors.HexColor("#DCFCE7") if total_score >= 75.0 else colors.HexColor("#FEF3C7"))
    text_color = colors.HexColor("#991B1B") if is_aborted else (colors.HexColor("#166534") if total_score >= 75.0 else colors.HexColor("#92400E"))

    summary_data = [
        [
            Paragraph(f"<b>NILAI AKHIR: {total_score:.1f} / 100</b>", ParagraphStyle(name="ScoreBig", fontSize=12, leading=15, textColor=text_color, alignment=1)),
            Paragraph(f"<b>STATUS: {status_label}</b>", ParagraphStyle(name="StatusLabel", fontSize=9.5, leading=13, textColor=text_color, alignment=1)),
            Paragraph(f"<b>INTEGRITAS: {session.integrity_score}%</b>", ParagraphStyle(name="IntegLabel", fontSize=9.5, leading=13, textColor=text_color, alignment=1)),
        ]
    ]
    summary_table = Table(summary_data, colWidths=[175, 175, 165])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg_color),
        ('BOX', (0, 0), (-1, -1), 1, text_color),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 15))

    # Answers table
    answers = (
        db.query(StudentAnswer)
        .filter(StudentAnswer.session_id == session.id)
        .all()
    )

    ans_rows = [["No", "Tipe", "Jawaban Siswa", "Kunci / Jawaban Benar", "Nilai"]]
    for idx, a in enumerate(answers, start=1):
        q = a.question
        q_type = "PG" if q and q.question_type == "multiple_choice" else "Esai"
        student_ans = (a.student_response or "-")[:55]
        correct_ans = (q.correct_answer or "-")[:55] if q else "-"
        score_val = f"{float(a.final_score or 0.0):.1f}"

        ans_rows.append([
            str(idx),
            q_type,
            student_ans,
            correct_ans,
            score_val,
        ])

    if len(ans_rows) == 1:
        ans_rows.append(["-", "-", "Belum ada jawaban tersimpan", "-", "-"])

    ans_table = Table(ans_rows, colWidths=[25, 45, 215, 180, 50])
    ans_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8.5),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('ALIGN', (0, 1), (1, -1), 'CENTER'),
        ('ALIGN', (4, 1), (4, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(ans_table)
    story.append(Spacer(1, 20))

    # Signature Block
    sig_data = [
        ["Peserta Ujian,", "", "Mengetahui,\nGuru Pengampu"],
        [f"\n\n______________________\n{student.full_name if student else 'Siswa'}", "", f"\n\n______________________\n{exam.teacher.full_name if exam and exam.teacher else 'Guru'}"]
    ]
    sig_table = Table(sig_data, colWidths=[200, 115, 200])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
    ]))
    story.append(sig_table)

    doc.build(story)
    buffer.seek(0)
    return buffer

