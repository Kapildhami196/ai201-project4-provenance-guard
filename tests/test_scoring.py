import pytest

from services.scoring import ScoringError, combine_signals


def test_strong_ai_agreement_returns_likely_ai() -> None:
    result = combine_signals(
        llm_score=0.95,
        stylometric_score=0.90,
    )

    assert result["ai_probability"] == 0.932
    assert result["confidence"] == 0.911
    assert result["label"]["variant"] == "likely_ai"
    assert result["label"]["title"] == "AI-generated content likely"


def test_strong_human_agreement_returns_likely_human() -> None:
    result = combine_signals(
        llm_score=0.05,
        stylometric_score=0.10,
    )

    assert result["ai_probability"] == 0.068
    assert result["confidence"] == 0.911
    assert result["label"]["variant"] == "likely_human"
    assert result["label"]["title"] == "Likely human-written"


def test_conflicting_signals_return_uncertain() -> None:
    result = combine_signals(
        llm_score=0.90,
        stylometric_score=0.10,
    )

    assert result["ai_probability"] == 0.62
    assert result["signal_agreement"] == 0.20
    assert result["confidence"] == 0.524
    assert result["label"]["variant"] == "uncertain"
    assert result["label"]["title"] == "Origin uncertain"


def test_middle_scores_return_uncertain() -> None:
    result = combine_signals(
        llm_score=0.60,
        stylometric_score=0.55,
    )

    assert result["label"]["variant"] == "uncertain"
    assert result["confidence"] < 0.70


@pytest.mark.parametrize(
    ("llm_score", "stylometric_score"),
    [
        (-0.01, 0.50),
        (0.50, 1.01),
        ("not-a-number", 0.50),
        (0.50, None),
        (True, 0.50),
    ],
)
def test_invalid_scores_raise_scoring_error(
    llm_score: object,
    stylometric_score: object,
) -> None:
    with pytest.raises(ScoringError):
        combine_signals(
            llm_score=llm_score,  # type: ignore[arg-type]
            stylometric_score=stylometric_score,  # type: ignore[arg-type]
        )
