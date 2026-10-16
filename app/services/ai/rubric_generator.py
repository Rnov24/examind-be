from typing import Dict, Any


def generate_4d_rubric(prompt: str, subject: str = "Umum") -> Dict[str, Any]:
    """Generates standard 4-dimensional essay rubric compliant with SRS/QGEN-003.

    1. dimension_1_concept (40%)
    2. dimension_2_argument (30%)
    3. dimension_3_terminology (15%)
    4. dimension_4_clarity (15%)
    Total = 100%
    """
    return {
        "dimension_1_concept": {
            "max": 40.0,
            "weight_pct": 40,
            "criteria": f"Penguasaan konsep inti dan esensi topik terkait: {prompt[:80]}...",
        },
        "dimension_2_argument": {
            "max": 30.0,
            "weight_pct": 30,
            "criteria": "Kelengkapan bukti, perbandingan analitis, dan alur penalaran logika",
        },
        "dimension_3_terminology": {
            "max": 15.0,
            "weight_pct": 15,
            "criteria": f"Ketepatan penggunaan kosakata dan istilah teknis baku bidang {subject}",
        },
        "dimension_4_clarity": {
            "max": 15.0,
            "weight_pct": 15,
            "criteria": "Runtutan paragraf, kejelasan bahasa, dan kaidah tata bahasa Indonesia yang baik",
        },
    }
