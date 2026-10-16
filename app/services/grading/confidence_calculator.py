import math
from typing import Dict, Any, List, Tuple


def calculate_ai_confidence(
    semantic_score: float,
    dimension_scores: Dict[str, float],
    max_dimension_scores: Dict[str, float],
    keyword_ratio: float,
) -> Tuple[float, str]:
    """Calculates AI Confidence Level C_ai based on:

    C_ai = 0.5 * S_semantic + 0.3 * (1 - sigma_subscores) + 0.2 * P_keyword

    Returns (confidence_score, confidence_level: 'high' | 'medium' | 'low')
    """
    # 1. Normalized semantic score [0.0, 1.0]
    s_semantic = max(0.0, min(1.0, semantic_score))

    # 2. Normalized dimension variance
    normalized_scores = []
    for dim, score in dimension_scores.items():
        max_s = max_dimension_scores.get(dim, 100.0)
        norm = score / max_s if max_s > 0 else 0.0
        normalized_scores.append(norm)

    if len(normalized_scores) > 1:
        mean_score = sum(normalized_scores) / len(normalized_scores)
        variance = sum((x - mean_score) ** 2 for x in normalized_scores) / len(normalized_scores)
        sigma = math.sqrt(variance)
    else:
        sigma = 0.0

    consistency_factor = max(0.0, min(1.0, 1.0 - sigma))

    # 3. Keyword ratio [0.0, 1.0]
    p_keyword = max(0.0, min(1.0, keyword_ratio))

    # Composite index
    c_ai = (0.5 * s_semantic) + (0.3 * consistency_factor) + (0.2 * p_keyword)
    c_ai = round(c_ai, 3)

    if c_ai >= 0.85:
        level = "high"
    elif c_ai >= 0.70:
        level = "medium"
    else:
        level = "low"

    return c_ai, level
