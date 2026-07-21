"""Wraps all AI provider calls. Nothing else in the app should import anthropic/groq/etc
directly — this is the one place provider SDKs are touched."""
import json
from flask import current_app
from anthropic import Anthropic
from groq import Groq
from app.services.ai_config import get_model_for_task


def _call_model(task: str, prompt: str, max_tokens: int = 2000) -> str:
    routing = get_model_for_task(task)
    provider = routing["provider"]
    model = routing["model"]

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