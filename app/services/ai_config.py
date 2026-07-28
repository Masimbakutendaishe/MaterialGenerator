"""Maps generation tasks to an ORDERED CHAIN of providers, tried in sequence: free
options first, paid last. If one provider is out of credits/quota or exhausts its
retries, the next in the chain is tried automatically."""


DEFAULT_CHAIN = [
    {"provider": "nyra", "model": "agnes-2.0-flash"},
    {"provider": "gemini", "model": "gemini-flash-latest"},
    {"provider": "groq", "model": "openai/gpt-oss-120b"},
    {"provider": "anthropic", "model": "claude-sonnet-5"},
]

TASK_MODEL_MAP = {
    "syllabus_generation":   {"chain": DEFAULT_CHAIN},
    "syllabus_structuring":  {"chain": DEFAULT_CHAIN},
    "textbook_writing":      {"chain": DEFAULT_CHAIN},
    "slide_content":         {"chain": DEFAULT_CHAIN},
}


def get_model_for_task(task: str) -> dict:
    if task not in TASK_MODEL_MAP:
        raise ValueError(f"No model configured for task '{task}'")
    return TASK_MODEL_MAP[task]