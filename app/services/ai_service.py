"""Wraps all AI provider calls. Nothing else in the app should import anthropic/groq/etc
directly — this is the one place provider SDKs are touched."""
import json
import time
from flask import current_app
from anthropic import Anthropic
from groq import Groq
from app.services.ai_config import get_model_for_task

import re


def _repair_json_string(raw: str) -> str:
    """Fixes the most common way AI models break JSON: emitting a backslash that isn't
    part of a valid JSON escape sequence (\\", \\\\, \\n, \\t, \\r, \\b, \\f, \\uXXXX).
    Doubles up any other backslash so it's treated as a literal character instead of
    an invalid escape."""
    return re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)

def _call_model(task: str, prompt: str, max_tokens: int = 2000, max_retries: int = 8, job_id: str = None) -> str:
    """Routes a prompt to whichever provider/model is configured for this task.
    Retries automatically on rate limits, with backoff matching the provider's stated wait time.
    If job_id is given, checks between retries whether the job was cancelled and aborts early."""
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
                wait_match = re.search(r'try again in (?:(\d+)m)?([\d.]+)s', error_str)
                if wait_match:
                    minutes = int(wait_match.group(1)) if wait_match.group(1) else 0
                    seconds = float(wait_match.group(2))
                    wait_time = minutes * 60 + seconds + 3
                else:
                    wait_time = min(10 * (attempt + 1), 60)
                wait_time = min(wait_time, 600)

                if job_id:
                    from app.models.generation_job import GenerationJob
                    from app.extensions import db
                    db.session.expire_all()
                    job = GenerationJob.query.get(job_id)
                    if job and job.status == "cancelled":
                        raise RuntimeError("Job was cancelled during retry wait")

                print(f"[RATE LIMIT] Attempt {attempt + 1}/{max_retries} — waiting {wait_time:.0f}s before retry...")
                time.sleep(wait_time)

                if job_id:
                    db.session.expire_all()
                    job = GenerationJob.query.get(job_id)
                    if job and job.status == "cancelled":
                        raise RuntimeError("Job was cancelled during retry wait")

                continue
            raise

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


def write_chapter_content(unit_name: str, outcomes: list, seta: str = None, nqf_level: str = None, job_id: str = None) -> dict:
    """Writes full chapter content for one syllabus unit. Returns a structured dict where
    each section is a list of typed content blocks (paragraph, scenario, table, formula)
    so the document builder can render each one with distinct, appropriate styling."""
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
regulatory references, common mistakes, and at least one detailed workplace scenario. Where a
calculation, ratio, or formula is genuinely relevant to the topic, include it. Where comparing options
or listing structured data is genuinely relevant, include a table.

Return ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "intro": "2-3 sentence introduction explaining why this chapter matters on the job",
  "sections": [
    {{
      "heading": "<short section heading tied to one learning outcome>",
      "blocks": [
        {{"type": "paragraph", "text": "Explanatory text, 100-200 words, plain text no markdown."}},
        {{"type": "scenario", "text": "A detailed, realistic workplace scenario walking through what happens and what the worker should do."}},
        {{"type": "table", "headers": ["Column A", "Column B"], "rows": [["value", "value"], ["value", "value"]]}},
        {{"type": "formula", "label": "Short name of the formula", "text": "The formula itself, plain text, e.g. Risk = Likelihood x Severity"}},
        {{"type": "diagram", "steps": ["Step 1 label", "Step 2 label", "Step 3 label"], "caption": "What this diagram shows"}},
        {{"type": "image", "search_term": "2-4 word search phrase for a relevant stock photo, e.g. 'warehouse worker safety helmet'", "caption": "What this image shows"}}
      ]
    }}
  ],
  "key_points": ["<concise takeaway 1>", "<concise takeaway 2>", "<concise takeaway 3>"]
}}

Include a "diagram" block where a step-by-step process is genuinely central to the topic (3-6 steps).
Include an "image" block where a real photo would help illustrate a concept (equipment, environment, technique).
Do not force every section to use every block type — most sections should just be paragraph and
occasionally scenario; diagrams, tables, formulas, and images are for genuinely relevant cases only.

Each section needs at least one "paragraph" block. Only include "scenario", "table", or "formula" blocks
where genuinely relevant to that section — do not force them into every section. One section per learning
outcome. Plain text only inside strings — no asterisks, no markdown headers."""

    for attempt in range(2):
        raw_response = _call_model("textbook_writing", prompt, max_tokens=4500, job_id=job_id)
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json_string(raw_response))
            except json.JSONDecodeError as exc:
                if attempt == 1:
                    raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
                continue

def generate_slide_content(unit_name: str, outcomes: list, seta: str = None, nqf_level: str = None, job_id: str = None) -> dict:
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
  "speaker_notes": "2-3 sentences the facilitator would say, including one concrete example.",
  "image_search_term": "2-4 word search phrase for a relevant photo, or null if this slide doesn't need one"
}}

Only include image_search_term where a real photo would genuinely support this specific slide's content
(e.g. equipment, environment, a technique being described) — most slides should have this as null."""

    raw_response = _call_model("slide_content", prompt, max_tokens=800, job_id=job_id)

    try:
        return json.loads(raw_response)
    except json.JSONDecodeError:
        try:
            return json.loads(_repair_json_string(raw_response))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"AI response was not valid JSON: {exc}") from exc

def generate_assessment_questions(unit_name: str, outcomes: list, seta: str = None, nqf_level: str = None, job_id: str = None) -> dict:
    """Generates test questions for one syllabus unit, covering its learning outcomes.
    Returns structured JSON so the docx builder can render blank space and marks per question."""
    outcomes_text = "\n".join(f"- {o}" for o in outcomes)
    context_lines = []
    if seta:
        context_lines.append(f"SETA: {seta}")
    if nqf_level:
        context_lines.append(f"NQF Level: {nqf_level}")

    prompt = f"""You are writing assessment questions for a South African SETA/QCTO-accredited
workplace training assessment.

Unit: {unit_name}
{chr(10).join(context_lines)}

This unit covers these learning outcomes:
{outcomes_text}

Write 4 to 6 assessment questions that test whether a learner has achieved these outcomes.
Mix question types: some short-answer (1-2 sentence expected answer), some multiple-choice
(4 options, one correct), some scenario-based (describe a workplace situation and ask what
the learner should do). Assign a mark value to each question based on its complexity (short
answer: 2-3 marks, multiple-choice: 1 mark, scenario: 4-5 marks).

Return ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "questions": [
    {{
      "type": "short_answer",
      "text": "<question text>",
      "marks": 3,
      "blank_lines": 3
    }},
    {{
      "type": "multiple_choice",
      "text": "<question text>",
      "marks": 1,
      "options": ["<option A>", "<option B>", "<option C>", "<option D>"]
    }},
    {{
      "type": "scenario",
      "text": "<scenario description followed by the question>",
      "marks": 5,
      "blank_lines": 5
    }}
  ]
}}

"blank_lines" for short_answer/scenario suggests how many ruled lines to leave for the answer.
For multiple_choice, omit "blank_lines"."""

    raw_response = _call_model("textbook_writing", prompt, max_tokens=3000, job_id=job_id)

    try:
        return json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"AI response was not valid JSON: {exc}") from exc

DOCUMENT_PROMPT_FRAMING = {
    "learner_manual": "a Learner Manual — the core training content the learner studies to gain the knowledge and skills required by the unit standard",
    "facilitator_guide": "a Facilitator Guide — delivery notes for the trainer: lesson objectives, timing, preparation notes, and delivery instructions for facilitating this unit",
    "formative_assessment": "a Formative Assessment — ongoing, low-stakes questions and activities used to check understanding as the learner progresses through this unit",
    "summative_assessment": "a Summative Assessment — formal end-of-unit questions and practical tasks used to certify competence in this unit",
    "assessment_guide": "an Assessment Guide — guidance for the Assessor on how to conduct and mark the assessment for this unit, including an evidence checklist",
    "moderator_guide": "a Moderator Guide — a checklist and guidance for the Moderator reviewing an Assessor's judgements for this unit",
    "poe_guide": "a Portfolio of Evidence Guide — instructions for the learner on what evidence to collect and how to compile it for this unit",
    "learner_induction_guide": "a Learner Induction Guide — an orientation document introducing the learner to the NQF learning approach, their rights and responsibilities, appeals procedures, and how assessment and certification work for this specific programme",
    "programme_strategy": "a Programme Strategy document — explains how the training programme's delivery and assessment strategy aligns with the outcomes of this unit, including delivery methods and resource requirements",
    "programme_alignment_matrix": "a Programme Alignment Matrix — a structured breakdown showing how this unit's learning outcomes align to assessment strategy and notional learning hours",
}


def generate_guide_section_content(document_subtype: str, unit_name: str, outcomes: list,
                                    seta: str = None, nqf_level: str = None, job_id: str = None) -> dict:
    """Generates section content for one unit of a SETA guide-style document
    (facilitator guide, assessment guide, etc). Shares the same block-typed shape
    as chapter content, but the prompt framing changes per document type."""
    framing = DOCUMENT_PROMPT_FRAMING.get(document_subtype, "a training support document")
    outcomes_text = "\n".join(f"- {o}" for o in outcomes)
    context_lines = []
    if seta:
        context_lines.append(f"SETA: {seta}")
    if nqf_level:
        context_lines.append(f"NQF Level: {nqf_level}")

    prompt = f"""You are writing content for {framing}, for a South African SETA/QCTO-accredited
workplace training programme.

Unit: {unit_name}
{chr(10).join(context_lines)}

This unit covers these learning outcomes:
{outcomes_text}

Write content appropriate to this specific document type — not generic textbook prose. Be practical
and specific to the role this document plays (e.g. a facilitator guide gives delivery instructions,
not learner-facing explanations; an assessment guide gives marking guidance, not questions themselves).

Return ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "intro": "1-2 sentence introduction to this section",
  "sections": [
    {{
      "heading": "<short section heading>",
      "blocks": [
        {{"type": "paragraph", "text": "Content appropriate to the document type, 80-150 words."}},
        {{"type": "table", "headers": ["Column A", "Column B"], "rows": [["value", "value"]]}},
        {{"type": "diagram", "steps": ["Step 1 label", "Step 2 label", "Step 3 label"], "caption": "What this diagram shows"}},
        {{"type": "image", "search_term": "2-4 word search phrase for a relevant stock photo", "caption": "What this image shows"}}
      ]
    }}
  ],
  "key_points": ["<concise takeaway 1>", "<concise takeaway 2>"]
}}

Only include table, diagram, or image blocks where genuinely relevant to this specific document type —
most sections should just be a paragraph block. One section per learning outcome. Plain text only, no markdown."""

    for attempt in range(2):
        raw_response = _call_model("textbook_writing", prompt, max_tokens=3000, job_id=job_id)
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json_string(raw_response))
            except json.JSONDecodeError as exc:
                if attempt == 1:
                    raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
                continue