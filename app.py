from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import Flask, jsonify, request

MIN_TEXT_LENGTH = 40
MAX_TEXT_LENGTH = 12_000
DATABASE_FILENAME = "provenance_guard.db"


def utc_now() -> str:
    """Return the current UTC time in ISO-8601 format."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def get_connection(database_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection that returns rows as dictionaries."""
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(database_path: Path) -> None:
    """Create local tables required for submissions and audit events."""
    with get_connection(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS contents (
                content_id TEXT PRIMARY KEY,
                creator_id TEXT NOT NULL,
                text TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                attribution TEXT NOT NULL,
                confidence REAL,
                status TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                content_id TEXT NOT NULL,
                creator_id TEXT NOT NULL,
                attribution TEXT,
                confidence REAL,
                status TEXT NOT NULL,
                FOREIGN KEY (content_id) REFERENCES contents(content_id)
            );
            """
        )


def create_app() -> Flask:
    """Create and configure the Provenance Guard Flask application."""
    app = Flask(__name__)
    database_path = Path(app.root_path) / DATABASE_FILENAME
    initialize_database(database_path)

    @app.get("/health")
    def health() -> tuple[Any, int]:
        """Return a simple response proving the API is running."""
        return jsonify({"status": "ok"}), 200

    @app.post("/submit")
    def submit() -> tuple[Any, int]:
        """Validate, store, and return a temporary Milestone 3 submission result."""
        if not request.is_json:
            return jsonify({"error": "Request body must be valid JSON."}), 400

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Request body must be a JSON object."}), 400

        text = payload.get("text")
        creator_id = payload.get("creator_id")

        if not isinstance(text, str) or not text.strip():
            return jsonify({"error": "Field 'text' is required and must be a non-empty string."}), 400

        if not isinstance(creator_id, str) or not creator_id.strip():
            return jsonify({"error": "Field 'creator_id' is required and must be a non-empty string."}), 400

        normalized_text = text.strip()
        normalized_creator_id = creator_id.strip()
        text_length = len(normalized_text)

        if text_length < MIN_TEXT_LENGTH:
            return jsonify(
                {
                    "error": f"Field 'text' must contain at least {MIN_TEXT_LENGTH} non-whitespace characters.",
                    "received_length": text_length,
                }
            ), 400

        if text_length > MAX_TEXT_LENGTH:
            return jsonify(
                {
                    "error": f"Field 'text' must contain no more than {MAX_TEXT_LENGTH} characters.",
                    "received_length": text_length,
                }
            ), 400

        content_id = str(uuid4())
        event_id = str(uuid4())
        timestamp = utc_now()
        attribution = "pending_detection"
        status = "received"

        with get_connection(database_path) as connection:
            connection.execute(
                """
                INSERT INTO contents (
                    content_id,
                    creator_id,
                    text,
                    submitted_at,
                    attribution,
                    confidence,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    content_id,
                    normalized_creator_id,
                    normalized_text,
                    timestamp,
                    attribution,
                    None,
                    status,
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
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    "submission",
                    timestamp,
                    content_id,
                    normalized_creator_id,
                    attribution,
                    None,
                    status,
                ),
            )

        return jsonify(
            {
                "content_id": content_id,
                "creator_id": normalized_creator_id,
                "attribution": attribution,
                "confidence": None,
                "label": {
                    "variant": "pending",
                    "title": "Analysis pending",
                    "message": "Submission validation passed and was added to the audit log. Detection signals will be added next.",
                },
                "status": status,
            }
        ), 201

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
                    status
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