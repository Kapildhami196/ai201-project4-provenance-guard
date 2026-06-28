from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv
from groq import Groq

MODEL_NAME = "llama-3.3-70b-versatile"


class LlmDetectionError(RuntimeError):
    """Raised when the Groq detector cannot produce a valid result."""


def analyze_text(text: str) -> dict[str, Any]:
    """
    Return one cautious AI-likelihood signal for submitted text.

    This is a heuristic signal, not proof of authorship.
    """
    load_dotenv()

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise LlmDetectionError("GROQ_API_KEY is missing from the local environment.")

    client = Groq(api_key=api_key)

    system_prompt = """
You are one signal in a cautious content-provenance system.

Assess whether submitted writing has characteristics often associated with
AI-generated or AI-assisted writing. This is not proof of authorship.

Return JSON with exactly these fields:
{
  "ai_likelihood": number,
  "reasoning": string
}

Rules:
- ai_likelihood must be between 0.0 and 1.0.
- 0.0 means little evidence of AI-like writing patterns.
- 0.5 means uncertain or mixed evidence.
- 1.0 means strong evidence of AI-like writing patterns.
- reasoning must be one short sentence.
- Consider generic phrasing, repetitive transitions, overly uniform tone,
  over-explanation, and polished but impersonal language.
- Be cautious with formal academic writing, poetry, and non-native English.
""".strip()

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0,
            max_tokens=160,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": f"Analyze this submitted text:\n\n{text}",
                },
            ],
        )
    except Exception as error:
        raise LlmDetectionError("Groq request failed. Try again later.") from error

    raw_response = completion.choices[0].message.content
    if not isinstance(raw_response, str) or not raw_response.strip():
        raise LlmDetectionError("Groq returned an empty response.")

    try:
        result = json.loads(raw_response)
    except json.JSONDecodeError as error:
        raise LlmDetectionError("Groq returned invalid JSON.") from error

    if not isinstance(result, dict):
        raise LlmDetectionError("Groq returned JSON that was not an object.")

    score = result.get("ai_likelihood")
    reasoning = result.get("reasoning")

    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise LlmDetectionError("Groq did not return a numeric ai_likelihood score.")

    normalized_score = float(score)
    if not 0.0 <= normalized_score <= 1.0:
        raise LlmDetectionError("Groq returned a score outside the 0.0 to 1.0 range.")

    if not isinstance(reasoning, str) or not reasoning.strip():
        raise LlmDetectionError("Groq did not return a usable reasoning string.")

    return {
        "llm_score": normalized_score,
        "reasoning": reasoning.strip(),
        "model": MODEL_NAME,
    }
