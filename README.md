# Provenance Guard

A cautious content-provenance prototype that analyzes submitted text with two independent signals:

1. **Groq LLM signal** — evaluates broad semantic and stylistic patterns.
2. **Local stylometric signal** — evaluates writing-pattern heuristics in Python.

The app does **not** claim to prove authorship. It provides a transparent automated assessment, reports uncertainty, preserves evidence in an audit log, and lets creators appeal a result.

---

## Project Goal

Provenance Guard helps answer a limited question:

> Does this submitted text appear more AI-like, more human-like, or too uncertain to label responsibly?

It is designed to avoid overclaiming. A result is never treated as proof that a person did or did not use AI.

---

## Features

- `POST /submit` accepts text and a creator ID
- Two independent detection signals
- Combined AI probability, signal agreement, and confidence score
- Three transparency labels:
  - **AI-generated content likely**
  - **Likely human-written**
  - **Origin uncertain**
- Creator appeal workflow
- Human review queue
- Structured SQLite audit log
- Rate limiting on expensive submission requests
- Browser interface for submitting and appealing content
- Automated test suite

---

## Architecture

```text
Browser UI or API request
          |
          v
      POST /submit
          |
          +--> Groq LLM signal
          |
          +--> Local stylometric signal
          |
          v
   Scoring and confidence logic
          |
          v
Transparency label and explanation
          |
          v
SQLite content record + audit event
          |
          +--> Creator appeal
          |
          v
      Human review queue
```

---

## Detection Signals

### 1. Groq LLM Signal

File: `services/llm_detector.py`

The Groq model evaluates broad semantic and stylistic patterns and returns:

- `llm_score` from `0.0` to `1.0`
- a short explanation
- the model name

Interpretation:

- `0.0` means less evidence of AI-like writing patterns
- `0.5` means uncertain or mixed evidence
- `1.0` means stronger evidence of AI-like writing patterns

This signal is cautious about formal academic writing, poetry, polished writing, and non-native English.

### 2. Local Stylometric Signal

File: `services/stylometric_detector.py`

This local Python signal evaluates writing-pattern heuristics such as:

- generic transition phrases
- generic formal phrases
- vocabulary repetition
- sentence-length uniformity
- lexical diversity

It returns a `stylometric_score`, explanation, and transparent metrics such as word count and sentence count.

Neither signal is proof of authorship.

---

## Confidence and Scoring

File: `services/scoring.py`

The app calculates combined AI probability using:

```text
AI probability =
(0.65 × Groq score) +
(0.35 × stylometric score)
```

Signal agreement is:

```text
1 - absolute difference between the two scores
```

Confidence becomes stronger only when the combined direction is strong **and** both independent signals agree. This prevents a high-confidence label when signals conflict.

---

## Transparency Labels

### AI-generated content likely

Shown only when:

```text
AI probability >= 0.75
Confidence >= 0.70
```

Message:

> Our independent signals strongly indicate AI assistance or generation. This is an automated assessment, not proof of authorship, and the creator may appeal.

### Likely human-written

Shown only when:

```text
AI probability <= 0.25
Confidence >= 0.70
```

Message:

> Our independent signals strongly indicate this text appears likely human-written. This automated assessment is not proof of authorship.

### Origin uncertain

Shown when evidence is weak, mixed, or the two signals disagree.

Message:

> The available signals do not support a reliable AI-versus-human conclusion. No definitive attribution label is shown. The creator may appeal.

---

## Appeals Workflow

Endpoint: `POST /appeal`

A creator sends:

```json
{
  "content_id": "content UUID",
  "creator_id": "original creator ID",
  "creator_reasoning": "Explanation of why the creator disagrees"
}
```

The app checks that:

- the content exists
- the creator ID matches the original creator
- the appeal reason is between 20 and 2,000 characters
- no appeal is already under review

A successful appeal preserves the original automated result, changes the content status to `under_review`, saves creator reasoning and timestamp, creates an `appeal` audit event, and places the item in `/review-queue`.

For this local prototype, ownership is checked by matching `creator_id`. A production system should use authenticated user identity.

---

## Audit Log

Endpoint: `GET /log`

Each audit event records structured information including:

- event type: `submission` or `appeal`
- timestamp
- content ID
- creator ID
- final label
- confidence
- Groq score and explanation
- stylometric score and explanation
- AI probability
- signal agreement
- appeal reasoning when applicable
- review status

The audit log is stored locally in SQLite.

---

## Rate Limiting

`POST /submit` is rate limited because every valid submission may call the Groq API.

Limits:

```text
10 requests per minute
100 requests per day
```

When the limit is exceeded, the app returns `HTTP 429 Too Many Requests` with a JSON error response.

The local prototype uses in-memory rate-limit storage. This resets when the Flask server restarts. A deployed version should use Redis or another shared storage system.

---

## Browser Interface

Start the server, then open:

```text
http://127.0.0.1:5000/
```

The browser interface supports:

- entering a creator ID and text
- analyzing content
- viewing the final label, probability, confidence, and both signals
- submitting an appeal
- opening the audit log and review queue

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/Kapildhami196/ai201-project4-provenance-guard.git
cd ai201-project4-provenance-guard
```

### 2. Create and activate a virtual environment

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create a local `.env` file

```text
GROQ_API_KEY=your_groq_api_key_here
```

Do not commit `.env`. It is ignored by `.gitignore`.

### 5. Run the application

```bash
python app.py
```

Then visit:

```text
http://127.0.0.1:5000/
```

---

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/` | Browser interface |
| `GET` | `/health` | Health check |
| `POST` | `/submit` | Analyze submitted content |
| `POST` | `/appeal` | Submit a creator appeal |
| `GET` | `/review-queue` | View content under review |
| `GET` | `/log` | View structured audit events |

---

## Example Submit Request

```bash
curl -s -X POST http://127.0.0.1:5000/submit \
  -H "Content-Type: application/json" \
  -d '{
    "creator_id": "demo-user",
    "text": "I fixed my bike after work yesterday. The chain kept slipping, so I adjusted the back wheel and tested it around the block."
  }' | python -m json.tool
```

---

## Running Tests

Run the entire test suite:

```bash
python -m pytest -q
```

Current tested areas include:

- scoring and confidence behavior
- likely-AI label behavior
- likely-human label behavior
- uncertain label behavior when signals disagree
- validation errors
- submission flow
- creator ownership checks
- appeal workflow
- duplicate appeal prevention
- review queue
- audit log entries

---

## Limitations

This project is a prototype and has important limitations:

- It cannot prove who wrote text.
- Formal academic writing may resemble AI-assisted writing.
- Non-native English may be misclassified.
- Heavily edited AI output can resemble human writing.
- Short writing has less reliable pattern information.
- Poetry, lyrics, technical writing, and intentionally repetitive text can confuse stylometric heuristics.
- The Groq signal depends on external API availability.
- The local prototype uses `creator_id`, not real authentication.
- The in-memory rate limiter resets after restarting the server.
- Human review is required for appealed content.

---

## Ethical Design Choices

Provenance Guard intentionally uses:

- two independent signals instead of one detector
- uncertainty rather than forced binary labels
- transparent score explanations
- an appeal mechanism
- preserved audit history
- a human review queue
- rate limiting to protect the external AI service

The purpose is to support careful review, not to punish users or make unsupported authorship claims.
