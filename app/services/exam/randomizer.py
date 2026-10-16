import random
import hashlib
from typing import List, Dict, Any


def get_seed(exam_id: int, student_id: int) -> int:
    seed_str = f"{exam_id}_{student_id}_examind_seed"
    # Derive an integer seed from MD5 hash
    return int(hashlib.md5(seed_str.encode("utf-8")).hexdigest(), 16) % (10**8)


def randomize_exam_package(
    questions: List[Dict[str, Any]],
    exam_id: int,
    student_id: int,
    randomize_questions: bool = True,
    randomize_options: bool = True,
) -> List[Dict[str, Any]]:
    """Deterministically shuffles questions and MCQ options per student session.

    If student refreshes, the seed is identical, resulting in exact same order.
    """
    seed_val = get_seed(exam_id, student_id)
    rng = random.Random(seed_val)

    # Shallow copy list of question items
    shuffled_questions = [dict(q) for q in questions]

    if randomize_questions:
        rng.shuffle(shuffled_questions)

    # Re-assign sequential order index for the student view
    for idx, q in enumerate(shuffled_questions, start=1):
        q["order_index"] = idx

        # If it's a multiple choice and randomize_options is on, shuffle options
        if randomize_options and q.get("options_json") and isinstance(q["options_json"], list):
            options = [dict(opt) for opt in q["options_json"]]
            # We seed per question specifically
            opt_rng = random.Random(seed_val + q.get("id", idx))
            opt_rng.shuffle(options)
            # Hide correct answer / rationale from student view payload
            clean_options = []
            for opt in options:
                clean_options.append({
                    "id": opt.get("id"),
                    "text": opt.get("text")
                })
            q["options_json"] = clean_options

    return shuffled_questions
