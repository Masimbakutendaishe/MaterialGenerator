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

def _has_real_content(items) -> bool:
    """True only if a list/value genuinely contains real extracted content — used to detect
    modules with no source material, so we can write an honest placeholder instead of letting
    the AI invent plausible-looking but ungrounded content."""
    if not items:
        return False
    if isinstance(items, list):
        return len(items) > 0
    if isinstance(items, str):
        return bool(items.strip())
    return bool(items)

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

    for attempt in range(2):
        raw_response = _call_model("syllabus_structuring", prompt, max_tokens=6000)
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json_string(raw_response))
            except json.JSONDecodeError as exc:
                if attempt == 1:
                    raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
                continue

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
set "ordered": true for sequential steps, "ordered": false for unordered items.

CRITICAL JSON SAFETY: never use a literal double-quote character (") inside any string value, even
for quoted speech, terms, or titles — this breaks JSON parsing. If you need to show quoted speech
or a term in quotes, use single quotes instead (e.g. the supervisor said 'stop the line', not the
supervisor said "stop the line")."""

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
set "ordered": true for sequential steps, "ordered": false for unordered items.

CRITICAL JSON SAFETY: never use a literal double-quote character (") inside any string value, even
for quoted speech, terms, or titles — this breaks JSON parsing. If you need to show quoted speech
or a term in quotes, use single quotes instead (e.g. the supervisor said 'stop the line', not the
supervisor said "stop the line")."""

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
    if not _has_real_content(module.get("topics")):
        return {
            "module_intro": f"No specific curriculum content was provided for '{module.get('title', 'this module')}' in the uploaded document.",
            "module_purpose": "Please supply source material (topics, elements, or guidelines) for this module to generate detailed content.",
            "topics": [],
        }

    def _topic_line(t):
        lines = [f"- {t.get('topic_code', '')}: {t.get('title', '')} (weight: {t.get('weight', 'n/a')})"]
        elements = t.get("elements") or []
        if elements:
            lines.append("  This topic's specific elements, ALL of which must be genuinely covered:")
            for el in elements:
                code = el.get("code") if isinstance(el, dict) else None
                text = el.get("text", "") if isinstance(el, dict) else (el or "")
                prefix = f"  - {code}: " if code else "  - "
                lines.append(f"{prefix}{text}")
        if t.get("guidelines"):
            lines.append(f"  Guidelines on what to cover: {t.get('guidelines')}")
        return "\n".join(lines)

    topics_text = "\n".join(_topic_line(t) for t in module.get("topics", []))

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
   depth, not a shallow gloss. Where a topic lists specific elements above, EVERY SINGLE
   element must be genuinely addressed somewhere in that topic's content — do not omit, skip,
   or silently merge away any element, even if the topic has many. Where a topic has
   "Guidelines on what to cover" listed above, your content MUST genuinely address everything
   those guidelines specify — treat them as a real requirement, not optional context. Include
   an "example_tip" block for each topic: a realistic workplace example paired with a
   practical, actionable tip.

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
    # 150,000 chars comfortably fits every provider in the chain (Gemini Flash, Groq's
    # 120B, Claude Sonnet 5 all support far more) and is large enough to reach the TOC/
    # module-summary section of real multi-module qualification documents — the previous
    # 40,000-char limit was cutting curricula off after roughly one module's worth of text,
    # which is why only KM-01/PM-01 were ever extracted from full qualification uploads.
    truncated_text = raw_text[:150000]

    prompt = f"""You are an instructional designer. Below is raw text extracted from an uploaded
South African QCTO curriculum document. Extract and structure its Knowledge Modules (KM),
Practical Skill Modules (PM), and Work Experience Modules (WM).

IMPORTANT — QCTO curriculum documents vary significantly in format. Different providers use
different code schemes, section header styles, and layouts. Do NOT assume one rigid structure.
Before extracting, check these signals, in order of reliability:
1. If the document has a Table of Contents or Curriculum Summary listing modules with codes
   and/or page numbers, use it as your primary index of what modules genuinely exist — this is
   usually the most complete and reliable listing.
2. Cross-reference against any "Total number of credits for [Module Type] Modules" summary
   lines, which often confirm the full set of modules per category.
3. Scan the body of the document for module/module-group headings even if their exact code
   format differs from a standard "QUALCODE-KM-01" pattern (e.g. some documents use only a
   number, only a title, or a different separator).

Every module you find — regardless of exact formatting — MUST be included. Do not skip a module
just because its heading style differs from others in the same document.

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
          "elements": [{{"code": "<element code, e.g. KT0101 — the SHORT code as printed, without repeating the topic code prefix>", "text": "<the full element text>"}}],
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
      "performance_assessment": [{{"code": "<PA code, e.g. PA0101 — the SHORT code as printed>", "text": "<the full element text>"}}],
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
        raw_response = _call_model("syllabus_structuring", prompt, max_tokens=24000)
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json_string(raw_response))
            except json.JSONDecodeError as exc:
                if attempt == 1:
                    raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
                continue

def _extract_relevant_window(raw_text: str, module_code: str, module_title: str = "", window_size: int = 60000) -> str:
    """Finds the section of the document most likely to contain a module's real detail,
    trying several signals in order since curriculum documents vary in format:
    1. The LAST occurrence of the module's exact code (detail sections usually come after
       an earlier summary mention, so the last occurrence is the more reliable one).
    2. If the code isn't found verbatim, the LAST occurrence of the module's title instead —
       some documents use headings by title rather than repeating the code.
    3. If neither is found, fall back to scanning from the start of the document."""
    idx = raw_text.rfind(module_code) if module_code else -1

    if idx == -1 and module_title:
        idx = raw_text.rfind(module_title)

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
    truncated_text = _extract_relevant_window(raw_text, module_code, module_title)  # still capped, but each call only needs to find ONE module's section

    prompt = f"""Below is the full text of a South African QCTO curriculum document. Find the
section specifically covering this module, and extract its detailed topic breakdown.

IMPORTANT — for each topic element: these are usually printed with their own short code,
distinct from the parent topic code — e.g. under topic "KM-01-KT01", each element carries a
code like "KT0101", "KT0102", etc. (the numbering resets per topic and does NOT repeat the
full topic code). This can appear as a bulleted/numbered list ("KT0101 The role of the
advanced emergency first aider...") or as a TABLE with columns like "TOPIC ELEMENT CODE" and
"TOPIC ELEMENT TITLE" (in which case the code and text may be in separate cells/lines with no
bullet character). Capture both the code and the full text for every element — if a genuine
per-element code truly isn't present in the source for a given element, leave "code" as null
rather than inventing one, but the "text" must still be captured.

IMPORTANT — beyond the topic elements themselves, carefully check the text UNDERNEATH each
topic/element for any guideline, explanatory, or "what to cover" text — this is often a
paragraph or short section explaining what the topic should include, separate from the bare
element list. Capture this as "guidelines" per topic if present. Do not skip this even if it
appears in a different format (a paragraph, a bulleted note, a "Guidelines for..." heading).

IMPORTANT — for assessment_criteria: search specifically for a section headed "Internal
Assessment Criteria" (this is the standard QCTO term, sometimes just called IAC), appearing
after each topic's element list. This section can appear in TWO different formats depending
on the source document — check for BOTH:
1. A bulleted list, often prefixed with a code like "IAC0201", e.g.: "IAC0201 Define and
   describe the concepts which underpin work, working and working relationships".
2. A TABLE with columns such as "IAC CODE" and "IAC DESCRIPTION" (sometimes also "% OF TIME
   TO BE SPENT"), where each row is one criterion — e.g. a row with "IAC0101" in one column
   and "Explain the role of the advanced emergency first aider..." in the next. When text is
   extracted from a table, the code and description may appear on the same line or on
   separate lines/paragraphs without any bullet character — do not assume a bullet symbol is
   required for this to be a real IAC entry.
Extract each criterion (whichever format it's in) as its own entry in assessment_criteria
(you may drop the leading IAC code, keeping just the criterion text, or keep it — either is
fine as long as the real wording is preserved). This is a distinct section from the topic's
"elements" list — do not confuse the two, and do not skip searching for it even if it isn't
immediately adjacent to the elements, or if it's several paragraphs/pages later in the
document. Only return an empty assessment_criteria array if you have genuinely searched the
ENTIRE section for this topic and this content truly isn't present — do not give up after a
quick scan, and do not stop searching just because the topic has many elements.

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
      "elements": [{{"code": "<element code, e.g. KT0101 — the SHORT code as printed, without repeating the topic code prefix>", "text": "<the full element text>"}}],
      "guidelines": "<any explanatory/guideline text found underneath this topic, describing what should be covered — or null if none found>",
      "assessment_criteria": ["<IAC 1>", "<IAC 2>"]
    }}
  ]
}}
If you cannot find this module's detailed topic breakdown in the text, return {{"topics": []}}.
Do not invent topics or guidelines that aren't genuinely present in the text."""
    raw_response = _call_model("syllabus_structuring", prompt, max_tokens=8000)
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
    truncated_text = _extract_relevant_window(raw_text, module_code, module_title)

    prompt = f"""Below is the full text of a South African QCTO curriculum document. Find the
section specifically covering this Practical Skill Module, and extract its detail.

IMPORTANT — beyond the performance assessment and applied knowledge elements themselves,
carefully check the text UNDERNEATH them for any guideline, explanatory, or "what to cover"
text — this is often a paragraph or short section explaining what should actually be done or
assessed, separate from the bare element list. Capture this as "guidelines" if present, even
if it appears in a different format (a paragraph, a bulleted note, a "Guidelines for..." heading).

IMPORTANT — for performance_assessment: these are usually printed with their own short
code, e.g. "PA0101 Assess and manage an emergency scene..." — often under a heading like
"PRACTICAL SKILL ACTIVITY ELEMENT CODES" or similar, possibly as a table with the code and
text in separate columns/lines with no bullet character. Capture both the code and the full
text for every item — if a genuine code truly isn't present for a given item, leave "code"
as null rather than inventing one, but the "text" must still be captured.

IMPORTANT — for assessment_criteria: search specifically for a section headed "Internal
Assessment Criteria" (the standard QCTO term, sometimes just called IAC), appearing after
the performance assessment elements. This section can appear in TWO different formats

IMPORTANT — for assessment_criteria: search specifically for a section headed "Internal
Assessment Criteria" (the standard QCTO term, sometimes just called IAC), appearing after
the performance assessment elements. This section can appear in TWO different formats
depending on the source document — check for BOTH:
1. A bulleted list, often prefixed with a code like "IAC0101", e.g.: "IAC0101 The reasons
   for the project reflect the desired outcomes of the project".
2. A TABLE with columns such as "IAC CODE" and "IAC DESCRIPTION", where each row is one
   criterion. When text is extracted from a table, the code and description may appear on
   the same line or on separate lines/paragraphs without any bullet character — do not
   assume a bullet symbol is required for this to be a real IAC entry.
Extract each criterion (whichever format it's in) as its own entry in assessment_criteria
(you may drop the leading IAC code, keeping just the criterion text, or keep it — either is
fine as long as the real wording is preserved). This is a distinct section from the
performance assessment/applied knowledge elements above it — do not confuse the two, and do
not skip searching for it even if it isn't immediately adjacent, or if it's several
paragraphs/pages later. Only return an empty assessment_criteria array if you have genuinely
searched the ENTIRE section for this module and this content truly isn't present — do not
give up after a quick scan.

Module Code: {module_code}
Module Title: {module_title}

Full curriculum text:
---
{truncated_text}
---

Return ONLY valid JSON (no markdown, no commentary) matching this exact shape:
{{
  "performance_assessment": [{{"code": "<PA code, e.g. PA0101 — the SHORT code as printed>", "text": "<the full element text>"}}],
  "applied_knowledge": ["<AK element 1>", "<AK element 2>"],
  "guidelines": "<any explanatory/guideline text found underneath these elements — or null if none found>",
  "assessment_criteria": ["<IAC 1>", "<IAC 2>"]
}}

If you cannot find this module's detail in the text, return empty arrays for each field and null for guidelines.
Do not invent content that isn't genuinely present in the text."""

    raw_response = _call_model("syllabus_structuring", prompt, max_tokens=6000)
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
    truncated_text = _extract_relevant_window(raw_text, module_code, module_title)

    prompt = f"""Below is the full text of a South African QCTO curriculum document. Find the
section specifically covering this Work Experience Module, and extract its detail.

IMPORTANT — beyond the work experience elements themselves, carefully check the text
UNDERNEATH each element for any guideline, explanatory, or "what to cover" text (often
labeled something like "Guidelines for Work Experiences") — this explains what should
actually be done for that element, separate from the bare element list. Capture this as
"guidelines" if present, even if it appears in a different format.

Module Code: {module_code}
Module Title: {module_title}

Full curriculum text:
---
{truncated_text}
---

Return ONLY valid JSON (no markdown, no commentary) matching this exact shape:
{{
  "purpose": "<purpose statement for this module>",
  "work_experience_elements": ["<WE element 1>", "<WE element 2>"],
  "guidelines": "<any explanatory/guideline text found underneath the elements — or null if none found>"
}}

If you cannot find this module's detail in the text, return an empty string for purpose, an
empty array for work_experience_elements, and null for guidelines. Do not invent content that
isn't genuinely present."""

    raw_response = _call_model("syllabus_structuring", prompt, max_tokens=6000)
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError:
        try:
            return json.loads(_repair_json_string(raw_response))
        except json.JSONDecodeError:
            return {"purpose": "", "work_experience_elements": []}

def generate_qcto_practical_module_content(module: dict, job_id: str = None) -> dict:
    """Generates content for one Practical Skill Module (PM) of a QCTO qualification,
    matching the real pattern: module intro/purpose, sub-modules table, then per-unit
    'Scope of Practical Skill' framing, detailed PA content, an example/tip box, and an
    exercise (scenario + task + questions)."""
    if not _has_real_content(module.get("performance_assessment")):
        return {
            "module_intro": f"No specific curriculum content was provided for '{module.get('title', 'this module')}' in the uploaded document.",
            "module_purpose": "Please supply source material (performance assessment elements or guidelines) for this module to generate detailed content.",
            "units": [],
        }

    pa_text = "\n".join(
        f"- {(pa.get('code') + ': ') if isinstance(pa, dict) and pa.get('code') else ''}{pa.get('text', '') if isinstance(pa, dict) else pa}"
        for pa in module.get("performance_assessment", [])
    )
    guidelines_text = module.get("guidelines")

    prompt = f"""You are writing a Practical Skills Module for a South African QCTO-accredited
occupational qualification, in the style of real accredited training material — detailed,
practical, hands-on.

Module: {module.get('title', '')}
Module Code: {module.get('module_code', '')}
NQF Level: {module.get('nqf_level', '')}
Credits: {module.get('credits', '')}

This module's Performance Assessment elements:
{pa_text}
{f"Guidelines on what to cover for this module: {guidelines_text}" if guidelines_text else ""}

IMPORTANT — where guidelines are provided above, your content MUST genuinely address everything
they specify — treat them as a real requirement, not optional context.

IMPORTANT — every single Performance Assessment element listed above MUST be genuinely covered
within one of the units below. Do not omit, skip, silently merge away, or generically summarize
past any element — each one needs real, specific coverage somewhere in the units you produce.
Use as many units as needed to cover all of them properly (typically 2-4 for a short list, more
if there are many distinct elements) — completeness comes before brevity.

Write:
1. A module introduction (2-3 sentences)
2. A module purpose statement (1-2 sentences)
3. Group the Performance Assessment elements into logical "units" (practical skill units),
   covering every element listed above. For EACH unit, write:
   - A short "Scope of Practical Skill" framing statement
   - Genuinely detailed, specific content covering the PA elements in that unit
   - One example_tip block
   - One exercise block (a realistic scenario, a task instruction, and 1-2 reflection questions)

Return ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "module_intro": "<2-3 sentences>",
  "module_purpose": "<1-2 sentences>",
  "units": [
    {{
      "unit_title": "<short unit title>",
      "scope_statement": "<Scope of Practical Skill framing, 1-2 sentences>",
      "blocks": [
        {{"type": "paragraph", "text": "Detailed explanatory text, 150-300 words with real depth."}},
        {{"type": "list", "items": ["<key point 1>", "<key point 2>"], "ordered": false}},
        {{"type": "diagram", "steps": ["<step 1>", "<step 2>", "<step 3>"], "caption": "What this diagram shows"}},
        {{"type": "image", "search_term": "SPECIFIC concrete search phrase for a real relevant photo", "caption": "What this image shows"}},
        {{"type": "example_tip", "example": "A realistic workplace example.", "tip": "A practical, actionable tip."}},
        {{"type": "exercise", "scenario": "A realistic workplace scenario.", "task": "What the learner must do.", "questions": ["<reflection question 1>", "<reflection question 2>"]}}
      ]
    }}
  ]
}}

NEVER invent specific standard numbers or regulatory citations you are not confident are real.
Every unit MUST include at least two paragraph blocks, one example_tip block, and one exercise
block. Include a diagram block where the unit involves a step-by-step process/procedure, and an
image block where a real photo would meaningfully illustrate a concrete tool/equipment/environment.
Use table blocks only where genuinely relevant."""

    for attempt in range(2):
        # Higher budget than KM's equivalent call — PM units are no longer capped at 2-4,
        # so a module with many performance-assessment elements can legitimately need more
        # units/output to cover all of them without truncating mid-JSON.
        raw_response = _call_model("textbook_writing", prompt, max_tokens=12000, job_id=job_id)
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json_string(raw_response))
            except json.JSONDecodeError as exc:
                if attempt == 1:
                    raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
                continue


def generate_qcto_workplace_module_content(module: dict, job_id: str = None) -> dict:
    """Generates content for one Workplace/Work Experience Module (WM) of a QCTO
    qualification, matching the real pattern: module intro/purpose, then per-unit 'Scope
    of Work Experience' framing with nested Key Work Activities (concept, step-by-step
    process, practical example), plus an example/tip box and exercise per unit."""
    if not _has_real_content(module.get("work_experience_elements")):
        return {
            "module_intro": f"No specific curriculum content was provided for '{module.get('title', 'this module')}' in the uploaded document.",
            "module_purpose": "Please supply source material (work experience elements or guidelines) for this module to generate detailed content.",
            "units": [],
        }

    we_text = "\n".join(f"- {we}" for we in module.get("work_experience_elements", []))
    guidelines_text = module.get("guidelines")

    prompt = f"""You are writing a Workplace Module for a South African QCTO-accredited
occupational qualification, in the style of real accredited training material — detailed,
grounded in genuine on-the-job activity.

Module: {module.get('title', '')}
Module Code: {module.get('module_code', '')}
NQF Level: {module.get('nqf_level', '')}
Credits: {module.get('credits', '')}
Purpose: {module.get('purpose', '')}

This module's Work Experience elements:
{we_text}
{f"Guidelines on what to cover for this module: {guidelines_text}" if guidelines_text else ""}

IMPORTANT — where guidelines are provided above, your content MUST genuinely address everything
they specify — treat them as a real requirement, not optional context.

Write:
1. A module introduction (2-3 sentences)
2. A module purpose statement (1-2 sentences)
3. Group the Work Experience elements into 2-3 logical "units". For EACH unit, write:
   - A "Scope of Work Experience" framing statement (1-2 sentences)
   - 2-3 "Key Work Activities" — each with a concept explanation, a step-by-step process
     (numbered), and a practical example grounded in a realistic workplace scenario
   - One example_tip block
   - One exercise block (scenario + task + 1-2 reflection questions)

Return ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "module_intro": "<2-3 sentences>",
  "module_purpose": "<1-2 sentences>",
  "units": [
    {{
      "unit_title": "<short unit title>",
      "scope_statement": "<Scope of Work Experience framing>",
      "activities": [
        {{
          "activity_code": "<e.g. WA0101>",
          "activity_title": "<short activity title>",
          "concept_explanation": ["<concept point 1>", "<concept point 2>"],
          "process_steps": ["<step 1>", "<step 2>", "<step 3>"],
          "practical_example": "A detailed, realistic workplace example illustrating this activity."
        }}
      ],
      "example_tip": {{"example": "A realistic workplace example.", "tip": "A practical, actionable tip."}},
      "exercise": {{"scenario": "A realistic workplace scenario.", "task": "What the learner must do.", "questions": ["<question 1>", "<question 2>"]}}
    }}
  ]
}}

NEVER invent specific standard numbers or regulatory citations you are not confident are real.
Every unit needs at least 2 activities, one example_tip, and one exercise."""

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

def generate_qcto_video_guide_content(module: dict, job_id: str = None) -> dict:
    """Generates a video resource guide entry for one QCTO module — for each topic/unit,
    a description and a genuine YouTube search query (not a fabricated direct link, since
    we can't know real video URLs — a search link is honest and still useful)."""
    items_text = ""
    if module.get("module_type") == "KM":
        items_text = "\n".join(f"- {t.get('title', '')}" for t in module.get("topics", []))
    elif module.get("module_type") == "PM":
        items_text = "\n".join(f"- {pa.get('text', '') if isinstance(pa, dict) else pa}" for pa in module.get("performance_assessment", []))
    elif module.get("module_type") == "WM":
        items_text = "\n".join(f"- {we}" for we in module.get("work_experience_elements", [])[:6])

    prompt = f"""You are curating a video training resource guide for a South African QCTO-accredited
occupational qualification.

Module: {module.get('title', '')}
Module Code: {module.get('module_code', '')}

Topics/items covered in this module:
{items_text}

For EACH topic/item, suggest ONE genuinely relevant, specific YouTube search query (not a
fabricated URL — a search query someone could type into YouTube to find real, relevant videos),
a short description of what kind of video content would help (2-3 sentences), and 2-3 learning
outcomes the learner should take away from watching such videos.

Return ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "entries": [
    {{
      "topic_name": "<matching topic/item name>",
      "description": "2-3 sentences describing what kind of video content would help here.",
      "search_query": "SPECIFIC YouTube search query, e.g. 'multihead weigher calibration tutorial'",
      "learning_outcomes": ["<outcome 1>", "<outcome 2>", "<outcome 3>"]
    }}
  ]
}}

Make each search query specific and genuinely likely to surface real, relevant training videos —
not generic. Do not invent a specific video title or channel name, only a search query."""

    for attempt in range(2):
        raw_response = _call_model("slide_content", prompt, max_tokens=3000, job_id=job_id)
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json_string(raw_response))
            except json.JSONDecodeError as exc:
                if attempt == 1:
                    raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
                continue

def generate_qcto_assessment_content(module: dict, job_id: str = None) -> dict:
    """Generates an assessment for one KM or PM module, matching the real pattern: questions
    organized into labeled sections, with blank answer space for written responses and
    occasional short calculation-style questions for KM specifically."""
    module_type = module.get("module_type", "KM")

    if module_type == "KM":
        items_text = "\n".join(f"- {t.get('title', '')}" for t in module.get("topics", []))
        question_style = (
            "Mix short-answer explanation questions with occasional calculation/practical "
            "questions where genuinely relevant. Group questions into 2-3 labeled sections "
            "(e.g. SECTION A, SECTION B), each covering a related cluster of topics."
        )
    else:  # PM
        items_text = "\n".join(f"- {pa.get('text', '') if isinstance(pa, dict) else pa}" for pa in module.get("performance_assessment", []))
        question_style = (
            "Write practical questions grounded in ONE detailed, specific, realistic South African "
            "workplace scenario — use real South African place names, industries, and workplace "
            "conditions appropriate to this module's subject matter (not generic \"your workplace\" "
            "placeholders). Set up the scenario once, then ask the learner to explain or describe how "
            "they would carry out each task within that specific scenario, referencing realistic "
            "equipment and situations. Group questions into 2-3 labeled sections covering related PA "
            "elements. Each question needs generous blank answer space, since these require fuller "
            "written responses."
        )

    prompt = f"""You are writing an assessment for a South African QCTO-accredited occupational
qualification, in the style of real accredited assessments.

Module: {module.get('title', '')}
Module Type: {module_type}
Module Code: {module.get('module_code', '')}

This module covers:
{items_text}

{question_style}

Return ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "sections": [
    {{
      "section_label": "SECTION A: <short section theme>",
      "questions": [
        {{"question_text": "<question, may include a calculation if genuinely relevant>", "blank_lines": 3, "marks": 5}}
      ]
    }}
  ]
}}

Write 4-6 questions per section, 2-3 sections total. blank_lines should reflect how much space
a genuine written answer would need (2-6 lines). Assign a realistic mark value to each
question based on its complexity (a short factual question might be worth 2-3 marks, a
fuller explanation 5-8 marks). Never invent specific standard numbers or regulatory
citations you are not confident are real."""

    for attempt in range(2):
        raw_response = _call_model("textbook_writing", prompt, max_tokens=4000, job_id=job_id)
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json_string(raw_response))
            except json.JSONDecodeError as exc:
                if attempt == 1:
                    raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
                continue

def derive_title_from_text(raw_text: str) -> str:
    """Derives a proper, human-readable course/qualification title from the actual document
    content — used when the user doesn't provide a title on upload, instead of falling back
    to the raw filename (which is often poorly formatted, e.g. 'SPCurriculumFirstAid.pdf')."""
    truncated_text = raw_text[:3000]

    prompt = f"""Below is the start of an uploaded training curriculum/syllabus document.
Identify the real course or qualification title it represents, and write it as a clean,
properly formatted title (proper spacing, capitalization, no file extensions or codes unless
genuinely part of the title).

Document text:
---
{truncated_text}
---

Return ONLY the title text itself, nothing else — no quotes, no markdown, no explanation."""

    try:
        result = _call_model("slide_content", prompt, max_tokens=50)
        cleaned = result.strip().strip('"').strip("'")
        return cleaned if cleaned else "Untitled Syllabus"
    except Exception:
        return "Untitled Syllabus"


def reason_isa_traceability(km_modules: list, pm_modules: list, wm_modules: list, job_id: str = None) -> dict:
    """Reasons about genuine competency links between each KM topic's real Internal
    Assessment Criteria and PM/WM modules' real activities — a semantic judgement, not
    keyword/title matching. Returns {topic_code: {"pm": [...], "wm": [...], "reasoning":
    "..."}}, defaulting any topic the model omits to no links (an honest default, not a
    crash). Raises on failure so the caller can fall back to a simpler heuristic."""
    km_lines = []
    for module in km_modules:
        for topic in module.get("topics", []):
            iac = topic.get("assessment_criteria") or []
            iac_text = "; ".join(iac) if iac else "(none extracted)"
            km_lines.append(f"- {topic.get('topic_code', '')}: {topic.get('title', '')} | IAC: {iac_text}")

    pm_lines = []
    for module in pm_modules:
        pa = module.get("performance_assessment") or []
        pa_texts = [p.get("text", "") if isinstance(p, dict) else p for p in pa]
        pa_text = "; ".join(t for t in pa_texts if t) if pa_texts else "(none extracted)"
        pm_lines.append(f"- {module.get('module_code', '')}: {module.get('title', '')} | Activities: {pa_text}")

    wm_lines = []
    for module in wm_modules:
        we = module.get("work_experience_elements") or []
        we_text = "; ".join(we) if we else "(none extracted)"
        wm_lines.append(f"- {module.get('module_code', '')}: {module.get('title', '')} | Activities: {we_text}")

    prompt = f"""You are analysing a QCTO occupational qualification to build a traceability table
linking Knowledge Module (KM) topics to related Practical Module (PM) and Workplace Module (WM)
content, based on genuine competency overlap — not just similar wording.

KM Topics (with their Internal Assessment Criteria):
{chr(10).join(km_lines)}

Practical Modules (with their real activities):
{chr(10).join(pm_lines)}

Workplace Modules (with their real activities):
{chr(10).join(wm_lines)}

For EACH KM topic, decide which PM module(s) and WM module(s), if any, contain practical or
workplace activity that would genuinely help demonstrate or reinforce the same underlying
competency as that KM topic's Internal Assessment Criteria. Do NOT force a link — many KM topics
will have zero linked PM/WM modules, and that is the correct, honest answer for them. Only link
where the actual skill or knowledge area substantively overlaps.

Return ONLY valid JSON in this exact format, one entry per KM topic:
{{
  "links": [
    {{"km_topic_code": "...", "linked_pm_codes": ["..."], "linked_wm_codes": ["..."], "reasoning": "one short sentence"}}
  ]
}}"""

    for attempt in range(2):
        raw_response = _call_model("syllabus_structuring", prompt, max_tokens=6000, job_id=job_id)
        try:
            data = json.loads(raw_response)
        except json.JSONDecodeError:
            try:
                data = json.loads(_repair_json_string(raw_response))
            except json.JSONDecodeError as exc:
                if attempt == 1:
                    raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
                continue

        lookup = {}
        for entry in data.get("links", []):
            code = entry.get("km_topic_code", "")
            lookup[code] = {
                "pm": entry.get("linked_pm_codes", []),
                "wm": entry.get("linked_wm_codes", []),
                "reasoning": entry.get("reasoning", ""),
            }
        # Ensure every real topic has an entry, even if the AI omitted it
        for module in km_modules:
            for topic in module.get("topics", []):
                code = topic.get("topic_code", "")
                if code not in lookup:
                    lookup[code] = {"pm": [], "wm": [], "reasoning": ""}
        return lookup


def generate_km_exam_objective_questions(km_modules: list, job_id: str = None) -> dict:
    """Generates the objective-format exam sections (Multiple Choice, Matching Columns,
    True/False) from real KM topic/element content — these formats need genuine authored
    content (plausible distractors, real matching pairs, a true/false mix), not something
    that can be deterministically templated from raw extracted text. Targets roughly 10 MC
    questions, 5 matching pairs, and 10 true/false statements, matching a typical accredited
    exam's mark weighting for these sections (20/10/20 marks at 2 marks each)."""
    km_lines = []
    for module in km_modules:
        km_lines.append(f"Module {module.get('module_code', '')}: {module.get('title', '')}")
        for topic in module.get("topics", []):
            raw_elements = topic.get("elements") or []
            element_texts = [el.get("text", "") if isinstance(el, dict) else (el or "") for el in raw_elements]
            elements_text = "; ".join(t for t in element_texts if t) if element_texts else "(no elements extracted)"
            km_lines.append(f"  - {topic.get('topic_code', '')}: {topic.get('title', '')} | Elements: {elements_text}")

    prompt = f"""Below is the real Knowledge Module structure of a QCTO occupational qualification.

{chr(10).join(km_lines)}

Using ONLY the real content above, generate three objective-format exam sections for a
Knowledge Module exam paper:

1. MULTIPLE CHOICE — 10 questions. Each question tests understanding of a real topic or
   element listed above. Provide 5 answer options (A-E), exactly one correct. Distractors
   should be plausible, not obviously wrong.

2. MATCHING COLUMNS — 5 pairs. Each pair matches a real term/concept from the content above
   with its correct description (also drawn from or consistent with the content above).

3. TRUE OR FALSE — 10 statements. Mix genuinely true statements (drawn directly from the
   content) with genuinely false ones (a plausible-sounding but incorrect claim about the
   same content) — roughly half and half, not obviously skewed to one side.

Return ONLY valid JSON in this exact format:
{{
  "multiple_choice": [
    {{"stem": "...", "options": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}}, "correct": "B"}}
  ],
  "matching_columns": [
    {{"term": "...", "description": "..."}}
  ],
  "true_false": [
    {{"statement": "...", "is_true": true}}
  ]
}}"""

    for attempt in range(2):
        raw_response = _call_model("syllabus_structuring", prompt, max_tokens=8000, job_id=job_id)
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json_string(raw_response))
            except json.JSONDecodeError as exc:
                if attempt == 1:
                    raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
                continue



def generate_model_answers_for_questions(module: dict, assessment_content: dict, job_id: str = None) -> dict:
    """Writes a Marking Memorandum for the REAL formative assessment questions already
    generated for this module (via generate_qcto_assessment_content) — does NOT invent new
    questions, only produces model answers/marks for the exact questions given, so the
    Facilitator Guide's Marking Memorandum genuinely corresponds to what the learner sees in
    the actual Formative Assessment document, rather than a disconnected parallel set."""
    module_title = module.get("title", "")
    module_code = module.get("module_code", "")

    questions_lines = []
    for section in assessment_content.get("sections", []):
        questions_lines.append(f"Section: {section.get('section_label', '')}")
        for q in section.get("questions", []):
            questions_lines.append(f"  - {q.get('question_text', '')}")
    questions_text = "\n".join(questions_lines)

    prompt = f"""You are writing a Marking Memorandum for an assessor, for the REAL formative
assessment questions below — these are the EXACT questions the learner will actually answer.
Do NOT invent new questions or alter the wording of the ones given.

Module: {module_title} ({module_code})

The real assessment questions, organized by section:
{questions_text}

For EACH question above, write a model answer as the assessor would expect it — broken into
distinct scoreable points (each point is something a learner could state to earn a mark), and
assign a total mark value based on how many scoreable points it has. Preserve the exact
question text and section structure given above.

Return ONLY valid JSON (no markdown, no commentary) matching this exact shape:
{{
  "sections": [
    {{
      "section_label": "<matching section label from above, verbatim>",
      "questions": [
        {{
          "question_text": "<matching question text from above, verbatim>",
          "marks": 5,
          "model_answer_points": ["<scoreable point 1>", "<scoreable point 2>"]
        }}
      ]
    }}
  ],
  "evaluation_criteria": ["<short yes/no checklist item an assessor uses, e.g. 'Was the learner able to explain X?'>"]
}}"""

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



def generate_km_formative_questions(topic: dict, job_id: str = None) -> dict:
    """Writes a genuine, marked, format-varied set of formative assessment questions for
    one KM topic — grounded in and covering EVERY real Internal Assessment Criterion for
    that topic, mixing open-response, diagram, and multiple-choice formats appropriately
    per criterion, rather than reprinting the criteria as bare bullet points."""
    topic_code = topic.get("topic_code", "")
    title = topic.get("title", "")
    criteria = topic.get("assessment_criteria") or []
    criteria_text = "\n".join(f"- {c}" for c in criteria)

    prompt = f"""You are writing formative assessment class activity questions for a South African
QCTO-accredited Knowledge Module topic, to be handwritten by the learner during training.

Topic: {topic_code} — {title}

This topic's real Internal Assessment Criteria, which your questions MUST genuinely and
completely cover — every single one must be addressed by at least one question, do not skip
or silently merge any away:
{criteria_text}

Write a set of questions that together cover all the criteria above, MIXING question formats
appropriately — some open-response (an explanation the learner writes by hand), some diagram
(where a criterion involves anatomy, structure, or a process better shown as a labeled
drawing), and some multiple choice (for more factual/classification-style criteria) — choose
whichever format best fits each specific criterion, don't force one format on everything.
Assign a reasonable mark value to each question based on its complexity.

Return ONLY valid JSON (no markdown, no commentary) matching this exact shape:
{{
  "questions": [
    {{"type": "open", "question_text": "...", "marks": 5, "blank_lines": 4, "source_criterion": "<which criterion above this addresses>"}},
    {{"type": "diagram", "question_text": "...", "marks": 5, "blank_lines": 6, "source_criterion": "..."}},
    {{"type": "multiple_choice", "question_text": "...", "marks": 2, "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}}, "correct": "B", "source_criterion": "..."}}
  ]
}}"""

    for attempt in range(2):
        raw_response = _call_model("textbook_writing", prompt, max_tokens=4000, job_id=job_id)
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json_string(raw_response))
            except json.JSONDecodeError as exc:
                if attempt == 1:
                    raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
                continue



def generate_pm_facilitation_steps(module: dict, job_id: str = None) -> dict:
    """Writes genuine, specific step-by-step facilitator instructions for EVERY real
    performance-assessment item in this module — how to actually demonstrate the skill,
    what to coach for during guided practice, signs the learner is ready for independent
    practice, and debrief questions to ask — enough real guidance for a first-time
    facilitator to run the session confidently, not a template phrase with the item text
    substituted in."""
    pa_items = module.get("performance_assessment") or []
    pa_lines = []
    for pa in pa_items:
        code = pa.get("code") if isinstance(pa, dict) else None
        text = pa.get("text", "") if isinstance(pa, dict) else (pa or "")
        pa_lines.append(f"- {code + ': ' if code else ''}{text}")
    pa_text = "\n".join(pa_lines)

    prompt = f"""You are writing a facilitator guide for a completely inexperienced, first-time
facilitator who has never taught this practical skill before — they need real, specific,
actionable instructions, not vague activity labels.

Module: {module.get('title', '')}

Every real practical skill this facilitator must teach — EVERY ONE below needs its own
guidance, do not skip or merge any away:
{pa_text}

For EACH skill above, write:
1. demonstration_steps — a numbered sequence of exactly what the facilitator physically does
   and says while demonstrating this skill to the group, specific enough that someone who has
   never taught before could follow it directly.
2. coaching_tips — specific things to watch for and correct while learners attempt the skill
   under supervision (common mistakes, safety points, technique cues).
3. readiness_signs — concrete, observable signs that a learner is ready to move from guided to
   independent practice on this specific skill.
4. debrief_questions — 2-3 specific discussion questions tied to this exact skill, not generic
   ("what went well") — questions that surface real understanding or gaps.

Return ONLY valid JSON (no markdown, no commentary) matching this exact shape:
{{
  "items": [
    {{
      "pa_text": "<matching skill text from above, verbatim>",
      "demonstration_steps": ["Step 1...", "Step 2..."],
      "coaching_tips": ["Watch for...", "Correct..."],
      "readiness_signs": ["Learner can...", "Learner consistently..."],
      "debrief_questions": ["Specific question 1?", "Specific question 2?"]
    }}
  ]
}}"""

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



def generate_pm_scenario_and_questions(module: dict, job_id: str = None) -> dict:
    """Writes ONE detailed, specific South African-contextualized workplace scenario for a
    PM module's Portfolio of Evidence practical activities, plus a genuine series of
    scenario-embedded questions per real skill — rather than a generic "your organisation"
    placeholder scenario and bare "perform a demonstration of X" instructions."""
    module_title = module.get("title", "")
    pa_items = module.get("performance_assessment") or []
    pa_lines = []
    for pa in pa_items:
        code = pa.get("code") if isinstance(pa, dict) else None
        text = pa.get("text", "") if isinstance(pa, dict) else (pa or "")
        pa_lines.append(f"- {code + ': ' if code else ''}{text}")
    pa_text = "\n".join(pa_lines)

    prompt = f"""You are writing a Portfolio of Evidence practical assessment scenario for a South
African QCTO-accredited practical module.

Module: {module_title}

Every real practical skill this assessment must cover through the scenario below — EVERY
ONE needs its own set of questions, do not skip or merge any away:
{pa_text}

Write ONE detailed, specific, realistic South African workplace scenario — use real South
African place names, industries, and workplace conditions appropriate to this module's
subject matter (not a generic "your organisation" placeholder). The scenario should be
concrete enough that a learner can picture the exact situation, people involved, and setting.

Then, for EACH real practical skill listed above, write 2-3 specific questions that are
embedded in and reference the scenario — not generic "perform a demonstration of X"
instructions, but real questions that test the learner's understanding and application of
that specific skill within the scenario's context.

Return ONLY valid JSON (no markdown, no commentary) matching this exact shape:
{{
  "scenario": "The full scenario text, with real South African specificity.",
  "items": [
    {{
      "pa_text": "<matching skill text from above, verbatim>",
      "questions": ["Scenario-embedded question 1?", "Scenario-embedded question 2?"]
    }}
  ]
}}"""

    for attempt in range(2):
        raw_response = _call_model("textbook_writing", prompt, max_tokens=6000, job_id=job_id)
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json_string(raw_response))
            except json.JSONDecodeError as exc:
                if attempt == 1:
                    raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
                continue



def generate_km_short_answer_questions(topic: dict, job_id: str = None) -> dict:
    """Writes 1-3 genuine, well-phrased short-answer exam questions for one KM topic,
    consolidating multiple related Internal Assessment Criteria into comprehensive
    questions where sensible — rather than reprinting each individual criterion as its own
    bare 'question,' which produces an impractically long exam for topics with many
    criteria."""
    topic_code = topic.get("topic_code", "")
    title = topic.get("title", "")
    criteria = topic.get("assessment_criteria") or []
    criteria_text = "\n".join(f"- {c}" for c in criteria)

    prompt = f"""You are writing short-answer exam questions for a South African QCTO-accredited
Knowledge Module topic.

Topic: {topic_code} — {title}

This topic's real Internal Assessment Criteria, which your questions must together cover:
{criteria_text}

Write 1 to 3 genuine, well-phrased exam questions (NOT the criteria reprinted verbatim as
questions) that together require the learner to demonstrate understanding of everything
listed above. Consolidate related criteria into single, comprehensive questions where
sensible, rather than writing one question per individual criterion — this must read like a
real exam, not a checklist. Assign a realistic mark value to each question reflecting how
much of the topic it covers.

Return ONLY valid JSON (no markdown, no commentary) matching this exact shape:
{{
  "questions": [
    {{"question_text": "A genuine, well-phrased exam question.", "marks": 8, "blank_lines": 5}}
  ]
}}"""

    for attempt in range(2):
        raw_response = _call_model("textbook_writing", prompt, max_tokens=2000, job_id=job_id)
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json_string(raw_response))
            except json.JSONDecodeError as exc:
                if attempt == 1:
                    raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
                continue