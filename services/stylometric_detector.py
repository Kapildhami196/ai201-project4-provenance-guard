from __future__ import annotations

import re
from collections import Counter
from statistics import pstdev
from typing import Any

GENERIC_TRANSITIONS = (
    "additionally",
    "consequently",
    "furthermore",
    "however",
    "in conclusion",
    "in summary",
    "moreover",
    "therefore",
)

FORMAL_PATTERNS = (
    "it is important to note",
    "it is essential to",
    "it is crucial to",
    "plays a significant role",
    "transformative paradigm shift",
    "stakeholders",
    "various sectors",
    "must be considered carefully",
    "ethical implications",
)

WORD_PATTERN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
SENTENCE_PATTERN = re.compile(r"[^.!?]+[.!?]?")


class StylometricDetectionError(ValueError):
    """Raised when text cannot be analyzed by the local detector."""


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    """Keep a numeric value inside the requested range."""
    return max(minimum, min(value, maximum))


def analyze_text(text: str) -> dict[str, Any]:
    """
    Return one cautious, local stylometric signal.

    This is a heuristic pattern score, not proof of authorship.
    Higher values mean the text contains more patterns commonly associated
    with generic or AI-assisted writing.
    """
    if not isinstance(text, str) or not text.strip():
        raise StylometricDetectionError("Text must be a non-empty string.")

    normalized_text = " ".join(text.lower().split())
    words = WORD_PATTERN.findall(normalized_text)
    sentences = [
        sentence.strip()
        for sentence in SENTENCE_PATTERN.findall(text)
        if sentence.strip()
    ]

    if len(words) < 8:
        raise StylometricDetectionError(
            "Text must contain at least eight words for stylometric analysis."
        )

    sentence_lengths = [
        len(WORD_PATTERN.findall(sentence))
        for sentence in sentences
        if WORD_PATTERN.findall(sentence)
    ]

    if not sentence_lengths:
        raise StylometricDetectionError(
            "Text did not contain enough sentence information for analysis."
        )

    word_count = len(words)
    sentence_count = len(sentence_lengths)
    unique_word_count = len(set(words))
    lexical_diversity = unique_word_count / word_count
    average_sentence_length = sum(sentence_lengths) / sentence_count

    if sentence_count > 1 and average_sentence_length > 0:
        sentence_length_variation = pstdev(sentence_lengths) / average_sentence_length
        uniform_sentence_score = 1.0 - clamp(sentence_length_variation)
    else:
        sentence_length_variation = 0.0
        uniform_sentence_score = 0.50

    transition_count = sum(
        normalized_text.count(phrase) for phrase in GENERIC_TRANSITIONS
    )
    formal_pattern_count = sum(
        normalized_text.count(phrase) for phrase in FORMAL_PATTERNS
    )

    transition_score = clamp(transition_count / 3)
    formal_pattern_score = clamp(formal_pattern_count / 3)

    repetition_score = clamp((0.62 - lexical_diversity) / 0.30)

    evidence_score = (
        (0.30 * transition_score)
        + (0.30 * formal_pattern_score)
        + (0.20 * uniform_sentence_score)
        + (0.20 * repetition_score)
    )

    reliability = clamp(sentence_count / 4)
    stylometric_score = 0.50 + ((evidence_score - 0.50) * reliability)
    stylometric_score = round(clamp(stylometric_score), 3)

    reasons: list[str] = []

    if transition_count > 0:
        reasons.append(
            f"found {transition_count} generic transition phrase(s)"
        )

    if formal_pattern_count > 0:
        reasons.append(
            f"found {formal_pattern_count} generic formal phrase(s)"
        )

    if uniform_sentence_score >= 0.75 and sentence_count >= 3:
        reasons.append("sentence lengths are relatively uniform")

    if repetition_score >= 0.50:
        reasons.append("vocabulary repetition is relatively high")

    if not reasons:
        reasons.append("no strong local stylometric pattern was detected")

    return {
        "stylometric_score": stylometric_score,
        "reasoning": "; ".join(reasons) + ".",
        "method": "local_stylometric_heuristics_v1",
        "metrics": {
            "word_count": word_count,
            "sentence_count": sentence_count,
            "average_sentence_length": round(average_sentence_length, 2),
            "sentence_length_variation": round(sentence_length_variation, 3),
            "lexical_diversity": round(lexical_diversity, 3),
            "generic_transition_count": transition_count,
            "formal_pattern_count": formal_pattern_count,
        },
    }
