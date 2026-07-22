"""Wraps all AI provider calls. Nothing else in the app should import anthropic/groq/etc
directly — this is the one place provider SDKs are touched."""
import json
import time
from flask import current_app
from anthropic import Anthropic
from groq import Groq
from app.services.ai_config import get_model_for_task



def _call_model(task: str, prompt: str, max_tokens: int = 2000, max_retries: int = 5) -> str:
    """Routes a prompt to whichever provider/model is configured for this task.
    Retries automatically on rate limits (common on free tiers), with backoff."""
    routing = get_model_for_task(task)
    provider = routing["provider"]
    model = routing["model"]

    last_error = None
    for attempt in range(max_retries):
        try:
            if provider == "anthropic":
                api_key = current_app.config.get("ANTHROPIC_API_KEY")
                if not api_key:
                    raise RuntimeError("ANTHROPIC_API_KEY is not configured")
                client = Anthropic(api_key=api_key)
                response = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                return "".join(block.text for block in response.content if block.type == "text")

            if provider == "groq":
                api_key = current_app.config.get("GROQ_API_KEY")
                if not api_key:
                    raise RuntimeError("GROQ_API_KEY is not configured")
                client = Groq(api_key=api_key)
                response = client.chat.completions.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.choices[0].message.content

            raise ValueError(f"Unknown provider '{provider}'")

        except Exception as exc:
            last_error = exc
            error_str = str(exc)
            if "rate_limit" in error_str or "429" in error_str:
                wait_time = min(10 * (attempt + 1), 60)  # back off progressively, cap at 60s
                time.sleep(wait_time)
                continue
            raise  # non-rate-limit errors fail immediately, no point retrying

    raise RuntimeError(f"AI call failed after {max_retries} retries (rate limited): {last_error}")


def generate_syllabus(topic: str, seta: str = None, nqf_level: str = None) -> dict:
    """Generates a structured syllabus (units + learning outcomes) for a given topic."""
    context_lines = [f"Topic: {topic}"]
    if seta:
        context_lines.append(f"SETA: {seta}")
    if nqf_level:
        context_lines.append(f"NQF Level: {nqf_level}")

    prompt = f"""You are an instructional designer creating a South African SETA/QCTO-aligned course syllabus.

{chr(10).join(context_lines)}

Return ONLY valid JSON (no markdown, no commentary) matching this exact shape:
{{
  "units": [
    {{
      "name": "Unit 1: <unit title>",
      "outcomes": ["<learning outcome 1>", "<learning outcome 2>"]
    }}
  ]
}}

Produce 4 to 8 units, each with 2 to 5 learning outcomes, appropriate for a work-related skills programme."""

    raw_text = _call_model("syllabus_generation", prompt, max_tokens=2000)

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"AI response was not valid JSON: {exc}") from exc

def structure_syllabus_from_text(raw_text: str, seta: str = None, nqf_level: str = None) -> dict:
    """Takes raw extracted text from an uploaded document and restructures it into
    the same {"units": [...]} shape used by the type-in and AI-generate paths."""
    context_lines = []
    if seta:
        context_lines.append(f"SETA: {seta}")
    if nqf_level:
        context_lines.append(f"NQF Level: {nqf_level}")

    # Truncate very long documents to stay within a reasonable prompt size
    truncated_text = raw_text[:12000]

    prompt = f"""You are an instructional designer. Below is raw text extracted from an uploaded
South African SETA/QCTO syllabus document. Restructure it into clean units and learning outcomes.

{chr(10).join(context_lines)}

Raw extracted text:
---
{truncated_text}
---

Return ONLY valid JSON (no markdown, no commentary) matching this exact shape:
{{
  "units": [
    {{
      "name": "Unit 1: <unit title>",
      "outcomes": ["<learning outcome 1>", "<learning outcome 2>"]
    }}
  ]
}}

Preserve the original structure and wording as closely as possible — this is restructuring, not rewriting."""

    raw_response = _call_model("syllabus_structuring", prompt, max_tokens=3000)

    try:
        return json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"AI response was not valid JSON: {exc}") from exc


def write_chapter_content(unit_name: str, outcomes: list, seta: str = None, nqf_level: str = None) -> dict:
    """Writes full chapter content for one syllabus unit. Returns a structured dict
    {"intro": str, "sections": [{"heading": str, "body": str}], "key_points": [str]}
    so the document builder can format each part correctly instead of guessing from raw text."""
    outcomes_text = "\n".join(f"- {o}" for o in outcomes)
    context_lines = []
    if seta:
        context_lines.append(f"SETA: {seta}")
    if nqf_level:
        context_lines.append(f"NQF Level: {nqf_level}")

    prompt = f"""You are a subject-matter expert writing a technical chapter for a South African
SETA/QCTO-accredited workplace training textbook.

Chapter: {unit_name}
{chr(10).join(context_lines)}

Learning outcomes this chapter must cover:
{outcomes_text}

Write technically specific, textbook-quality content — not generic overview text. For each learning
outcome, include where relevant: precise definitions, step-by-step procedures, specific standards or
regulatory references (e.g. OHS Act, SANS standards, specific PPE classes/ratings), common mistakes or
failure points workers make, and one detailed, realistic workplace scenario (not a one-line example —
walk through what happens, what the worker does, and why). Assume the reader is a working adult who
needs to actually apply this on the job, not just recognize the terminology.

Return ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "intro": "2-3 sentence introduction explaining why this chapter matters on the job",
  "sections": [
    {{
      "heading": "<short section heading tied to one learning outcome>",
      "body": "Full technical explanation, 150-250 words, following the guidance above. Plain text, no markdown."
    }}
  ],
  "key_points": ["<concise takeaway 1>", "<concise takeaway 2>", "<concise takeaway 3>"]
}}

One section per learning outcome. Plain text only inside strings — no asterisks, no markdown headers."""

    for attempt in range(2):  # try once, retry once more if JSON parsing fails
        raw_response = _call_model("textbook_writing", prompt, max_tokens=4500)
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError as exc:
            if attempt == 1:
                raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
            continue

def generate_slide_content(unit_name: str, outcomes: list, seta: str = None, nqf_level: str = None) -> dict:
    """Expands a syllabus unit into real slide content: a few genuinely useful bullets
    per slide plus speaker notes, rather than just repeating the raw outcomes."""
    outcomes_text = "\n".join(f"- {o}" for o in outcomes)
    context_lines = []
    if seta:
        context_lines.append(f"SETA: {seta}")
    if nqf_level:
        context_lines.append(f"NQF Level: {nqf_level}")

    prompt = f"""You are creating a training slide for a South African SETA/QCTO-accredited
workplace training presentation.

Slide topic: {unit_name}
{chr(10).join(context_lines)}

This slide covers these learning outcomes:
{outcomes_text}

Write slide content: 3 to 5 short, punchy bullet points a facilitator would actually put on screen
(not full sentences restating the outcomes — genuinely useful, specific takeaways: key facts, steps,
warnings, or numbers). Then write speaker notes: 2-3 sentences the facilitator would say out loud to
explain and expand on the bullets, including one concrete workplace example.

Return ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "bullets": ["<short bullet 1>", "<short bullet 2>", "<short bullet 3>"],
  "speaker_notes": "2-3 sentences the facilitator would say, including one concrete example."
}}"""

    raw_response = _call_model("slide_content", prompt, max_tokens=800)

    try:
        return json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"AI response was not valid JSON: {exc}") from exc