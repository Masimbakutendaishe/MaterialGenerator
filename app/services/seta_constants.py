"""Canonical list of South Africa's 21 SETAs — slug (used as the stored accreditation_info
value and the logo filename) mapped to full display name. Single source of truth, imported
by both the syllabus creation form (for the dropdown) and document_service.py (to look up
each SETA's logo file and full name for document headers)."""

SETA_CHOICES = {
    "agriseta": "AgriSETA",
    "bankseta": "BANKSETA",
    "cathsseta": "CATHSSETA",
    "ceta": "CETA",
    "chieta": "CHIETA",
    "etdpseta": "ETDP SETA",
    "ewseta": "EWSETA",
    "fasset": "FASSET",
    "foodbevseta": "FoodBev SETA",
    "fpmseta": "FP&M SETA",
    "hwseta": "HWSETA",
    "inseta": "InSETA",
    "lgseta": "LGSETA",
    "merseta": "merSETA",
    "mictseta": "MICT SETA",
    "mqa": "MQA",
    "pseta": "PSETA",
    "sasseta": "SASSETA",
    "servicesseta": "Services SETA",
    "teta": "TETA",
    "wrseta": "W&RSETA",
}


def get_seta_name(slug: str) -> str:
    """Returns the full display name for a SETA slug, or the slug itself (title-cased) if
    it's not one of the known 21 — keeps old free-text values from earlier syllabi from
    breaking rather than showing nothing."""
    return SETA_CHOICES.get(slug, slug.title() if slug else "")


def get_seta_logo_path(slug: str) -> str:
    """Returns the expected static-file path for a SETA's logo, or empty string if the
    slug isn't recognized. Callers should check the file actually exists before using it
    (a SETA being in the dropdown doesn't guarantee its logo has been uploaded yet)."""
    if slug not in SETA_CHOICES:
        return ""
    return f"app/static/seta_logos/{slug}.png"

# Friendly display names for document/material subtypes, used consistently across the
# document-type dropdown and the generation status tables — a single source of truth so
# these can't drift out of sync with each other again.
DOCUMENT_DISPLAY_NAMES = {
    "textbook": "Textbook (Word)",
    "presentation": "Presentation (PowerPoint)",
    "assessment": "Assessment",
    "facilitator_guide": "Facilitator Guide",
    "poe_guide": "Portfolio of Evidence Guide",
    "programme_alignment_matrix": "Programme Alignment Matrix",
    "qcto_knowledge_modules": "KM Learner Guide",
    "qcto_practical_modules": "PM Learner Guide",
    "qcto_workplace_modules": "WM Learner Guide",
    "qcto_workplace_logbook": "WM Logbook",
    "qcto_video_guide": "Video Guide",
    "qcto_km_assessment": "KM Assessment",
    "qcto_pm_assessment": "PM Assessment",
    "qcto_km_facilitator_guide": "KM Facilitator Guide",
    "qcto_km_assessment_guide": "KM Assessment Guide",
    "qcto_km_poe": "KM Portfolio of Evidence",
    "qcto_km_learner_workbook": "KM Learner Workbook",
    "qcto_isa": "ISA Traceability Document",
    "qcto_pm_facilitator_guide": "PM Facilitator Guide",
    "qcto_pm_assessment_guide": "PM Assessment Guide",
    "qcto_pm_poe": "PM Portfolio of Evidence",
    "qcto_wm_supervisor_guide": "WM Guide for Industry Supervisors",
    "qcto_final_exam": "Final Exam",
    "qcto_fisa": "FISA (Final Integrated Summative Assessment)",
    "qcto_learning_matrix": "Learning Matrix",
    "qcto_km_powerpoint": "KM PowerPoint (per module, ZIP)",
    "qcto_pm_powerpoint": "PM PowerPoint (per module, ZIP)",
}


def document_display_name(value):
    """Looks up the friendly display name for a document type value, falling back to a
    title-cased, underscore-replaced version for any type not in the mapping (so a
    newly-added document type never renders as a raw, unreadable value)."""
    if not value:
        return ""
    if value in DOCUMENT_DISPLAY_NAMES:
        return DOCUMENT_DISPLAY_NAMES[value]
    return value.replace("_", " ").replace("qcto ", "").title()
