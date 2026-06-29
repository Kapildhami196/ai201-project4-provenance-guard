from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import Flask, jsonify, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from services.llm_detector import LlmDetectionError, analyze_text as analyze_llm_text
from services.scoring import ScoringError, combine_signals
from services.stylometric_detector import (
    StylometricDetectionError,
    analyze_text as analyze_stylometric_text,
)

MIN_TEXT_LENGTH = 40
MAX_TEXT_LENGTH = 12_000
MIN_APPEAL_REASON_LENGTH = 20
MAX_APPEAL_REASON_LENGTH = 2_000
DATABASE_FILENAME = "provenance_guard.db"
SUBMIT_RATE_LIMIT = "10 per minute; 100 per day"

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://",
)


def utc_now() -> str:
    """Return the current UTC time in ISO-8601 format."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def get_connection(database_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection that returns rows as dictionaries."""
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    """Add one missing column when upgrading an older local database."""
    existing_columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }

    if column_name not in existing_columns:
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_definition}"
        )


def initialize_database(database_path: Path) -> None:
    """Create and safely upgrade local tables for submissions and appeals."""
    with get_connection(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS contents (
                content_id TEXT PRIMARY KEY,
                creator_id TEXT NOT NULL,
                text TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                llm_score REAL,
                llm_reasoning TEXT,
                stylometric_score REAL,
                stylometric_reasoning TEXT,
                ai_probability REAL,
                signal_agreement REAL,
                attribution TEXT NOT NULL,
                confidence REAL,
                status TEXT NOT NULL,
                appeal_reasoning TEXT,
                appealed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                content_id TEXT NOT NULL,
                creator_id TEXT NOT NULL,
                attribution TEXT,
                confidence REAL,
                llm_score REAL,
                llm_reasoning TEXT,
                stylometric_score REAL,
                stylometric_reasoning TEXT,
                ai_probability REAL,
                signal_agreement REAL,
                status TEXT NOT NULL,
                appeal_reasoning TEXT,
                appealed_at TEXT,
                FOREIGN KEY (content_id) REFERENCES contents(content_id)
            );
            """
        )

        ensure_column(connection, "contents", "llm_score", "llm_score REAL")
        ensure_column(
            connection,
            "contents",
            "llm_reasoning",
            "llm_reasoning TEXT",
        )
        ensure_column(
            connection,
            "contents",
            "stylometric_score",
            "stylometric_score REAL",
        )
        ensure_column(
            connection,
            "contents",
            "stylometric_reasoning",
            "stylometric_reasoning TEXT",
        )
        ensure_column(
            connection,
            "contents",
            "ai_probability",
            "ai_probability REAL",
        )
        ensure_column(
            connection,
            "contents",
            "signal_agreement",
            "signal_agreement REAL",
        )
        ensure_column(
            connection,
            "contents",
            "appeal_reasoning",
            "appeal_reasoning TEXT",
        )
        ensure_column(
            connection,
            "contents",
            "appealed_at",
            "appealed_at TEXT",
        )

        ensure_column(
            connection,
            "audit_events",
            "llm_score",
            "llm_score REAL",
        )
        ensure_column(
            connection,
            "audit_events",
            "llm_reasoning",
            "llm_reasoning TEXT",
        )
        ensure_column(
            connection,
            "audit_events",
            "stylometric_score",
            "stylometric_score REAL",
        )
        ensure_column(
            connection,
            "audit_events",
            "stylometric_reasoning",
            "stylometric_reasoning TEXT",
        )
        ensure_column(
            connection,
            "audit_events",
            "ai_probability",
            "ai_probability REAL",
        )
        ensure_column(
            connection,
            "audit_events",
            "signal_agreement",
            "signal_agreement REAL",
        )
        ensure_column(
            connection,
            "audit_events",
            "appeal_reasoning",
            "appeal_reasoning TEXT",
        )
        ensure_column(
            connection,
            "audit_events",
            "appealed_at",
            "appealed_at TEXT",
        )


def validate_submission_payload() -> tuple[str, str] | tuple[None, Any]:
    """Validate submission JSON and return normalized text and creator ID."""
    if not request.is_json:
        return None, (
            jsonify({"error": "Request body must be valid JSON."}),
            400,
        )

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, (
            jsonify({"error": "Request body must be a JSON object."}),
            400,
        )

    text = payload.get("text")
    creator_id = payload.get("creator_id")

    if not isinstance(text, str) or not text.strip():
        return None, (
            jsonify(
                {
                    "error": "Field 'text' is required and must be a non-empty string."
                }
            ),
            400,
        )

    if not isinstance(creator_id, str) or not creator_id.strip():
        return None, (
            jsonify(
                {
                    "error": (
                        "Field 'creator_id' is required and must be a non-empty "
                        "string."
                    )
                }
            ),
            400,
        )

    normalized_text = text.strip()
    normalized_creator_id = creator_id.strip()
    text_length = len(normalized_text)

    if text_length < MIN_TEXT_LENGTH:
        return None, (
            jsonify(
                {
                    "error": (
                        f"Field 'text' must contain at least "
                        f"{MIN_TEXT_LENGTH} non-whitespace characters."
                    ),
                    "received_length": text_length,
                }
            ),
            400,
        )

    if text_length > MAX_TEXT_LENGTH:
        return None, (
            jsonify(
                {
                    "error": (
                        f"Field 'text' must contain no more than "
                        f"{MAX_TEXT_LENGTH} characters."
                    ),
                    "received_length": text_length,
                }
            ),
            400,
        )

    return normalized_text, normalized_creator_id


def create_app() -> Flask:
    """Create and configure the Provenance Guard Flask application."""
    app = Flask(__name__)
    app.config["RATELIMIT_HEADERS_ENABLED"] = True
    limiter.init_app(app)
    database_path = Path(app.root_path) / DATABASE_FILENAME
    initialize_database(database_path)

    @app.get("/")
    def home() -> str:
        """Render the browser interface for the local prototype."""
        return render_template("index.html")

    @app.get("/health")
    def health() -> tuple[Any, int]:
        """Return a simple response proving the API is running."""
        return jsonify({"status": "ok"}), 200

    @app.post("/submit")
    @limiter.limit(SUBMIT_RATE_LIMIT)
    def submit() -> tuple[Any, int]:
        """Validate, analyze, store, and return a two-signal result."""
        validation_result = validate_submission_payload()

        if validation_result[0] is None:
            return validation_result[1]

        normalized_text, normalized_creator_id = validation_result

        try:
            llm_result = analyze_llm_text(normalized_text)
        except LlmDetectionError:
            return jsonify(
                {
                    "error": (
                        "The AI classification service is temporarily unavailable. "
                        "Please try again later."
                    )
                }
            ), 503

        try:
            stylometric_result = analyze_stylometric_text(normalized_text)
        except StylometricDetectionError:
            return jsonify(
                {
                    "error": (
                        "The local writing-pattern analysis could not process "
                        "this text."
                    )
                }
            ), 422

        try:
            decision = combine_signals(
                llm_result["llm_score"],
                stylometric_result["stylometric_score"],
            )
        except ScoringError:
            return jsonify(
                {
                    "error": (
                        "The analysis scores could not be combined safely. "
                        "Please try again later."
                    )
                }
            ), 500

        content_id = str(uuid4())
        event_id = str(uuid4())
        timestamp = utc_now()

        llm_score = llm_result["llm_score"]
        llm_reasoning = llm_result["reasoning"]
        stylometric_score = stylometric_result["stylometric_score"]
        stylometric_reasoning = stylometric_result["reasoning"]

        ai_probability = decision["ai_probability"]
        signal_agreement = decision["signal_agreement"]
        confidence = decision["confidence"]
        label = decision["label"]
        attribution = label["variant"]
        status = "classified"

        with get_connection(database_path) as connection:
            connection.execute(
                """
                INSERT INTO contents (
                    content_id,
                    creator_id,
                    text,
                    submitted_at,
                    llm_score,
                    llm_reasoning,
                    stylometric_score,
                    stylometric_reasoning,
                    ai_probability,
                    signal_agreement,
                    attribution,
                    confidence,
                    status,
                    appeal_reasoning,
                    appealed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    content_id,
                    normalized_creator_id,
                    normalized_text,
                    timestamp,
                    llm_score,
                    llm_reasoning,
                    stylometric_score,
                    stylometric_reasoning,
                    ai_probability,
                    signal_agreement,
                    attribution,
                    confidence,
                    status,
                    None,
                    None,
                ),
            )

            connection.execute(
                """
                INSERT INTO audit_events (
                    event_id,
                    event_type,
                    timestamp,
                    content_id,
                    creator_id,
                    attribution,
                    confidence,
                    llm_score,
                    llm_reasoning,
                    stylometric_score,
                    stylometric_reasoning,
                    ai_probability,
                    signal_agreement,
                    status,
                    appeal_reasoning,
                    appealed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    "submission",
                    timestamp,
                    content_id,
                    normalized_creator_id,
                    attribution,
                    confidence,
                    llm_score,
                    llm_reasoning,
                    stylometric_score,
                    stylometric_reasoning,
                    ai_probability,
                    signal_agreement,
                    status,
                    None,
                    None,
                ),
            )

        return jsonify(
            {
                "content_id": content_id,
                "creator_id": normalized_creator_id,
                "attribution": attribution,
                "confidence": confidence,
                "ai_probability": ai_probability,
                "signal_agreement": signal_agreement,
                "label": label,
                "signals": {
                    "llm": {
                        "score": llm_score,
                        "reasoning": llm_reasoning,
                        "model": llm_result["model"],
                    },
                    "stylometric": {
                        "score": stylometric_score,
                        "reasoning": stylometric_reasoning,
                        "method": stylometric_result["method"],
                        "metrics": stylometric_result["metrics"],
                    },
                },
                "status": status,
            }
        ), 201

    @app.errorhandler(429)
    def rate_limit_error(error: Any) -> tuple[Any, int]:
        """Return a clear JSON response when submit rate limiting is reached."""
        return jsonify(
            {
                "error": "Rate limit exceeded.",
                "message": (
                    "Too many submission requests were received. "
                    "Please wait before submitting again."
                ),
            }
        ), 429

    @app.post("/appeal")
    def appeal() -> tuple[Any, int]:
        """
        Store a creator appeal and move the original item to under_review.

        This prototype verifies ownership by matching creator_id. A deployed
        application would use authenticated account identity instead.
        """
        if not request.is_json:
            return jsonify({"error": "Request body must be valid JSON."}), 400

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Request body must be a JSON object."}), 400

        content_id = payload.get("content_id")
        creator_id = payload.get("creator_id")
        creator_reasoning = payload.get("creator_reasoning")

        if not isinstance(content_id, str) or not content_id.strip():
            return jsonify(
                {
                    "error": (
                        "Field 'content_id' is required and must be a non-empty "
                        "string."
                    )
                }
            ), 400

        if not isinstance(creator_id, str) or not creator_id.strip():
            return jsonify(
                {
                    "error": (
                        "Field 'creator_id' is required and must be a non-empty "
                        "string."
                    )
                }
            ), 400

        if not isinstance(creator_reasoning, str) or not creator_reasoning.strip():
            return jsonify(
                {
                    "error": (
                        "Field 'creator_reasoning' is required and must be a "
                        "non-empty string."
                    )
                }
            ), 400

        normalized_content_id = content_id.strip()
        normalized_creator_id = creator_id.strip()
        normalized_reasoning = creator_reasoning.strip()
        reasoning_length = len(normalized_reasoning)

        if reasoning_length < MIN_APPEAL_REASON_LENGTH:
            return jsonify(
                {
                    "error": (
                        f"Field 'creator_reasoning' must contain at least "
                        f"{MIN_APPEAL_REASON_LENGTH} characters."
                    ),
                    "received_length": reasoning_length,
                }
            ), 400

        if reasoning_length > MAX_APPEAL_REASON_LENGTH:
            return jsonify(
                {
                    "error": (
                        f"Field 'creator_reasoning' must contain no more than "
                        f"{MAX_APPEAL_REASON_LENGTH} characters."
                    ),
                    "received_length": reasoning_length,
                }
            ), 400

        with get_connection(database_path) as connection:
            content = connection.execute(
                """
                SELECT
                    content_id,
                    creator_id,
                    llm_score,
                    llm_reasoning,
                    stylometric_score,
                    stylometric_reasoning,
                    ai_probability,
                    signal_agreement,
                    attribution,
                    confidence,
                    status
                FROM contents
                WHERE content_id = ?
                """,
                (normalized_content_id,),
            ).fetchone()

            if content is None:
                return jsonify({"error": "Content was not found."}), 404

            if content["creator_id"] != normalized_creator_id:
                return jsonify(
                    {
                        "error": (
                            "Only the original creator may appeal this content."
                        )
                    }
                ), 403

            if content["status"] == "under_review":
                return jsonify(
                    {
                        "error": (
                            "An appeal for this content is already under review."
                        )
                    }
                ), 409

            appeal_timestamp = utc_now()
            event_id = str(uuid4())
            status = "under_review"

            connection.execute(
                """
                UPDATE contents
                SET
                    status = ?,
                    appeal_reasoning = ?,
                    appealed_at = ?
                WHERE content_id = ?
                """,
                (
                    status,
                    normalized_reasoning,
                    appeal_timestamp,
                    normalized_content_id,
                ),
            )

            connection.execute(
                """
                INSERT INTO audit_events (
                    event_id,
                    event_type,
                    timestamp,
                    content_id,
                    creator_id,
                    attribution,
                    confidence,
                    llm_score,
                    llm_reasoning,
                    stylometric_score,
                    stylometric_reasoning,
                    ai_probability,
                    signal_agreement,
                    status,
                    appeal_reasoning,
                    appealed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    "appeal",
                    appeal_timestamp,
                    normalized_content_id,
                    normalized_creator_id,
                    content["attribution"],
                    content["confidence"],
                    content["llm_score"],
                    content["llm_reasoning"],
                    content["stylometric_score"],
                    content["stylometric_reasoning"],
                    content["ai_probability"],
                    content["signal_agreement"],
                    status,
                    normalized_reasoning,
                    appeal_timestamp,
                ),
            )

        return jsonify(
            {
                "content_id": normalized_content_id,
                "status": "under_review",
                "message": (
                    "Your appeal was recorded and the content is now under "
                    "review. The original automated result remains in the "
                    "audit log."
                ),
                "appeal": {
                    "creator_reasoning": normalized_reasoning,
                    "appealed_at": appeal_timestamp,
                },
            }
        ), 201

    @app.get("/review-queue")
    def review_queue() -> tuple[Any, int]:
        """
        Return appealed content with its original result for human review.

        This endpoint is for the local prototype demonstration. A production
        version would require reviewer authentication and authorization.
        """
        with get_connection(database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    content_id,
                    creator_id,
                    text,
                    submitted_at,
                    llm_score,
                    llm_reasoning,
                    stylometric_score,
                    stylometric_reasoning,
                    ai_probability,
                    signal_agreement,
                    attribution,
                    confidence,
                    status,
                    appeal_reasoning,
                    appealed_at
                FROM contents
                WHERE status = 'under_review'
                ORDER BY appealed_at DESC
                LIMIT 50
                """
            ).fetchall()

        return jsonify({"items": [dict(row) for row in rows]}), 200

    @app.get("/log")
    def get_log() -> tuple[Any, int]:
        """Return recent structured audit events for project demonstration."""
        with get_connection(database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    event_id,
                    event_type,
                    timestamp,
                    content_id,
                    creator_id,
                    attribution,
                    confidence,
                    llm_score,
                    llm_reasoning,
                    stylometric_score,
                    stylometric_reasoning,
                    ai_probability,
                    signal_agreement,
                    status,
                    appeal_reasoning,
                    appealed_at
                FROM audit_events
                ORDER BY timestamp DESC, event_id DESC
                LIMIT 50
                """
            ).fetchall()

        return jsonify({"entries": [dict(row) for row in rows]}), 200

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
