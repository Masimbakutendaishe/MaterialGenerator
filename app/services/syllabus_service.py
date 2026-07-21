# Parse/normalize/generate syllabi
"""Parses uploaded files and structures raw syllabus text via AI."""
import io
from docx import Document
from pypdf import PdfReader


def extract_text_from_upload(file_storage) -> str:
    """Extracts plain text from an uploaded .docx, .pdf, or .txt file.
    file_storage is a Werkzeug FileStorage object from request.files."""
    filename = (file_storage.filename or "").lower()
    file_bytes = file_storage.read()

    if filename.endswith(".docx"):
        doc = Document(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    if filename.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(file_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if filename.endswith(".txt"):
        return file_bytes.decode("utf-8", errors="ignore")

    raise ValueError(f"Unsupported file type: {filename}. Supported: .docx, .pdf, .txt")