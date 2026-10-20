import math
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.exam import Exam, ExamQuestion
from app.models.session import ExamSession, StudentAnswer


def compute_exam_analytics(db: Session, exam_id: int) -> Dict[str, Any]:
    """Computes full item analysis (P-Index & D-Index) and class summary statistics."""
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        return {}

    sessions = (
        db.query(ExamSession)
        .filter(ExamSession.exam_id == exam_id, ExamSession.status.in_(["graded", "submitted"]))
        .order_by(ExamSession.total_score.desc())
        .all()
    )

    total_examinees = len(sessions)
    if total_examinees == 0:
        return {
            "total_examinees": 0,
            "average_score": 0.0,
            "highest_score": 0.0,
            "lowest_score": 0.0,
            "std_deviation": 0.0,
            "pass_rate": 0.0,
            "score_distribution": {"0-49": 0, "50-69": 0, "70-84": 0, "85-100": 0},
            "item_analysis": [],
        }

    scores = [float(s.total_score or 0.0) for s in sessions]
    avg_score = round(sum(scores) / total_examinees, 2)
    highest = max(scores)
    lowest = min(scores)

    # Standard deviation
    var = sum((x - avg_score) ** 2 for x in scores) / total_examinees
    std_dev = round(math.sqrt(var), 2)

    # Pass rate (assuming passing grade >= 70.0)
    passed = len([s for s in scores if s >= 70.0])
    pass_rate = round((passed / total_examinees) * 100.0, 1)

    # Buckets
    buckets = {"0-49": 0, "50-69": 0, "70-84": 0, "85-100": 0}
    for s in scores:
        if s < 50:
            buckets["0-49"] += 1
        elif s < 70:
            buckets["50-69"] += 1
        elif s < 85:
            buckets["70-84"] += 1
        else:
            buckets["85-100"] += 1

    # Item Analysis (Upper 27% and Lower 27% groups)
    group_size = max(1, int(round(total_examinees * 0.27)))
    upper_sessions = {s.id for s in sessions[:group_size]}
    lower_sessions = {s.id for s in sessions[-group_size:]}
    session_ids = [s.id for s in sessions]

    # One query for ALL answers of this exam (needed columns only), grouped by question in Python.
    all_answers = (
        db.query(
            StudentAnswer.question_id,
            StudentAnswer.session_id,
            StudentAnswer.is_correct,
            StudentAnswer.final_score,
        )
        .filter(StudentAnswer.session_id.in_(session_ids))
        .all()
    )
    answers_by_question: Dict[int, List[Any]] = {}
    for a in all_answers:
        answers_by_question.setdefault(a.question_id, []).append(a)

    item_analysis_results = []
    for eq in exam.exam_questions:
        q = eq.question
        if not q:
            continue

        q_id = q.id
        allocated = float(eq.allocated_points)

        q_answers = answers_by_question.get(q_id, [])

        correct_count = 0
        upper_correct = 0
        lower_correct = 0

        for a in q_answers:
            # Full credit or PG is_correct
            is_full = bool(a.is_correct) or (float(a.final_score or 0.0) >= allocated * 0.7)
            if is_full:
                correct_count += 1
                if a.session_id in upper_sessions:
                    upper_correct += 1
                elif a.session_id in lower_sessions:
                    lower_correct += 1

        # Difficulty Index P = B / N
        p_index = round(correct_count / total_examinees, 2)
        if p_index < 0.30:
            diff_label = "Sukar"
        elif p_index <= 0.70:
            diff_label = "Sedang"
        else:
            diff_label = "Mudah"

        # Discrimination Index D = (Ba - Bb) / N_group
        d_index = round((upper_correct - lower_correct) / group_size, 2)
        if d_index < 0.0:
            disc_label = "Perlu Direvisi (Negatif)"
            recommendation = "Cacat / Membingungkan (Kunci atau Soal Salah)"
        elif d_index < 0.20:
            disc_label = "Jelek"
            recommendation = "Perbaiki Opsi Pengecoh"
        elif d_index < 0.40:
            disc_label = "Cukup"
            recommendation = "Dapat Diterima dengan Sedikit Revisi"
        elif d_index < 0.70:
            disc_label = "Baik"
            recommendation = "Butir Soal Baik & Layak Disimpan"
        else:
            disc_label = "Sangat Baik"
            recommendation = "Butir Soal Sangat Membedakan Siswa Mahir"

        item_analysis_results.append({
            "order_index": eq.order_index,
            "question_id": q.id,
            "prompt_snippet": q.prompt[:80] + "..." if len(q.prompt) > 80 else q.prompt,
            "question_type": q.question_type,
            "allocated_points": allocated,
            "p_index": p_index,
            "difficulty_label": diff_label,
            "d_index": d_index,
            "discrimination_label": disc_label,
            "recommendation": recommendation,
        })

    return {
        "total_examinees": total_examinees,
        "average_score": avg_score,
        "highest_score": highest,
        "lowest_score": lowest,
        "std_deviation": std_dev,
        "pass_rate": pass_rate,
        "score_distribution": buckets,
        "item_analysis": item_analysis_results,
    }
