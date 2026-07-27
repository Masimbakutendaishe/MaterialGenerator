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

    prompt = f"""You are a subject-matter expert writing a chapter for a South African
SETA/QCTO-accredited training textbook, in the style of real accredited SETA learner guides.

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
        {{"type": "image", "search_term": "2-4 word search phrase for a relevant stock photo", "caption": "What this image shows"}}
      ]
    }}
  ],
  "key_points": ["<concise takeaway 1>", "<concise takeaway 2>", "<concise takeaway 3>"]
}}

Only the FIRST section needs an info_box scope block. Every section needs at least one paragraph
block. Only include scenario/table/formula/diagram/image blocks where genuinely relevant — do not
force them into every section. One section per learning outcome. Plain text only inside strings —
no asterisks, no markdown headers."""

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

Bullets must be short fragments (4-8 words each), not full sentences. Where a worked example
is used, show it step by step (e.g. "Step 1: Round R2,899 to R3,000").

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
        raw_response = _call_model("slide_content", prompt, max_tokens=1200, job_id=job_id)
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json_string(raw_response))
            except json.JSONDecodeError as exc:
                if attempt == 1:
                    raise RuntimeError(f"AI response was not valid JSON after retry: {exc}") from exc
                continue

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
training programme, in the style of real accredited SETA learner/facilitator guides.

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
        {{"type": "image", "search_term": "2-4 word search phrase for a relevant stock photo", "caption": "What this image shows"}}
      ]
    }}
  ],
  "key_points": ["<concise takeaway 1>", "<concise takeaway 2>"]
}}

Only the FIRST section needs an info_box scope block. Only include table, formula, diagram, or image
blocks where genuinely relevant to this specific document type — most sections should just be a
paragraph block. One section per learning outcome. Plain text only, no markdown."""

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

def generate_facilitator_guide_content(unit_name: str, outcomes: list, seta: str = None, nqf_level: str = None, job_id: str = None) -> dict:
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