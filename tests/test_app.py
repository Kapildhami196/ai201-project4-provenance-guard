from __future__ import annotations

from pathlib import Path

import pytest

import app as app_module


AI_LLM_RESULT = {
    "llm_score": 0.90,
    "reasoning": "Test LLM signal found generic formal patterns.",
    "model": "test-model",
}

AI_STYLOMETRIC_RESULT = {
    "stylometric_score": 0.85,
    "reasoning": "Test local signal found repetitive formal patterns.",
    "method": "test-stylometric-method",
    "metrics": {
        "word_count": 50,
        "sentence_count": 4,
    },
}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Create an isolated app with a temporary SQLite database.

    Detector functions are replaced with stable test results so these tests
    never call Groq or require an API key.
    """
    test_database = tmp_path / "test_provenance_guard.db"

    monkeypatch.setattr(
        app_module,
        "DATABASE_FILENAME",
        str(test_database),
    )
    monkeypatch.setattr(
        app_module,
        "analyze_llm_text",
        lambda text: AI_LLM_RESULT,
    )
    monkeypatch.setattr(
        app_module,
        "analyze_stylometric_text",
        lambda text: AI_STYLOMETRIC_RESULT,
    )

    previous_limiter_state = app_module.limiter.enabled
    app_module.limiter.enabled = False

    test_app = app_module.create_app()
    test_app.config["TESTING"] = True

    with test_app.test_client() as test_client:
        yield test_client

    app_module.limiter.enabled = previous_limiter_state


def submit_test_content(client):
    response = client.post(
        "/submit",
        json={
            "creator_id": "test-creator",
            "text": (
                "This is a sufficiently long test submission with formal language "
                "that allows the two-signal provenance workflow to run safely."
            ),
        },
    )

    assert response.status_code == 201
    return response.get_json()


def test_submit_returns_two_signal_result(client) -> None:
    result = submit_test_content(client)

    assert result["status"] == "classified"
    assert result["attribution"] == "likely_ai"
    assert result["label"]["variant"] == "likely_ai"
    assert result["confidence"] >= 0.70
    assert result["signals"]["llm"]["score"] == 0.90
    assert result["signals"]["stylometric"]["score"] == 0.85


def test_submit_rejects_missing_creator_id(client) -> None:
    response = client.post(
        "/submit",
        json={
            "text": "This test text is long enough but does not include a creator ID.",
        },
    )

    assert response.status_code == 400
    assert "creator_id" in response.get_json()["error"]


def test_submit_rejects_too_short_text(client) -> None:
    response = client.post(
        "/submit",
        json={
            "creator_id": "test-creator",
            "text": "Too short",
        },
    )

    assert response.status_code == 400
    assert response.get_json()["received_length"] == 9


def test_creator_can_appeal_own_content(client) -> None:
    submission = submit_test_content(client)

    appeal_response = client.post(
        "/appeal",
        json={
            "content_id": submission["content_id"],
            "creator_id": "test-creator",
            "creator_reasoning": (
                "I wrote this text myself and used formal language because it was "
                "prepared for an academic assignment."
            ),
        },
    )

    appeal_result = appeal_response.get_json()

    assert appeal_response.status_code == 201
    assert appeal_result["status"] == "under_review"

    review_queue = client.get("/review-queue").get_json()

    assert len(review_queue["items"]) == 1
    assert review_queue["items"][0]["status"] == "under_review"
    assert review_queue["items"][0]["appeal_reasoning"].startswith(
        "I wrote this text myself"
    )


def test_other_creator_cannot_appeal_content(client) -> None:
    submission = submit_test_content(client)

    response = client.post(
        "/appeal",
        json={
            "content_id": submission["content_id"],
            "creator_id": "different-creator",
            "creator_reasoning": (
                "I am trying to appeal this content even though I am not the "
                "original creator."
            ),
        },
    )

    assert response.status_code == 403
    assert "original creator" in response.get_json()["error"]


def test_duplicate_active_appeal_is_rejected(client) -> None:
    submission = submit_test_content(client)

    appeal_payload = {
        "content_id": submission["content_id"],
        "creator_id": "test-creator",
        "creator_reasoning": (
            "I wrote this myself and want a reviewer to consider the context "
            "of the formal wording."
        ),
    }

    first_response = client.post("/appeal", json=appeal_payload)
    second_response = client.post("/appeal", json=appeal_payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert "already under review" in second_response.get_json()["error"]


def test_audit_log_records_submission_and_appeal(client) -> None:
    submission = submit_test_content(client)

    client.post(
        "/appeal",
        json={
            "content_id": submission["content_id"],
            "creator_id": "test-creator",
            "creator_reasoning": (
                "I wrote this text myself and request human review because "
                "formal writing style influenced the result."
            ),
        },
    )

    log_result = client.get("/log").get_json()
    event_types = [entry["event_type"] for entry in log_result["entries"]]

    assert "submission" in event_types
    assert "appeal" in event_types
