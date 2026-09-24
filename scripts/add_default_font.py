"""One-time automation: adds _set_default_font(doc, brand_colors.get("font")) right after
every 'doc = Document()' line across the QCTO document builder files, and ensures each
file imports _set_default_font from document_service. Run once, then discard.

Usage: python scripts/add_default_font.py
"""
import re
import glob

TARGET_FILES = [
    f for f in glob.glob("app/services/*.py")
    if f != "app/services/document_service.py"
]

import_pattern = re.compile(
    r"(from app\.services\.document_service import \(\n(?:.*\n)*?)(\))"
)


def add_import(match):
    body = match.group(1)
    if "_set_default_font" in body:
        return match.group(0)
    stripped = body.rstrip().rstrip(",")
    return stripped + ", _set_default_font,\n" + match.group(2)


changed_files = []
skipped_no_doc_call = []
skipped_no_import = []

for path in TARGET_FILES:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if "doc = Document()" not in content:
        continue

    original = content

    if "from app.services.document_service import (" in content:
        content = import_pattern.sub(add_import, content, count=1)
    elif "_set_default_font" not in content:
        skipped_no_import.append(path)
        continue

    new_content, n = re.subn(
        r"(\n(\s*)doc = Document\(\)\n)",
        r'\1\2_set_default_font(doc, brand_colors.get("font"))\n',
        content,
    )

    if n == 0:
        skipped_no_doc_call.append(path)
        continue

    if new_content != original:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        changed_files.append((path, n))

print(f"Changed {len(changed_files)} files:")
for path, n in changed_files:
    print(f"  {path}  ({n} call site(s) added)")

if skipped_no_import:
    print(f"\nSkipped (no document_service import found — needs manual review): {skipped_no_import}")
if skipped_no_doc_call:
    print(f"\nSkipped (had 'doc = Document()' text but regex found 0 matches — needs manual review): {skipped_no_doc_call}")