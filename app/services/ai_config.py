"""Maps generation tasks to specific models/providers. Change routing here only —
nothing elsewhere in the app should hardcode a model name."""

TASK_MODEL_MAP = {
    "syllabus_generation": {"provider": "groq", "model": "openai/gpt-oss-120b"},   # free tier for testing
    "textbook_writing":    {"provider": "anthropic", "model": "claude-sonnet-5"},
    "slide_content":       {"provider": "anthropic", "model": "claude-sonnet-5"},
}


def get_model_for_task(task: str) -> dict:
    if task not in TASK_MODEL_MAP:
        raise ValueError(f"No model configured for task '{task}'")
    return TASK_MODEL_MAP[task]