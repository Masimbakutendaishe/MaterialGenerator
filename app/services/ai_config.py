"""Maps generation tasks to specific models/providers, with an automatic fallback
provider used if the primary provider is out of credits/quota. Change routing here only —
nothing elsewhere in the app should hardcode a model name."""

TASK_MODEL_MAP = {
    "syllabus_generation":   {"provider": "anthropic", "model": "claude-sonnet-5", "fallback_provider": "groq", "fallback_model": "openai/gpt-oss-120b"},
    "syllabus_structuring":  {"provider": "anthropic", "model": "claude-sonnet-5", "fallback_provider": "groq", "fallback_model": "openai/gpt-oss-120b"},
    "textbook_writing":      {"provider": "anthropic", "model": "claude-sonnet-5", "fallback_provider": "groq", "fallback_model": "openai/gpt-oss-120b"},
    "slide_content":         {"provider": "anthropic", "model": "claude-sonnet-5", "fallback_provider": "groq", "fallback_model": "openai/gpt-oss-120b"},
}


def get_model_for_task(task: str) -> dict:
    if task not in TASK_MODEL_MAP:
        raise ValueError(f"No model configured for task '{task}'")
    return TASK_MODEL_MAP[task]