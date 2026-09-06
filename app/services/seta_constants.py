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
