"""Finds real, verified PDF links for legal/standard documents referenced in generated
learner material, via the Serper.dev search API. Only ever returns a link whose URL
genuinely ends in .pdf, as returned by the search engine itself — never a link invented
or guessed by the AI, since that is exactly where hallucination risk lives. A document
this can't find a genuine PDF for is simply omitted, not filled with a weaker guess."""
import requests
from flask import current_app


def search_for_document_pdf(document_name: str) -> dict | None:
    """Searches Serper.dev for a document by name and returns the first genuinely-PDF
    result, or None if no PDF result was found or the API call failed. Never raises —
    a search failure should mean 'no reference found', not a broken generation job."""
    api_key = current_app.config.get("SERPER_API_KEY")
    if not api_key:
        return None

    try:
        response = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": f"{document_name} filetype:pdf"},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json()
    except Exception:
        return None

    for result in results.get("organic", []):
        url = result.get("link", "")
        if url.lower().split("?")[0].endswith(".pdf"):
            return {
                "name": document_name,
                "url": url,
                "title": result.get("title", ""),
            }
    return None


def find_referenced_document_pdfs(document_names: list) -> list:
    """Runs search_for_document_pdf for a list of document names and returns only the
    ones a genuine PDF was actually found for — silently dropping the rest, since an
    unverifiable reference is worse than no reference at all."""
    found = []
    for name in document_names:
        result = search_for_document_pdf(name)
        if result:
            found.append(result)
    return found