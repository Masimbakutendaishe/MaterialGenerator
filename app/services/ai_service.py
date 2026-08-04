"""Wraps all AI provider calls. Nothing else in the app should import anthropic/groq/etc
directly — this is the one place provider SDKs are touched."""
import json
import time
from flask import current_app
from anthropic import Anthropic
from groq import Groq
from app.services.ai_config import get_model_for_task
import google.generativeai as genai

import re


def _repair_json_string(raw: str) -> str:
    """Fixes common ways AI models break JSON: stray backslashes, trailing commas
    before closing brackets/braces, and markdown code fences wrapping the response."""
    # Strip markdown code fences if the model wrapped its JSON in ```json ... ```
    raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip())
    # Fix stray backslashes not part of a valid JSON escape
    raw = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)
    # Remove trailing commas before a closing } or ]
    raw = re.sub(r',(\s*[}\]])', r'\1', raw)
    return raw

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

    for attempt in range(2):
        raw_text = _call_model("syllabus_generation", prompt, max_tokens=4000)
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json_string(raw_text))
            except json.JSONDecodeError as exc:
                if attempt == 1:
                    raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
                continue


def structure_syllabus_from_text(raw_text: str, seta: str = None, nqf_level: str = None) -> dict:
    """Takes raw extracted text from an uploaded document and restructures it into
    the same {"units": [...]} shape used by the type-in and AI-generate paths."""
    context_lines = []
    if seta:
        context_lines.append(f"SETA: {seta}")
    if nqf_level:
        context_lines.append(f"NQF Level: {nqf_level}")

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

def _call_model(task: str, prompt: str, max_tokens: int = 2000, max_retries: int = 4, job_id: str = None) -> str:
    """Tries each provider in the task's chain in order (free options first, paid last).
    Within each provider, retries on rate limits with backoff up to max_retries; if a
    provider is out of credits or exhausts its retries, moves to the next in the chain."""
    routing = get_model_for_task(task)
    chain = routing["chain"]

    def _attempt(provider, model):
        for attempt in range(max_retries):
            try:
                if provider == "anthropic":
                    api_key = current_app.config.get("ANTHROPIC_API_KEY")
                    if not api_key:
                        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
                    client = Anthropic(api_key=api_key)
                    response = client.messages.create(
                        model=model, max_tokens=max_tokens,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    return "".join(block.text for block in response.content if block.type == "text")

                if provider == "groq":
                    api_key = current_app.config.get("GROQ_API_KEY")
                    if not api_key:
                        raise RuntimeError("GROQ_API_KEY is not configured")
                    client = Groq(api_key=api_key)
                    response = client.chat.completions.create(
                        model=model, max_tokens=max_tokens,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    return response.choices[0].message.content

                if provider == "gemini":
                    api_key = current_app.config.get("GEMINI_API_KEY")
                    if not api_key:
                        raise RuntimeError("GEMINI_API_KEY is not configured")
                    import google.generativeai as genai
                    genai.configure(api_key=api_key)
                    gemini_model = genai.GenerativeModel(model)
                    response = gemini_model.generate_content(
                        prompt,
                        generation_config={"max_output_tokens": max_tokens},
                    )
                    return response.text

                if provider == "nyra":
                    api_key = current_app.config.get("NYRA_API_KEY")
                    if not api_key:
                        raise RuntimeError("NYRA_API_KEY is not configured")
                    import requests as _requests
                    try:
                        resp = _requests.post(
                            "https://router.bynara.id/v1/chat/completions",
                            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                            json={"model": model, "max_tokens": max_tokens,
                                  "messages": [{"role": "user", "content": prompt}]},
                            timeout=60,
                        )
                    except _requests.exceptions.RequestException as exc:
                        raise RuntimeError(f"Nyra connection error: {exc}") from exc
                    if resp.status_code != 200:
                        raise RuntimeError(f"Nyra error {resp.status_code}: {resp.text}")
                    resp_json = resp.json()
                    if "choices" not in resp_json or not resp_json["choices"]:
                        raise RuntimeError(f"Nyra returned an unexpected response shape (no 'choices'): {resp.text[:300]}")
                    return resp_json["choices"][0]["message"]["content"]

                raise ValueError(f"Unknown provider '{provider}'")

            except Exception as exc:
                error_str = str(exc).lower()

                if "rate_limit" in error_str or "429" in error_str or "rate limit" in error_str:
                    wait_match = re.search(r'try again in (?:(\d+)m)?([\d.]+)s', str(exc))
                    if wait_match:
                        minutes = int(wait_match.group(1)) if wait_match.group(1) else 0
                        seconds = float(wait_match.group(2))
                        wait_time = minutes * 60 + seconds + 3
                    else:
                        wait_time = min(10 * (attempt + 1), 60)
                    wait_time = min(wait_time, 120)  # capped short — we have more providers to fall through to

                    if job_id:
                        from app.models.generation_job import GenerationJob
                        from app.extensions import db
                        db.session.expire_all()
                        job = GenerationJob.query.get(job_id)
                        if job and job.status == "cancelled":
                            raise RuntimeError("Job was cancelled during retry wait")

                    print(f"[RATE LIMIT] ({provider}) Attempt {attempt + 1}/{max_retries} — waiting {wait_time:.0f}s before retry...")
                    time.sleep(wait_time)

                    if job_id:
                        db.session.expire_all()
                        job = GenerationJob.query.get(job_id)
                        if job and job.status == "cancelled":
                            raise RuntimeError("Job was cancelled during retry wait")
                    continue

                if "credit balance" in error_str or "insufficient_quota" in error_str:
                    raise _OutOfCreditsError(str(exc)) from exc

                # Any other unexpected error (malformed response, SDK-specific exception, etc.)
                # gets wrapped as RuntimeError so the chain-walking loop can catch it and
                # move to the next provider, instead of crashing the whole generation.
                raise RuntimeError(f"{provider} error: {exc}") from exc

        raise RuntimeError(f"{provider} exhausted {max_retries} retries")

    last_error = None
    for step in chain:
        try:
            result = _attempt(step["provider"], step["model"])
            return result
        except (_OutOfCreditsError, RuntimeError) as exc:
            last_error = exc
            print(f"[CHAIN] {step['provider']} unavailable ({exc}) — trying next provider in chain")
            continue

    raise RuntimeError(f"All providers in chain failed. Last error: {last_error}")


class _OutOfCreditsError(Exception):
    """Internal signal that a provider is out of credits/quota — triggers moving to the next in chain."""
    pass


class _OutOfCreditsError(Exception):
    """Internal signal that the primary provider is out of credits/quota — triggers fallback."""
    pass


def write_chapter_content(unit_name: str, outcomes: list, course_title: str = None, seta: str = None, nqf_level: str = None, job_id: str = None) -> dict:
    """Writes full chapter content for one syllabus unit. Returns a structured dict where
    each section is a list of typed content blocks (paragraph, scenario, table, formula)
    so the document builder can render each one with distinct, appropriate styling."""
    outcomes_text = "\n".join(f"- {o}" for o in outcomes)
    context_lines = []
    if seta:
        context_lines.append(f"SETA: {seta}")
    if nqf_level:
        context_lines.append(f"NQF Level: {nqf_level}")

    prompt = f"""You are a subject-matter expert writing a chapter for a South African
SETA/QCTO-accredited training textbook, in the style of real accredited SETA learner guides.
COURSE CONTEXT — this chapter belongs to the course "{course_title or 'Unspecified Course'}". Every
example, scenario, and piece of terminology in this chapter MUST be genuinely relevant to that course's
actual subject matter. If a unit name or outcome is vague, interpret it strictly in the context of
"{course_title}" — never substitute in content from an unrelated field.
Chapter: {unit_name}
{chr(10).join(context_lines)}

Learning outcomes this chapter must cover:
{outcomes_text}

Write content grounded in the ACTUAL subject matter of this unit — do not force unrelated
industrial, workplace-safety, or manufacturing framing onto topics that aren't about that
(e.g. a programming or IT topic should use programming examples, not steel plants or mining).

CITATIONS: If this topic genuinely involves South African law or regulation (e.g. finance, HR,
health and safety), you may cite REAL acts/sections you are confident actually exist (e.g.
"Pension Funds Act 24 of 1956", "Section 11(k)(i)"), and explicitly state you are scoping to
the relevant ones for this chapter. If the topic does NOT involve law/regulation (e.g. a technical
or IT skill), do not invent or reference any legislation at all — just teach the subject directly.
Never invent a specific act name, section number, or standard number you are not confident is real.

STRUCTURE, matching real accredited learner guides:
- Open with a scope statement: what this chapter covers, as an info_box block with bullet items
- Each section should be genuinely detailed — several paragraphs, not a shallow gloss
- Where the topic has real formulas/calculations, always include a variable legend (what each
  symbol means), not a bare formula
- Where comparing multiple options/approaches, use a real comparative table (not a single-column list)
- Where relevant, include Advantages/Disadvantages as a clearly labelled paragraph or info_box
- Address the learner directly ("you") in a practical, applied tone — this is workplace training,
  not an academic textbook
- Use a detailed, realistic scenario where it helps ground an abstract concept in practice

For each learning outcome, include where relevant: precise definitions, step-by-step procedures,
common mistakes, and at least one detailed, realistic scenario using examples natural to this
actual subject matter.

Return ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "intro": "2-3 sentence introduction explaining why this chapter matters on the job",
  "sections": [
    {{
      "heading": "<short section heading tied to one learning outcome>",
      "blocks": [
        {{"type": "info_box", "title": "This Chapter Covers", "items": ["<point 1>", "<point 2>"]}},
        {{"type": "paragraph", "text": "Explanatory text, 100-200 words, plain text no markdown."}},
        {{"type": "scenario", "text": "A detailed, realistic workplace scenario walking through what happens and what the worker should do."}},
        {{"type": "table", "headers": ["Column A", "Column B"], "rows": [["value", "value"], ["value", "value"]]}},
        {{"type": "formula", "label": "Short name of the formula", "text": "The formula itself, e.g. Z = C + E - D", "variables": [{{"symbol": "Z", "meaning": "what Z represents"}}, {{"symbol": "C", "meaning": "what C represents"}}]}},
        {{"type": "diagram", "steps": ["Step 1 label", "Step 2 label", "Step 3 label"], "caption": "What this diagram shows"}},
        {{"type": "list", "items": ["<item 1>", "<item 2>", "<item 3>"], "ordered": false}},
        {{"type": "image", "search_term": "SPECIFIC concrete search phrase naming the exact real object/scene relevant to this outcome (e.g. 'fire extinguisher workplace' not 'safety equipment')", "caption": "What this image shows"}}
      ]
    }}
  ],
  "key_points": ["<concise takeaway 1>", "<concise takeaway 2>", "<concise takeaway 3>"]
}}

Use "diagram" for any step-by-step process, sequence, or decision flow. Use "image" ONLY for a
concrete physical object, tool, environment, or scene that a real photograph would meaningfully
illustrate — never use "image" for abstract concepts or processes a diagram would represent better.

Only the FIRST section needs an info_box scope block. Every section needs at least one paragraph
block. Only include scenario/table/formula/diagram/image/list blocks where genuinely relevant — do
not force them into every section. One section per learning outcome. Plain text only inside strings —
no asterisks, no markdown headers.

NEVER write a numbered or bulleted list inline inside a paragraph's text (e.g. "1) X 2) Y 3) Z" or
"firstly... secondly..."). Whenever you have 3 or more related items, use a "list" block instead —
set "ordered": true for sequential steps, "ordered": false for unordered items."""

    for attempt in range(2):
        raw_response = _call_model("textbook_writing", prompt, max_tokens=8192, job_id=job_id)
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json_string(raw_response))
            except json.JSONDecodeError as exc:
                if attempt == 1:
                    raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
                continue

def generate_slide_content(unit_name: str, outcomes: list, course_title: str = None, seta: str = None, nqf_level: str = None, job_id: str = None) -> dict:
    """Generates 1-2 slides for one syllabus unit: a teaching slide, and (where the
    content suits it) a practice/exercise slide applying the concept — matching the
    real pattern of alternating instruction and hands-on practice in accredited decks."""
    outcomes_text = "\n".join(f"- {o}" for o in outcomes)
    context_lines = []
    if seta:
        context_lines.append(f"SETA: {seta}")
    if nqf_level:
        context_lines.append(f"NQF Level: {nqf_level}")

    prompt = f"""You are creating slides for a South African SETA/QCTO-accredited workplace
training presentation, in the style of real accredited training decks: punchy fragment-style
bullets (not full sentences), concrete worked numbers where relevant, and a clear teach-then-
practice rhythm.

COURSE CONTEXT — these slides belong to the course "{course_title or 'Unspecified Course'}". Every
example, bullet, and worked exercise MUST be genuinely relevant to that course's actual subject
matter. If the unit name or an outcome is vague, interpret it strictly in the context of
"{course_title}" — never substitute in content from an unrelated field.

Unit: {unit_name}
{chr(10).join(context_lines)}

This unit covers these learning outcomes:
{outcomes_text}

Create ONE teaching slide covering the core concept(s) for this unit. If the outcomes involve
a calculation, procedure, or skill a learner could practically apply, ALSO create ONE practice
slide with a concrete exercise or scenario question the learner works through — using real,
specific numbers/examples, not abstract placeholders (e.g. "What's 15% of R8,000?" not
"calculate a percentage"). If the unit is purely conceptual with nothing to practically apply,
return only the teaching slide.

Bullets must be short fragments (4-8 words each), not full sentences. The teaching slide should
have 5-7 bullets covering the concept with real substance (definitions, key facts, or steps) —
not 2-3 sparse bullets. Where a worked example is used, show it step by step (e.g. "Step 1:
Round R2,899 to R3,000") as separate bullets, not compressed into one line.

Return ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "slides": [
    {{
      "slide_type": "teach",
      "title": "<short slide title>",
      "bullets": ["<fragment 1>", "<fragment 2>", "<fragment 3>"],
      "speaker_notes": "2-3 sentences the facilitator would say, including one concrete example.",
      "image_search_term": "2-4 word search phrase for a relevant photo, or null if not needed"
    }},
    {{
      "slide_type": "practice",
      "title": "<short slide title, e.g. 'Let's Practice!' or a scenario name>",
      "bullets": ["<exercise instruction or question with real numbers>", "<follow-up question>"],
      "speaker_notes": "What the facilitator says to set up this exercise.",
      "image_search_term": "2-4 word search phrase for a relevant photo, or null if not needed"
    }}
  ]
}}

Omit the practice slide entirely from the array if this unit has nothing practical to exercise."""

    for attempt in range(2):
        raw_response = _call_model("slide_content", prompt, max_tokens=2000, job_id=job_id)
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json_string(raw_response))
            except json.JSONDecodeError as exc:
                if attempt == 1:
                    raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
                continue

def generate_assessment_questions(unit_name: str, outcomes: list, course_title: str = None, seta: str = None, nqf_level: str = None, job_id: str = None) -> dict:
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

COURSE CONTEXT — this assessment belongs to the course "{course_title or 'Unspecified Course'}". Every
question and scenario MUST be genuinely relevant to that course's actual subject matter. If the unit
name or an outcome is vague, interpret it strictly in the context of "{course_title}" — never
substitute in content from an unrelated field.

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

DOCUMENT_PROMPT_FRAMING = {
    "learner_manual": "a Learner Manual — the core training content the learner studies to gain the knowledge and skills required by the unit standard",
    "facilitator_guide": "a Facilitator Guide — practical delivery notes for the trainer running this unit in a live session: session objectives, suggested timing per activity, materials/preparation needed, step-by-step delivery instructions (what to say, what to do, what to ask learners), and at least one suggested classroom activity or discussion prompt tied directly to this unit's topic",
    "formative_assessment": "a Formative Assessment — ongoing, low-stakes questions and activities used to check understanding as the learner progresses through this unit",
    "summative_assessment": "a Summative Assessment — formal end-of-unit questions and practical tasks used to certify competence in this unit",
    "assessment_guide": "an Assessment Guide — guidance for the Assessor on how to conduct and mark the assessment for this unit, including an evidence checklist",
    "moderator_guide": "a Moderator Guide — a checklist and guidance for the Moderator reviewing an Assessor's judgements for this unit",
    "poe_guide": "a Portfolio of Evidence Guide — instructions for the learner on what evidence to collect and how to compile it for this unit",
    "learner_induction_guide": "a Learner Induction Guide — an orientation document introducing the learner to the NQF learning approach, their rights and responsibilities, appeals procedures, and how assessment and certification work for this specific programme",
    "programme_strategy": "a Programme Strategy document — explains how the training programme's delivery and assessment strategy aligns with the outcomes of this unit, including delivery methods and resource requirements",
    "programme_alignment_matrix": "a Programme Alignment Matrix — a structured breakdown showing how this unit's learning outcomes align to assessment strategy and notional learning hours",
}


def generate_guide_section_content(document_subtype: str, unit_name: str, outcomes: list, course_title: str = None,
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
training programme, in the style of real accredited SETA learner/facilitator guides.
COURSE CONTEXT — this chapter belongs to the course "{course_title or 'Unspecified Course'}". Every
example, scenario, and piece of terminology in this chapter MUST be genuinely relevant to that course's
actual subject matter. If a unit name or outcome is vague, interpret it strictly in the context of
"{course_title}" — never substitute in content from an unrelated field.

Write content grounded in the ACTUAL subject matter of this unit — do not force unrelated industrial,
workplace-safety, or manufacturing framing onto topics that aren't about that (e.g. a programming or IT
topic should use programming examples, not steel plants or mining).

CITATIONS: If this topic genuinely involves South African law or regulation, you may cite REAL
acts/sections you are confident actually exist, and explicitly scope to the relevant ones for this
section. If the topic does NOT involve law/regulation, do not invent or reference any legislation at
all. Never invent a specific act name, section number, or standard number you are not confident is real.

Unit: {unit_name}
{chr(10).join(context_lines)}

This unit covers these learning outcomes:
{outcomes_text}

Write content appropriate to this specific document type — not generic textbook prose. Be practical
and specific to the role this document plays (e.g. a facilitator guide gives delivery instructions,
not learner-facing explanations; an assessment guide gives marking guidance, not questions themselves).

STRUCTURE, matching real accredited guides:
- Open the first section with a scope statement (an info_box block with bullet items) stating what
  this section covers
- Give genuine depth per section — several sentences of real substance, not a shallow gloss
- Where the topic has real formulas/calculations, always include a variable legend, not a bare formula
- Where comparing multiple options/approaches, use a real comparative table
- Address the reader directly and practically, appropriate to this document type's role

Return ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "intro": "1-2 sentence introduction to this section",
  "sections": [
    {{
      "heading": "<short section heading>",
      "blocks": [
        {{"type": "info_box", "title": "This Section Covers", "items": ["<point 1>", "<point 2>"]}},
        {{"type": "paragraph", "text": "Content appropriate to the document type, 80-150 words."}},
        {{"type": "table", "headers": ["Column A", "Column B"], "rows": [["value", "value"]]}},
        {{"type": "formula", "label": "Short name", "text": "The formula itself", "variables": [{{"symbol": "X", "meaning": "what X represents"}}]}},
        {{"type": "diagram", "steps": ["Step 1 label", "Step 2 label", "Step 3 label"], "caption": "What this diagram shows"}},
        {{"type": "list", "items": ["<item 1>", "<item 2>", "<item 3>"], "ordered": false}},
        {{"type": "image", "search_term": "SPECIFIC concrete search phrase naming the exact real object/scene relevant to this outcome (e.g. 'fire extinguisher workplace' not 'safety equipment')", "caption": "What this image shows"}}
      ]
    }}
  ],
  "key_points": ["<concise takeaway 1>", "<concise takeaway 2>"]
}}

Use "diagram" for any step-by-step process, sequence, or decision flow. Use "image" ONLY for a concrete physical object, tool, environment, or scene that a real photograph would meaningfully illustrate—never use "image" for abstract concepts or processes a diagram would represent better.

Only the FIRST section needs an info_box scope block. Every section needs at least one paragraph block. Only include scenario/table/formula/diagram/image/list blocks where genuinely relevant—do not force them into every section. One section per learning outcome. Plain text only inside strings—no asterisks, no markdown headers.

NEVER write a numbered or bulleted list inline inside a paragraph's text (e.g. "1) X 2) Y 3) Z" or
"firstly... secondly..."). Whenever you have 3 or more related items, use a "list" block instead —
set "ordered": true for sequential steps, "ordered": false for unordered items."""

    for attempt in range(2):
        raw_response = _call_model("textbook_writing", prompt, max_tokens=5000, job_id=job_id)
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json_string(raw_response))
            except json.JSONDecodeError as exc:
                if attempt == 1:
                    raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
                continue

def generate_facilitator_guide_content(unit_name: str, outcomes: list, course_title: str = None, seta: str = None, nqf_level: str = None, job_id: str = None) -> dict:
    """Generates model-answer assessment content for a Facilitator/Assessor Guide,
    matching the real INSETA-style format: activities with model answers marked by
    key scoreable points and mark allocations, plus unit standard reference data."""
    outcomes_text = "\n".join(f"- {o}" for o in outcomes)
    context_lines = []
    if seta:
        context_lines.append(f"SETA: {seta}")
    if nqf_level:
        context_lines.append(f"NQF Level: {nqf_level}")

    prompt = f"""You are writing a Facilitator/Assessor Guide for a South African
SETA/QCTO-accredited training programme, in the style of real accredited assessor guides.
This document gives the ASSESSOR the model answers and marking guidance for the formative
assessment activity covering this unit — it is not learner-facing content.

COURSE CONTEXT — this belongs to the course "{course_title or 'Unspecified Course'}". Every question
and model answer MUST be genuinely relevant to that course's actual subject matter. If the unit name
or an outcome is vague, interpret it strictly in the context of "{course_title}" — never substitute
in content from an unrelated field.

Unit: {unit_name}
{chr(10).join(context_lines)}

This unit covers these learning outcomes:
{outcomes_text}

Write ONE activity for this unit. The activity should have 1-3 questions that test the
learning outcomes. For each question, write a model answer as the assessor would expect it —
broken into distinct scoreable points (each point is something a learner could state to earn
a mark), and assign a total mark value to the question based on how many scoreable points
it has.

Return ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "activity_title": "<short activity name>",
  "questions": [
    {{
      "question_text": "<the question exactly as it would appear to the learner>",
      "marks": 8,
      "model_answer_points": ["<scoreable point 1>", "<scoreable point 2>", "<scoreable point 3>"]
    }}
  ],
  "evaluation_criteria": ["<short criterion the assessor checks off, e.g. 'Was the learner able to explain X?'>"]
}}

evaluation_criteria should be 1-3 short yes/no checklist items an assessor uses to confirm
the learner met this activity's requirements — phrased as questions."""

    for attempt in range(2):
        raw_response = _call_model("textbook_writing", prompt, max_tokens=5000, job_id=job_id)
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json_string(raw_response))
            except json.JSONDecodeError as exc:
                if attempt == 1:
                    raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
                continue

def generate_summative_assessment_content(title: str, units: list, seta: str = None, nqf_level: str = None, job_id: str = None) -> dict:
    """Generates a case-study-driven summative assessment covering all units of a syllabus:
    a realistic named-client scenario, followed by multiple choice questions referencing it,
    short knowledge questions, and a long/essay question — matching real accredited exam format."""
    all_outcomes = []
    for unit in units:
        all_outcomes.extend(unit.get("outcomes", []))
    outcomes_text = "\n".join(f"- {o}" for o in all_outcomes)

    context_lines = []
    if seta:
        context_lines.append(f"SETA: {seta}")
    if nqf_level:
        context_lines.append(f"NQF Level: {nqf_level}")

    prompt = f"""You are writing a Summative Assessment for a South African SETA/QCTO-accredited
training programme, in the style of real accredited exams.

Course: {title}
{chr(10).join(context_lines)}

This assessment must cover these learning outcomes across the whole course:
{outcomes_text}

Write a realistic CASE STUDY: a named individual or business client with specific, concrete
details (numbers, amounts, dates, circumstances) relevant to this course's subject matter.
This case study is the shared reference point for Section A's questions.

Then write:
- SECTION A: 6-10 multiple choice questions, each with 4 options, that require the learner to
  apply knowledge to the case study (reference specific details from it in the questions)
- SECTION B: 2-3 short knowledge questions (definitions/explanations, not tied to the case study)
- SECTION C: 1 long/essay question requiring a fuller written response

Assign realistic marks per question based on complexity.

Return ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "case_study": "The full case study text with specific concrete details.",
  "section_a": [
    {{"question_text": "<question referencing the case study>", "marks": 1, "options": ["<A>", "<B>", "<C>", "<D>"]}}
  ],
  "section_b": [
    {{"question_text": "<short knowledge question>", "marks": 3, "blank_lines": 4}}
  ],
  "section_c": [
    {{"question_text": "<essay question>", "marks": 10, "blank_lines": 15}}
  ]
}}"""

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

def generate_alignment_matrix_row(unit_name: str, outcome: str, course_title: str = None, job_id: str = None) -> dict:
    """Generates the assessment-type classification for one learning outcome, for the
    Programme Alignment Matrix — matching real INSETA-style traceability tables."""
    prompt = f"""For this single learning outcome from a South African SETA/QCTO-accredited
training programme, classify how it would typically be assessed.

COURSE CONTEXT — this belongs to the course "{course_title or 'Unspecified Course'}". Interpret the
unit and outcome strictly in that context.

Unit: {unit_name}
Outcome: {outcome}

Return ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "assessment_type": "<one of: MC, SQ, LQ, ESS, WPA, OTJ>",
  "notional_hours": 2
}}

Type codes: MC = Multiple Choice, SQ = Short Question, LQ = Long Question, ESS = Essay,
WPA = Workplace Application, OTJ = On The Job. notional_hours is a realistic estimate (1-8)
of study/practice hours for this one outcome."""

    raw_response = _call_model("slide_content", prompt, max_tokens=200, job_id=job_id)
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError:
        try:
            return json.loads(_repair_json_string(raw_response))
        except json.JSONDecodeError:
            return {"assessment_type": "SQ", "notional_hours": 2}  # safe fallback, never breaks the document

def generate_qcto_knowledge_module_content(module: dict, job_id: str = None) -> dict:
    """Generates content for one Knowledge Module (KM) of a QCTO qualification, matching
    the real structural pattern: module intro, sub-modules/units table, then detailed
    content per Knowledge Topic with a practical example/tip callout."""
    topics_text = "\n".join(
        f"- {t.get('topic_code', '')}: {t.get('title', '')} (weight: {t.get('weight', 'n/a')})"
        for t in module.get("topics", [])
    )

    prompt = f"""You are writing a Knowledge Module for a South African QCTO-accredited
occupational qualification, in the style of real accredited training material — detailed,
practical, and grounded in the actual subject matter (not generic filler).

Module: {module.get('title', '')}
Module Code: {module.get('module_code', '')}
NQF Level: {module.get('nqf_level', '')}
Credits: {module.get('credits', '')}

This module covers these Knowledge Topics:
{topics_text}

Write:
1. A short module introduction (2-3 sentences on why this module matters occupationally)
2. A short module purpose statement (1-2 sentences)
3. For EACH Knowledge Topic listed above, write genuinely detailed, specific content — real
   depth, not a shallow gloss. Include a "example_tip" block for each topic: a realistic
   workplace example paired with a practical, actionable tip.

Return ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "module_intro": "<2-3 sentence introduction>",
  "module_purpose": "<1-2 sentence purpose statement>",
  "topics": [
    {{
      "topic_code": "<matching topic code from the list above>",
      "topic_title": "<matching topic title>",
      "blocks": [
        {{"type": "paragraph", "text": "Detailed explanatory text, 150-300 words with real depth — definitions, mechanisms, step-by-step detail, common mistakes."}},
        {{"type": "paragraph", "text": "A second paragraph continuing the explanation with more depth, or covering a distinct sub-aspect of this topic."}},
        {{"type": "list", "items": ["<key point 1>", "<key point 2>", "<key point 3>", "<key point 4>"], "ordered": false}},
        {{"type": "diagram", "steps": ["<step 1>", "<step 2>", "<step 3>"], "caption": "What this diagram shows"}},
        {{"type": "image", "search_term": "SPECIFIC concrete search phrase for a real relevant photo", "caption": "What this image shows"}},
        {{"type": "example_tip", "example": "A detailed, realistic workplace example illustrating this topic.", "tip": "A practical, actionable tip related to this topic."}}
      ]
    }}
  ]
}}

NEVER invent specific standard numbers, unit standard IDs, or regulatory citations you are not
confident are real. Every topic MUST include AT LEAST TWO paragraph blocks with real depth (not
a shallow gloss — write like a genuine textbook chapter section) and exactly one example_tip
block. Include a diagram block where the topic involves a process/sequence, and an image block
where a real photo would meaningfully illustrate a concrete object/tool/environment. Use table
or formula blocks only where genuinely relevant to that specific topic."""

    for attempt in range(2):
        raw_response = _call_model("textbook_writing", prompt, max_tokens=8000, job_id=job_id)
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json_string(raw_response))
            except json.JSONDecodeError as exc:
                if attempt == 1:
                    raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
                continue

def structure_qcto_syllabus_from_text(raw_text: str) -> dict:
    """Parses raw text extracted from an uploaded QCTO curriculum document into the
    structured modules format (KM/PM/WM with codes, credits, topics, elements, IACs)."""
    truncated_text = raw_text[:40000]

    prompt = f"""You are an instructional designer. Below is raw text extracted from an uploaded
South African QCTO curriculum document. Extract and structure its Knowledge Modules (KM),
Practical Skill Modules (PM), and Work Experience Modules (WM).

Raw extracted text:
---
{truncated_text}
---

Return ONLY valid JSON (no markdown, no commentary) matching this exact shape:
{{
  "qualification_code": "<the qualification code, e.g. 718302-000-00>",
  "qualification_title": "<the full qualification title>",
  "modules": [
    {{
      "module_type": "KM",
      "module_code": "<full module code>",
      "title": "<module title>",
      "nqf_level": "<NQF level>",
      "credits": <credits as a number>,
      "topics": [
        {{
          "topic_code": "<topic code, e.g. KM-01-KT02>",
          "title": "<topic title>",
          "weight": "<weight percentage if given, else null>",
          "elements": ["<topic element 1>", "<topic element 2>"],
          "assessment_criteria": ["<IAC 1>", "<IAC 2>"]
        }}
      ]
    }},
    {{
      "module_type": "PM",
      "module_code": "<full module code>",
      "title": "<module title>",
      "nqf_level": "<NQF level>",
      "credits": <credits as a number>,
      "performance_assessment": ["<PA element 1>", "<PA element 2>"],
      "applied_knowledge": ["<AK element 1>", "<AK element 2>"],
      "assessment_criteria": ["<IAC 1>", "<IAC 2>"]
    }},
    {{
      "module_type": "WM",
      "module_code": "<full module code>",
      "title": "<module title>",
      "nqf_level": "<NQF level>",
      "credits": <credits as a number>,
      "purpose": "<purpose statement>",
      "work_experience_elements": ["<WE element 1>", "<WE element 2>"]
    }}
  ]
}}

Extract EVERY module and topic/element you can find in the text — do not skip any. Preserve
the original codes, titles, and wording as closely as possible. If credits/NQF level for a
specific module isn't stated near it, infer from context or use the qualification-level value."""

    for attempt in range(2):
        raw_response = _call_model("syllabus_structuring", prompt, max_tokens=16000)
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json_string(raw_response))
            except json.JSONDecodeError as exc:
                if attempt == 1:
                    raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
                continue

def _extract_relevant_window(raw_text: str, module_code: str, window_size: int = 30000) -> str:
    """Finds the LAST occurrence of a module's code in the document — curriculum documents
    typically list every module in a brief summary near the start, then cover each one in
    full detail later. The last occurrence is far more likely to be the actual detailed
    section than the first (which is usually just the summary mention)."""
    idx = raw_text.rfind(module_code)
    if idx == -1:
        return raw_text[:window_size]
    start = max(0, idx - 2000)
    end = min(len(raw_text), idx + window_size)
    return raw_text[start:end]

def extract_qcto_module_topics(module_code: str, module_title: str, raw_text: str) -> list:
    """Extracts detailed topics/elements/assessment criteria for ONE specific module from
    the full curriculum text — used as a second pass after structure_qcto_syllabus_from_text
    identifies the module list, avoiding truncation issues on large documents by focusing
    each call on just one module's relevant section."""
    truncated_text = _extract_relevant_window(raw_text, module_code)  # still capped, but each call only needs to find ONE module's section

    prompt = f"""Below is the full text of a South African QCTO curriculum document. Find the
section specifically covering this module, and extract its detailed topic breakdown.

Module Code: {module_code}
Module Title: {module_title}

Full curriculum text:
---
{truncated_text}
---

Return ONLY valid JSON (no markdown, no commentary) matching this exact shape:
{{
  "topics": [
    {{
      "topic_code": "<topic code, e.g. KM-01-KT02>",
      "title": "<topic title>",
      "weight": "<weight percentage if given, else null>",
      "elements": ["<topic element 1>", "<topic element 2>"],
      "assessment_criteria": ["<IAC 1>", "<IAC 2>"]
    }}
  ]
}}

If you cannot find this module's detailed topic breakdown in the text, return {{"topics": []}}.
Do not invent topics that aren't genuinely present in the text."""

    raw_response = _call_model("syllabus_structuring", prompt, max_tokens=3000)
    try:
        result = json.loads(raw_response)
    except json.JSONDecodeError:
        try:
            result = json.loads(_repair_json_string(raw_response))
        except json.JSONDecodeError:
            return []
    return result.get("topics", [])


def extract_qcto_pm_details(module_code: str, module_title: str, raw_text: str) -> dict:
    """Extracts detailed performance assessment, applied knowledge, and assessment criteria
    for ONE specific Practical Skill Module (PM) — second-pass extraction, same pattern as
    extract_qcto_module_topics, to avoid truncation on large documents."""
    truncated_text = _extract_relevant_window(raw_text, module_code)

    prompt = f"""Below is the full text of a South African QCTO curriculum document. Find the
section specifically covering this Practical Skill Module, and extract its detail.

Module Code: {module_code}
Module Title: {module_title}

Full curriculum text:
---
{truncated_text}
---

Return ONLY valid JSON (no markdown, no commentary) matching this exact shape:
{{
  "performance_assessment": ["<PA element 1>", "<PA element 2>"],
  "applied_knowledge": ["<AK element 1>", "<AK element 2>"],
  "assessment_criteria": ["<IAC 1>", "<IAC 2>"]
}}

If you cannot find this module's detail in the text, return empty arrays for each field.
Do not invent content that isn't genuinely present in the text."""

    raw_response = _call_model("syllabus_structuring", prompt, max_tokens=3000)
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError:
        try:
            return json.loads(_repair_json_string(raw_response))
        except json.JSONDecodeError:
            return {"performance_assessment": [], "applied_knowledge": [], "assessment_criteria": []}


def extract_qcto_wm_details(module_code: str, module_title: str, raw_text: str) -> dict:
    """Extracts detailed work experience elements for ONE specific Work Experience Module
    (WM) — second-pass extraction, same pattern as extract_qcto_module_topics."""
    truncated_text = _extract_relevant_window(raw_text, module_code)

    prompt = f"""Below is the full text of a South African QCTO curriculum document. Find the
section specifically covering this Work Experience Module, and extract its detail.

Module Code: {module_code}
Module Title: {module_title}

Full curriculum text:
---
{truncated_text}
---

Return ONLY valid JSON (no markdown, no commentary) matching this exact shape:
{{
  "purpose": "<purpose statement for this module>",
  "work_experience_elements": ["<WE element 1>", "<WE element 2>"]
}}

If you cannot find this module's detail in the text, return an empty string for purpose and
an empty array for work_experience_elements. Do not invent content that isn't genuinely present."""

    raw_response = _call_model("syllabus_structuring", prompt, max_tokens=3000)
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError:
        try:
            return json.loads(_repair_json_string(raw_response))
        except json.JSONDecodeError:
            return {"purpose": "", "work_experience_elements": []}