from __future__ import annotations

from typing import Any


LLM_WEIGHT = 0.65
STYLOMETRIC_WEIGHT = 0.35


class ScoringError(ValueError):
    """Raised when detector scores cannot be combined safely."""


def _validate_score(score: float, score_name: str) -> float:
    """Validate that one detector score is a number from 0.0 through 1.0."""
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ScoringError(f"{score_name} must be a number.")

    normalized_score = float(score)

    if not 0.0 <= normalized_score <= 1.0:
        raise ScoringError(f"{score_name} must be between 0.0 and 1.0.")

    return normalized_score


def choose_label(ai_probability: float, confidence: float) -> dict[str, str]:
    """
    Choose the final transparency label.

    A strong directional probability is not enough by itself. The two signals
    must also agree enough for the result to receive a likely-AI or
    likely-human label.
    """
    if ai_probability >= 0.75 and confidence >= 0.70:
        return {
            "variant": "likely_ai",
            "title": "AI-generated content likely",
            "message": (
                "Our independent signals strongly indicate AI assistance or "
                "generation. This is an automated assessment, not proof of "
                "authorship, and the creator may appeal."
            ),
        }

    if ai_probability <= 0.25 and confidence >= 0.70:
        return {
            "variant": "likely_human",
            "title": "Likely human-written",
            "message": (
                "Our independent signals strongly indicate this text appears "
                "likely human-written. This automated assessment is not proof "
                "of authorship."
            ),
        }

    return {
        "variant": "uncertain",
        "title": "Origin uncertain",
        "message": (
            "The available signals do not support a reliable AI-versus-human "
            "conclusion. No definitive attribution label is shown. The creator "
            "may appeal."
        ),
    }


def combine_signals(llm_score: float, stylometric_score: float) -> dict[str, Any]:
    """
    Combine two independent heuristic signals.

    The returned values are not proof of authorship. Confidence becomes higher
    only when the combined direction is strong and the signals agree.
    """
    normalized_llm_score = _validate_score(llm_score, "llm_score")
    normalized_stylometric_score = _validate_score(
        stylometric_score,
        "stylometric_score",
    )

    ai_probability = (
        (LLM_WEIGHT * normalized_llm_score)
        + (STYLOMETRIC_WEIGHT * normalized_stylometric_score)
    )

    signal_agreement = 1.0 - abs(
        normalized_llm_score - normalized_stylometric_score
    )

    direction_strength = abs(ai_probability - 0.50) * 2

    confidence = 0.50 + (
        0.50 * direction_strength * signal_agreement
    )

    ai_probability = round(ai_probability, 3)
    signal_agreement = round(signal_agreement, 3)
    confidence = round(confidence, 3)

    label = choose_label(ai_probability, confidence)

    return {
        "ai_probability": ai_probability,
        "confidence": confidence,
        "signal_agreement": signal_agreement,
        "label": label,
    }
