# Provenance Guard — Planning Specification

## 1. Project Purpose

Provenance Guard is a backend system for creative-sharing platforms. It analyzes text-based content, such as poems, short stories, blog posts, and personal writing, to provide a careful estimate of whether the content may have been generated or assisted by AI.

The system does not claim to prove who wrote a piece of content. AI detection is not fully reliable, and a false positive can unfairly harm a real writer. For that reason, Provenance Guard will use multiple independent signals, show uncertainty honestly, and allow creators to appeal a classification.

## 2. Main Goal

The goal is to help a creative platform give readers useful context about content origin while treating creators fairly.

The system will:

1. Accept submitted text and a creator ID.
2. Analyze the text with two independent detection signals.
3. Calculate an AI-likelihood score and a confidence score.
4. Return a reader-facing transparency label.
5. Save every decision in a structured audit log.
6. Allow creators to appeal a decision.
7. Change appealed content to `under_review`.
8. Rate-limit submissions to reduce spam and abuse.

## 3. Simple Submission Story

A creator sends writing to the `POST /submit` endpoint.

The app first checks that the request contains valid text and a creator ID. It then gives the text to two different detection signals:

- Signal 1: Groq LLM analysis
- Signal 2: Python stylometric heuristics

Each signal returns an AI-likelihood score between `0.0` and `1.0`.

The app combines the two scores, checks whether the signals agree, calculates a confidence score, selects a transparency label, saves the decision in SQLite and the audit log, and sends the result back to the creator or platform.

## 4. Simple Appeal Story

If a creator believes the result is wrong, they send an appeal to `POST /appeal`.

The app checks that the content exists and that the creator ID matches the original creator. It then changes the content status to `under_review`, saves the creator’s explanation, creates an appeal audit-log entry, and returns a confirmation message.

## 5. Architecture Diagram

```text
SUBMISSION FLOW
===============

Creator / Platform Client
        |
        | POST /submit
        | { text, creator_id }
        v
+------------------------+
| Flask API              |
| - validate JSON        |
| - validate text        |
| - apply rate limit     |
| - create content_id    |
+------------------------+
        |
        | raw text
        +-----------------------------+
        |                             |
        v                             v
+------------------------+     +----------------------------+
| Signal 1: Groq LLM     |     | Signal 2: Stylometrics     |
| semantic / holistic    |     | structural / measurable    |
| AI score: 0.0 to 1.0   |     | AI score: 0.0 to 1.0       |
+------------------------+     +----------------------------+
        |                             |
        | llm_score                   | stylometric_score
        +-------------+---------------+
                      |
                      v
          +------------------------+
          | Confidence Scoring     |
          | - combine both scores  |
          | - check agreement      |
          | - choose attribution   |
          +------------------------+
                      |
                      | result, confidence,
                      | signal scores
                      v
          +------------------------+
          | Transparency Label     |
          | likely AI / human /    |
          | uncertain              |
          +------------------------+
                      |
                      | structured decision
                      v
          +------------------------+
          | SQLite + Audit Log     |
          | save submission and    |
          | classification result  |
          +------------------------+
                      |
                      | JSON response
                      v
            Creator / Platform Client


APPEAL FLOW
===========

Creator / Platform Client
        |
        | POST /appeal
        | { content_id, creator_id, creator_reasoning }
        v
+------------------------+
| Flask API              |
| - validate request     |
| - find content         |
| - verify creator ID    |
+------------------------+
        |
        | valid appeal
        v
+------------------------+
| SQLite Database        |
| change status to       |
| "under_review"         |
+------------------------+
        |
        | appeal reason + status change
        v
+------------------------+
| Structured Audit Log   |
| save appeal event      |
+------------------------+
        |
        | confirmation JSON
        v
Creator / Platform Client
```

### Architecture Summary

For a submission, Provenance Guard receives a text submission, validates it, analyzes it through two independent signals, combines the signal scores into an attribution decision and confidence score, creates a transparency label, and saves the complete decision in SQLite and the audit log.

For an appeal, the system verifies that the original creator is submitting the appeal, changes the content status to `under_review`, stores the creator’s explanation, and records the appeal in the structured audit log.

## 6. Detection Signals

Provenance Guard uses two different signals because one signal alone is not reliable enough. The two signals look at different parts of the writing. One looks at the overall meaning and style. The other measures simple writing patterns with Python.

### Signal 1: Groq LLM Analysis

**What it checks:**

The Groq LLM reads the writing as a whole. It looks for broad patterns that may be associated with AI-generated writing, such as very generic wording, repetitive transitions, unusually even tone, over-explanation, or polished but impersonal phrasing.

**What it returns:**

The Groq signal returns an `llm_score` between `0.0` and `1.0`.

- `0.0` means the LLM sees very little evidence that the text is AI-generated.
- `0.5` means the LLM is unsure.
- `1.0` means the LLM sees strong evidence that the text may be AI-generated.

**Why this signal is useful:**

It can look at the writing holistically. For example, it may notice generic phrases, awkwardly smooth transitions, or a broad tone that a simple math-based checker cannot understand.

**What it can get wrong:**

A real person can write formal, polished, or academic text. A non-native English writer may also use careful and repetitive grammar. The LLM can mistakenly score this kind of human writing as AI-like. It can also miss AI-generated text that a person heavily rewrote.

### Signal 2: Python Stylometric Heuristics

**What it checks:**

The stylometric signal uses pure Python to measure visible writing patterns. It will calculate several small metrics:

1. **Sentence-length variation** — Human writing often mixes short and long sentences. AI writing can sometimes be more uniform.
2. **Vocabulary diversity** — The system compares unique words with total words. Very repetitive wording can be one weak sign of formulaic text.
3. **Generic transition phrase density** — The system checks for phrases such as `furthermore`, `moreover`, `in conclusion`, and `it is important to note`.
4. **Expressive and casual writing patterns** — The system looks for contractions, informal wording, fragments, question marks, exclamation marks, and other signs of varied natural writing.

**What it returns:**

The stylometric signal returns a `stylometric_score` between `0.0` and `1.0`.

- `0.0` means the measured patterns look more human-like.
- `0.5` means the structural patterns are unclear.
- `1.0` means the measured patterns look more formulaic or AI-like.

**Why this signal is useful:**

This signal is independent from the LLM signal. It does not try to understand meaning. It only measures text structure. That gives the system a second kind of evidence instead of asking two models to do nearly the same job.

**What it can get wrong:**

Poems, lyrics, short writing, formal essays, writing by non-native English speakers, and intentionally repetitive creative writing may have unusual patterns. The stylometric signal may score those pieces too highly even when a human wrote them.

### Why Both Signals Are Needed

The Groq signal is semantic and holistic. The stylometric signal is structural and measurable. Because they inspect different properties of the same text, agreement between them is more useful than one score alone.

However, disagreement is also useful. If one signal says the text looks strongly AI-like but the other signal says it looks human-like, Provenance Guard will lower its confidence and prefer the `uncertain` result instead of making a strong claim.

## 7. Confidence Scoring and Uncertainty

### 7.1 Important Meaning of the Scores

Provenance Guard keeps two ideas separate:

- **AI-likelihood** answers: “How AI-like does this text look according to the combined signals?”
- **Confidence** answers: “How strong and consistent is the evidence for showing a directional label?”

These numbers are engineering heuristics for this course project. They are not scientifically calibrated proof of authorship, and they must not be treated as proof that a person or AI wrote a piece of text.

### 7.2 Combined AI-Likelihood Score

Both detection signals return a number from `0.0` to `1.0`. The system combines them with a weighted average:

```text
ai_probability = (0.65 × llm_score) + (0.35 × stylometric_score)
```

The Groq LLM receives a slightly higher weight because it can examine the overall language, tone, and meaning of the text. The stylometric score remains important because it is a separate structural signal.

### 7.3 Signal Agreement

The system measures how closely the two signals agree:

```text
signal_agreement = 1 - abs(llm_score - stylometric_score)
```

- A result close to `1.0` means the signals agree strongly.
- A result close to `0.0` means the signals strongly disagree.

### 7.4 Confidence Formula

The system first measures how far the combined AI-likelihood is from the uncertain middle point of `0.50`:

```text
direction_strength = abs(ai_probability - 0.50) × 2
```

Then it combines direction strength with signal agreement:

```text
confidence = 0.50 + (0.50 × direction_strength × signal_agreement)
```

The result will always stay between `0.0` and `1.0`.

This design is intentionally careful:

- A score near `0.50` means the system has no strong direction.
- Strong agreement between signals raises confidence.
- Large disagreement lowers confidence.
- Mixed evidence should produce an `uncertain` result.

### 7.5 Attribution Thresholds

| Condition | Attribution | Meaning |
|---|---|---|
| `ai_probability >= 0.75` and `confidence >= 0.70` | `likely_ai` | The system has enough consistent evidence to say AI assistance or generation is likely. |
| `ai_probability <= 0.25` and `confidence >= 0.70` | `likely_human` | The system has enough consistent evidence to say the writing looks likely human-written. |
| Every other result | `uncertain` | Evidence is weak, mixed, or not strong enough for a fair directional label. |

### 7.6 What a Confidence Score of 0.60 Means

A confidence score of `0.60` means the system sees some evidence in one direction, but not enough agreement or distance from the middle point to make a strong attribution claim.

The system will return the `uncertain` label instead of forcing the text into an AI or human category.

This is intentional. On a creative platform, falsely labeling a human writer as AI-generated can cause more harm than leaving an AI-assisted text in the uncertain category.

### 7.7 How We Will Test Whether Scores Are Meaningful

Before finalizing the project, we will test the full pipeline with at least four deliberately different inputs:

1. A clearly generic, uniform AI-like paragraph.
2. A casual and irregular human-written review.
3. A formal human-written academic paragraph.
4. A lightly edited AI-like paragraph.

For each input, we will record `llm_score`, `stylometric_score`, `ai_probability`, `confidence`, and the returned label. We will inspect disagreements instead of hiding them.


The goal is not perfect detection. The goal is for the scores and labels to be explainable, cautious, and meaningfully different across different types of writing.

## 8. Transparency Label Design

The transparency label is the short, plain-language message a reader would see on a creative platform. It must explain the automated result without pretending the system has proof of authorship.

Every `POST /submit` response will include a `label` object with a `variant`, `title`, and `message`.

### 8.1 High-Confidence AI Label

**Variant:** `likely_ai`

**Title:** `AI-generated content likely`

**Exact message:**

`Our independent signals strongly indicate AI assistance or generation. This is an automated assessment, not proof of authorship, and the creator may appeal.`

**When it appears:**

This label appears only when `ai_probability >= 0.75` and `confidence >= 0.70`.

### 8.2 High-Confidence Human Label

**Variant:** `likely_human`

**Title:** `Likely human-written`

**Exact message:**

`Our independent signals strongly indicate this text appears likely human-written. This automated assessment is not proof of authorship.`

**When it appears:**

This label appears only when `ai_probability <= 0.25` and `confidence >= 0.70`.

### 8.3 Uncertain Label

**Variant:** `uncertain`

**Title:** `Origin uncertain`

**Exact message:**

`The available signals do not support a reliable AI-versus-human conclusion. No definitive attribution label is shown. The creator may appeal.`

**When it appears:**

This label appears for every result that does not meet the high-confidence AI or high-confidence human thresholds.

### 8.4 Why the Uncertain Label Is Important

The uncertain label is not a failure state. It is the correct, honest result when the text is too short, the signals disagree, the score is near the middle, or the system lacks strong evidence. This protects creators from a harmful false-positive AI label while still giving readers transparent context about uncertainty.

### 8.5 Example API Label Object


```json
{
  "variant": "uncertain",
  "title": "Origin uncertain",
  "message": "The available signals do not support a reliable AI-versus-human conclusion. No definitive attribution label is shown. The creator may appeal."
}
```

## 9. Appeals Workflow

An appeal gives a creator a clear path to contest a classification they believe is unfair or incorrect. The appeal process does not automatically change the attribution result. It changes the content status to `under_review` so a human reviewer can inspect the original decision and the creator’s explanation.

### 9.1 Who Can Submit an Appeal

Only the creator who submitted the content can appeal it. In this course-project prototype, the system checks this by comparing the `creator_id` in the appeal request with the `creator_id` stored for the original submission.

In a real production platform, this comparison would be replaced by authenticated user sessions and authorization checks.

### 9.2 Appeal Request Contract

The creator sends a `POST /appeal` request with:

```json
{
  "content_id": "the-content-id-from-submit",
  "creator_id": "creator-123",
  "creator_reasoning": "I wrote this myself from personal experience. My formal style may look unusual because English is not my first language."
}
```

The API validates the following rules:

- `content_id` is required.
- `creator_id` is required.
- `creator_reasoning` is required.
- `creator_reasoning` must contain at least 20 non-whitespace characters.
- `creator_reasoning` must not exceed 2,000 characters.
- The content ID must exist.
- The supplied creator ID must match the stored creator ID.
- A submission already marked `under_review` cannot receive a duplicate active appeal.

### 9.3 What Happens When an Appeal Is Received

When the request is valid, the system performs these steps in order:

1. Finds the original content record by `content_id`.
2. Verifies that the supplied `creator_id` belongs to that content.
3. Changes the content status from `classified` to `under_review`.
4. Saves the creator’s reasoning and the appeal timestamp in SQLite.
5. Creates a structured audit-log entry with `event_type: "appeal"`.
6. Returns a confirmation response.

The response will be:

```json
{
  "content_id": "the-content-id-from-submit",
  "status": "under_review",
  "message": "Appeal received. The classification has been marked for human review."
}
```

### 9.4 What the Audit Log Records for an Appeal

Every appeal event will include:

```text
- event_type: appeal
- timestamp
- content_id
- creator_id
- original attribution result
- original ai_probability
- original confidence
- original llm_score
- original stylometric_score
- status: under_review
- appeal_reasoning
```

This makes the appeal traceable back to the original classification decision.

### 9.5 What a Human Reviewer Would See

A future human-review queue would show:

- Content ID and creator ID
- Original submitted text
- Submission timestamp
- Original attribution and transparency label
- AI probability and confidence score
- Both individual signal scores
- Appeal timestamp
- Creator reasoning
- Current status: `under_review`

Automated reclassification is intentionally out of scope. The project requirement is to capture the appeal, update the status, and record the event reliably.

## 10. Rate Limiting

### 10.1 Submission Limit

The `POST /submit` endpoint will use Flask-Limiter with this limit:

```text
10 submissions per minute; 100 submissions per day
```

### 10.2 Why These Limits Were Chosen

A normal creator may submit a few drafts, revisions, or separate pieces of writing in a short period. Ten submissions per minute gives legitimate users room to test their work without feeling blocked.

The daily limit of 100 submissions reduces abuse. Without a daily limit, a script could repeatedly call the endpoint, consume Groq API capacity, fill the audit log with junk data, and probe the detector to learn how the scoring behaves.

When the minute or daily limit is exceeded, Flask-Limiter will return HTTP status `429 Too Many Requests`.

### 10.3 Rate-Limit Test Plan

During the demo, we will send 12 rapid requests to `POST /submit` from the same local address. The expected behavior is:

```text
Requests 1 through 10: HTTP 200
Requests 11 and 12: HTTP 429
```

The exact test command will be added to the README after the API is implemented.

## 11. SQLite Database and Structured Audit Log

### 11.1 Why SQLite

SQLite is built into Python, requires no extra account or cloud database, and keeps submissions and appeals available after the Flask server restarts. It is a better fit than storing state only in Python memory because the appeal endpoint needs to find the original submission later.

The local database file will be named `provenance_guard.db`. It is intentionally ignored by Git because it contains local demo data and can be regenerated.

### 11.2 Content Record

Each successful `POST /submit` call will create one content record with these fields:

```text
content_id
creator_id
text
submitted_at
llm_score
stylometric_score
ai_probability
confidence
attribution
label_variant
label_title
label_message
status
appeal_reasoning
appealed_at
```

The initial status is `classified`. After a valid appeal, the status becomes `under_review`.

### 11.3 Audit Event Record

The audit log records an immutable event whenever something important happens. It will be stored in SQLite and returned through `GET /log` as structured JSON for the demo.

Each audit event will include:

```text
event_id
event_type
timestamp
content_id
creator_id
attribution
ai_probability
confidence
llm_score
stylometric_score
label_variant
status
appeal_reasoning
```

### 11.4 Audit Event Types

The first version will use these event types:

| Event type | When it is created |
|---|---|
| `submission` | A text submission is classified successfully. |
| `appeal` | A creator submits a valid appeal and the content changes to `under_review`. |

`GET /log` will return the newest events first. For the demo, we will create at least three submission events and at least one appeal event.

## 12. Anticipated Edge Cases and Limitations

### 12.1 Poetry, Lyrics, and Repetitive Creative Writing

A poem or lyric can intentionally repeat words, use short lines, and have a narrow vocabulary. The stylometric signal may incorrectly treat that structure as formulaic or AI-like.

### 12.2 Formal Human Academic Writing

A human-written academic paragraph can use polished grammar, repeated transitions, and consistent sentence lengths. Both signals may lean AI-like even when the author is a human student or researcher.

### 12.3 Writing by a Non-Native English Speaker

A writer may use highly formal phrases, limited vocabulary, or repeated sentence structures because English is not their first language. The system could unfairly score this as AI-like. This is one reason the app is conservative and allows appeals.

### 12.4 Heavily Edited AI Output

A person can start with AI-generated text and then substantially rewrite it using personal stories, varied sentence lengths, and casual language. The system may return `likely_human` or `uncertain` even though AI was used earlier in the process.

### 12.5 Very Short Text

Very short text does not contain enough sentences or vocabulary for meaningful stylometric analysis. The API will reject text with fewer than 40 non-whitespace characters. Text just above that minimum may still receive an `uncertain` result.

### 12.6 Groq Service Failure

If the Groq API key is missing, invalid, rate-limited, or the Groq service is unavailable, the app must not invent an LLM score. It will return a controlled service error and will not save a misleading completed classification.

## 13. AI Tool Plan

### M3 — Submission Endpoint and First Signal

**Planning sections to provide to an AI tool:**

- Architecture narrative and diagram
- API contract for `POST /submit`
- Groq LLM signal specification
- SQLite and audit-log requirements

**What we will ask the AI tool to generate:**

- Flask app skeleton
- `GET /health`
- `POST /submit` route with validation
- A Groq signal service that returns a structured score
- Unique content-ID generation
- Initial SQLite content and audit-log storage
- `GET /log`

**How we will verify it:**

1. Start the Flask server.
2. Call `GET /health`.
3. Submit valid text with `curl`.
4. Verify the response contains a real `content_id`, signal score, placeholder or initial scoring result, and status.
5. Call `GET /log` and confirm a structured submission event exists.
6. Test invalid JSON, missing `text`, missing `creator_id`, and too-short text.

### M4 — Second Signal and Confidence Scoring

**Planning sections to provide to an AI tool:**

- Detection signals
- Confidence scoring and uncertainty formulas
- Attribution thresholds
- Architecture diagram

**What we will ask the AI tool to generate:**

- Pure-Python stylometric detector
- Metrics for sentence variation, vocabulary diversity, transition phrases, and expressive writing patterns
- Scoring logic that uses the exact formulas from Section 7
- Unit tests for scoring boundaries and label categories

**How we will verify it:**

1. Run both signals on four deliberately different test inputs.
2. Print both individual signal scores.
3. Verify the combined AI probability and confidence follow the written formulas.
4. Confirm that signal disagreement reduces confidence.
5. Confirm that the three label variants are reachable.

### M5 — Production Layer

**Planning sections to provide to an AI tool:**

- Transparency label design
- Appeals workflow
- Rate limiting
- SQLite and audit-log design
- Architecture diagram

**What we will ask the AI tool to generate:**

- Label-generation function using the three exact variants
- `POST /appeal` endpoint
- SQLite update from `classified` to `under_review`
- Appeal audit events
- Flask-Limiter configuration using `10 per minute; 100 per day`
- Tests for appeal ownership, duplicate appeals, label selection, and rate limiting

**How we will verify it:**

1. Trigger all three label variants with controlled test inputs or scoring tests.
2. Submit a content item and appeal it as the correct creator.
3. Confirm the status becomes `under_review`.
4. Confirm the appeal reasoning appears in `GET /log`.
5. Attempt an appeal with the wrong creator ID and verify it is rejected.
6. Send 12 rapid submissions and verify that later requests return HTTP 429.

## 14. Planned API Surface

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | `GET` | Confirms that the Flask app is running. |
| `/submit` | `POST` | Validates text, runs the detection pipeline, saves a classification, and returns the decision. |
| `/appeal` | `POST` | Records creator reasoning and changes an existing content item to `under_review`. |
| `/log` | `GET` | Returns recent structured audit events for the demo. |

### 14.1 Submit Request and Response Shape

Request:

```json
{
  "text": "A piece of writing to analyze.",
  "creator_id": "creator-123"
}
```

Response:

```json
{
  "content_id": "uuid-value",
  "attribution": "uncertain",
  "ai_probability": 0.52,
  "confidence": 0.54,
  "label": {
    "variant": "uncertain",
    "title": "Origin uncertain",
    "message": "The available signals do not support a reliable AI-versus-human conclusion. No definitive attribution label is shown. The creator may appeal."
  },
  "signals": {
    "llm_score": 0.54,
    "stylometric_score": 0.49
  },
  "status": "classified"
}
```

This is a planned example response shape. Real values will come from the running detector and must be tested before they are shown in the final demo.