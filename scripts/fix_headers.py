"""One-shot script: adds accreditation_info/document_label support across all QCTO document
builders. Run from the project root: python scripts/fix_headers.py

Safe by design: uses regex with flexible whitespace matching, so it doesn't depend on
guessing exact indentation widths (which vary per function name length) — it matches
whatever indentation is actually in the file. Every replacement is checked to occur exactly
once before being applied; if a file's content doesn't match what's expected (already
edited, or genuinely differs), it's skipped with a clear message rather than silently
corrupting anything. All file I/O uses explicit UTF-8.
"""
import re
import subprocess
import sys

SERVICES_DIR = "app/services"

STANDARD_FILES = [
    ("qcto_km_assessment_guide_service.py", "build_qcto_km_assessment_guide_docx", "KM Assessment Guide"),
    ("qcto_km_facilitator_guide_service.py", "build_qcto_km_facilitator_guide_docx", "KM Facilitator Guide"),
    ("qcto_km_learner_workbook_service.py", "build_qcto_km_learner_workbook_docx", "KM Learner Workbook"),
    ("qcto_km_poe_service.py", "build_qcto_km_poe_docx", "KM Portfolio of Evidence"),
    ("qcto_learning_matrix_service.py", "build_qcto_learning_matrix_docx", "Learning Matrix"),
    ("qcto_pm_assessment_guide_service.py", "build_qcto_pm_assessment_guide_docx", "PM Assessment Guide"),
    ("qcto_pm_facilitator_guide_service.py", "build_qcto_pm_facilitator_guide_docx", "PM Facilitator Guide"),
    ("qcto_pm_poe_service.py", "build_qcto_pm_poe_docx", "PM Portfolio of Evidence"),
    ("qcto_practical_module_service.py", "build_qcto_practical_module_docx", "PM Learner Guide"),
    ("qcto_wm_supervisor_guide_service.py", "build_qcto_wm_supervisor_guide_docx", "WM Guide for Industry Supervisors"),
    ("qcto_workplace_module_service.py", "build_qcto_workplace_module_docx", "WM Guide"),
    ("qcto_fisa_service.py", "build_qcto_fisa_docx", "FISA"),
    ("qcto_isa_service.py", "build_qcto_isa_docx", "ISA Traceability Document"),
]


def regex_replace_once(content, pattern, replacement, label):
    """Like re.sub, but requires exactly one match — raises clearly if zero or multiple,
    rather than silently applying to the wrong number of places."""
    matches = list(re.finditer(pattern, content, re.MULTILINE))
    if len(matches) != 1:
        raise ValueError(f"  [{label}] expected exactly 1 regex match, found {len(matches)} — skipping this file entirely")
    return content[:matches[0].start()] + re.sub(pattern, replacement, matches[0].group(0), count=1) + content[matches[0].end():]


def process_standard_file(filename, stem, document_label):
    path = f"{SERVICES_DIR}/{filename}"
    print(f"Processing {filename} ...")

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Main function signature — \s+ tolerates whatever the real continuation-line
    # indentation actually is, no need to compute or guess it.
    sig_pattern = (
        rf"def {re.escape(stem)}\(title: str, syllabus_content: dict, organization_name: str = None,\n"
        rf"\s+logo_bytes: bytes = None, brand_colors: dict = None,\n"
        rf"\s+job_id: str = None\) -> BytesIO:\n"
        rf"    brand_colors = brand_colors or \{{\}}"
    )
    matches = list(re.finditer(sig_pattern, content))
    if len(matches) != 1:
        raise ValueError(f"  [main signature] expected exactly 1 match, found {len(matches)} — skipping this file entirely")
    original_block = matches[0].group(0)
    # Extract the real continuation-line indent actually used in this file
    indent_match = re.search(r"\n(\s+)logo_bytes: bytes = None", original_block)
    real_indent = indent_match.group(1)
    new_block = (
        f"def {stem}(title: str, syllabus_content: dict, organization_name: str = None,\n"
        f"{real_indent}logo_bytes: bytes = None, brand_colors: dict = None,\n"
        f"{real_indent}accreditation_info: dict = None, job_id: str = None) -> BytesIO:\n"
        f"    accreditation_info = dict(accreditation_info or {{}})\n"
        f"    if syllabus_content.get(\"qualification_code\"):\n"
        f"        accreditation_info.setdefault(\"qualification_code\", syllabus_content.get(\"qualification_code\"))\n"
        f"    brand_colors = brand_colors or {{}}"
    )
    content = content[:matches[0].start()] + new_block + content[matches[0].end():]

    # Header call — single line, no multi-line indentation risk
    old_header = (
        '    _add_branded_header_footer(doc, logo_bytes=logo_bytes, qualification_name=qualification_title, '
        'organization_name=organization_name, primary_hex=primary_hex)'
    )
    if content.count(old_header) != 1:
        raise ValueError(f"  [header call] expected exactly 1 match, found {content.count(old_header)} — skipping this file entirely")
    new_header = (
        '    _add_branded_header_footer(doc, logo_bytes=logo_bytes, qualification_name=qualification_title, '
        f'organization_name=organization_name, primary_hex=primary_hex, accreditation_info=accreditation_info, document_label="{document_label}")'
    )
    content = content.replace(old_header, new_header)

    # Adapter signature — same flexible-indent approach
    adapter_stem = stem + "_adapter"
    adapter_pattern = (
        rf"def {re.escape(adapter_stem)}\(title, units, organization_name=None, seta=None,\n"
        rf"\s+nqf_level=None, logo_bytes=None, brand_colors=None,\n"
        rf"\s+job_id=None, \*\*kwargs\):"
    )
    matches = list(re.finditer(adapter_pattern, content))
    if len(matches) != 1:
        raise ValueError(f"  [adapter signature] expected exactly 1 match, found {len(matches)} — skipping this file entirely")
    original_adapter_block = matches[0].group(0)
    adapter_indent_match = re.search(r"\n(\s+)nqf_level=None", original_adapter_block)
    real_adapter_indent = adapter_indent_match.group(1)
    new_adapter_block = (
        f"def {adapter_stem}(title, units, organization_name=None, seta=None,\n"
        f"{real_adapter_indent}nqf_level=None, logo_bytes=None, brand_colors=None,\n"
        f"{real_adapter_indent}accreditation_info=None, job_id=None, **kwargs):"
    )
    content = content[:matches[0].start()] + new_adapter_block + content[matches[0].end():]

    # Adapter return call — single, consistent block regardless of function name
    old_return = "        brand_colors=brand_colors,\n        job_id=job_id,\n    )"
    if content.count(old_return) != 1:
        raise ValueError(f"  [adapter return] expected exactly 1 match, found {content.count(old_return)} — skipping this file entirely")
    new_return = "        brand_colors=brand_colors,\n        accreditation_info=accreditation_info,\n        job_id=job_id,\n    )"
    content = content.replace(old_return, new_return)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  OK — 4 replacements applied")


def process_km_learner_guide():
    """qcto_knowledge_module_service.py has a multi-line header call, handled separately —
    only main signature + adapter are touched here; header call needs manual follow-up."""
    filename = "qcto_knowledge_module_service.py"
    stem = "build_qcto_knowledge_module_docx"
    path = f"{SERVICES_DIR}/{filename}"
    print(f"Processing {filename} (special case) ...")

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    sig_pattern = (
        rf"def {re.escape(stem)}\(title: str, syllabus_content: dict, organization_name: str = None,\n"
        rf"\s+logo_bytes: bytes = None, brand_colors: dict = None,\n"
        rf"\s+job_id: str = None\) -> BytesIO:\n"
        rf"    brand_colors = brand_colors or \{{\}}"
    )
    matches = list(re.finditer(sig_pattern, content))
    if len(matches) != 1:
        raise ValueError(f"  [main signature] expected exactly 1 match, found {len(matches)}")
    original_block = matches[0].group(0)
    indent_match = re.search(r"\n(\s+)logo_bytes: bytes = None", original_block)
    real_indent = indent_match.group(1)
    new_block = (
        f"def {stem}(title: str, syllabus_content: dict, organization_name: str = None,\n"
        f"{real_indent}logo_bytes: bytes = None, brand_colors: dict = None,\n"
        f"{real_indent}accreditation_info: dict = None, job_id: str = None) -> BytesIO:\n"
        f"    accreditation_info = dict(accreditation_info or {{}})\n"
        f"    if syllabus_content.get(\"qualification_code\"):\n"
        f"        accreditation_info.setdefault(\"qualification_code\", syllabus_content.get(\"qualification_code\"))\n"
        f"    brand_colors = brand_colors or {{}}"
    )
    content = content[:matches[0].start()] + new_block + content[matches[0].end():]

    adapter_stem = stem + "_adapter"
    adapter_pattern = (
        rf"def {re.escape(adapter_stem)}\(title, units, organization_name=None, seta=None,\n"
        rf"\s+nqf_level=None, logo_bytes=None, brand_colors=None,\n"
        rf"\s+job_id=None, \*\*kwargs\):"
    )
    matches = list(re.finditer(adapter_pattern, content))
    if len(matches) != 1:
        raise ValueError(f"  [adapter signature] expected exactly 1 match, found {len(matches)}")
    original_adapter_block = matches[0].group(0)
    adapter_indent_match = re.search(r"\n(\s+)nqf_level=None", original_adapter_block)
    real_adapter_indent = adapter_indent_match.group(1)
    new_adapter_block = (
        f"def {adapter_stem}(title, units, organization_name=None, seta=None,\n"
        f"{real_adapter_indent}nqf_level=None, logo_bytes=None, brand_colors=None,\n"
        f"{real_adapter_indent}accreditation_info=None, job_id=None, **kwargs):"
    )
    content = content[:matches[0].start()] + new_adapter_block + content[matches[0].end():]

    old_return = "        brand_colors=brand_colors,\n        job_id=job_id,"
    if content.count(old_return) != 1:
        raise ValueError(f"  [adapter return] expected exactly 1 match, found {content.count(old_return)}")
    new_return = "        brand_colors=brand_colors,\n        accreditation_info=accreditation_info,\n        job_id=job_id,"
    content = content.replace(old_return, new_return)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("  OK — 3 replacements applied (header call NOT touched — multi-line, needs manual edit, see summary)")


def process_assessment_service():
    filename = "qcto_assessment_service.py"
    path = f"{SERVICES_DIR}/{filename}"
    print(f"Processing {filename} (special case) ...")

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    old_sig = (
        "def build_qcto_assessment_docx(title: str, syllabus_content: dict, module_type: str = \"KM\",\n"
        "                                organization_name: str = None, logo_bytes: bytes = None,\n"
        "                                brand_colors: dict = None, job_id: str = None) -> BytesIO:\n"
        "    brand_colors = brand_colors or {}"
    )
    if content.count(old_sig) != 1:
        raise ValueError(f"  [main signature] expected exactly 1 match, found {content.count(old_sig)}")
    new_sig = (
        "def build_qcto_assessment_docx(title: str, syllabus_content: dict, module_type: str = \"KM\",\n"
        "                                organization_name: str = None, logo_bytes: bytes = None,\n"
        "                                brand_colors: dict = None, accreditation_info: dict = None,\n"
        "                                job_id: str = None) -> BytesIO:\n"
        "    accreditation_info = dict(accreditation_info or {})\n"
        "    if syllabus_content.get(\"qualification_code\"):\n"
        "        accreditation_info.setdefault(\"qualification_code\", syllabus_content.get(\"qualification_code\"))\n"
        "    document_label = \"KM Formative Assessment\" if module_type == \"KM\" else \"PM Assessment (Scenario-Based)\"\n"
        "    brand_colors = brand_colors or {}"
    )
    content = content.replace(old_sig, new_sig)

    old_header = (
        '    _add_branded_header_footer(doc, logo_bytes=logo_bytes, qualification_name=qualification_title, '
        'organization_name=organization_name, primary_hex=primary_hex)'
    )
    if content.count(old_header) != 1:
        raise ValueError(f"  [header call] expected exactly 1 match, found {content.count(old_header)}")
    new_header = (
        '    _add_branded_header_footer(doc, logo_bytes=logo_bytes, qualification_name=qualification_title, '
        'organization_name=organization_name, primary_hex=primary_hex, accreditation_info=accreditation_info, document_label=document_label)'
    )
    content = content.replace(old_header, new_header)

    old_km_adapter = (
        "def build_qcto_km_assessment_docx_adapter(title, units, organization_name=None, seta=None,\n"
        "                                           nqf_level=None, logo_bytes=None, brand_colors=None,\n"
        "                                           job_id=None, **kwargs):\n"
        "    syllabus_content = {\"modules\": units} if isinstance(units, list) else (units or {\"modules\": []})\n"
        "    return build_qcto_assessment_docx(\n"
        "        title=title, syllabus_content=syllabus_content, module_type=\"KM\",\n"
        "        organization_name=organization_name, logo_bytes=logo_bytes,\n"
        "        brand_colors=brand_colors, job_id=job_id,\n"
        "    )"
    )
    if content.count(old_km_adapter) != 1:
        raise ValueError(f"  [KM adapter] expected exactly 1 match, found {content.count(old_km_adapter)}")
    new_km_adapter = (
        "def build_qcto_km_assessment_docx_adapter(title, units, organization_name=None, seta=None,\n"
        "                                           nqf_level=None, logo_bytes=None, brand_colors=None,\n"
        "                                           accreditation_info=None, job_id=None, **kwargs):\n"
        "    syllabus_content = {\"modules\": units} if isinstance(units, list) else (units or {\"modules\": []})\n"
        "    return build_qcto_assessment_docx(\n"
        "        title=title, syllabus_content=syllabus_content, module_type=\"KM\",\n"
        "        organization_name=organization_name, logo_bytes=logo_bytes,\n"
        "        brand_colors=brand_colors, accreditation_info=accreditation_info, job_id=job_id,\n"
        "    )"
    )
    content = content.replace(old_km_adapter, new_km_adapter)

    old_pm_adapter = (
        "def build_qcto_pm_assessment_docx_adapter(title, units, organization_name=None, seta=None,\n"
        "                                           nqf_level=None, logo_bytes=None, brand_colors=None,\n"
        "                                           job_id=None, **kwargs):\n"
        "    syllabus_content = {\"modules\": units} if isinstance(units, list) else (units or {\"modules\": []})\n"
        "    return build_qcto_assessment_docx(\n"
        "        title=title, syllabus_content=syllabus_content, module_type=\"PM\",\n"
        "        organization_name=organization_name, logo_bytes=logo_bytes,\n"
        "        brand_colors=brand_colors, job_id=job_id,\n"
        "    )"
    )
    if content.count(old_pm_adapter) != 1:
        raise ValueError(f"  [PM adapter] expected exactly 1 match, found {content.count(old_pm_adapter)}")
    new_pm_adapter = (
        "def build_qcto_pm_assessment_docx_adapter(title, units, organization_name=None, seta=None,\n"
        "                                           nqf_level=None, logo_bytes=None, brand_colors=None,\n"
        "                                           accreditation_info=None, job_id=None, **kwargs):\n"
        "    syllabus_content = {\"modules\": units} if isinstance(units, list) else (units or {\"modules\": []})\n"
        "    return build_qcto_assessment_docx(\n"
        "        title=title, syllabus_content=syllabus_content, module_type=\"PM\",\n"
        "        organization_name=organization_name, logo_bytes=logo_bytes,\n"
        "        brand_colors=brand_colors, accreditation_info=accreditation_info, job_id=job_id,\n"
        "    )"
    )
    content = content.replace(old_pm_adapter, new_pm_adapter)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("  OK — 4 replacements applied (fully complete, no manual follow-up needed)")


def main():
    results = {}

    for filename, stem, label in STANDARD_FILES:
        try:
            process_standard_file(filename, stem, label)
            results[filename] = "OK"
        except Exception as exc:
            print(f"  SKIPPED: {exc}")
            results[filename] = f"SKIPPED: {exc}"

    try:
        process_km_learner_guide()
        results["qcto_knowledge_module_service.py"] = "PARTIAL (header call needs manual edit)"
    except Exception as exc:
        print(f"  SKIPPED: {exc}")
        results["qcto_knowledge_module_service.py"] = f"SKIPPED: {exc}"

    try:
        process_assessment_service()
        results["qcto_assessment_service.py"] = "OK"
    except Exception as exc:
        print(f"  SKIPPED: {exc}")
        results["qcto_assessment_service.py"] = f"SKIPPED: {exc}"

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for filename, status in results.items():
        print(f"  {filename}: {status}")

    print("\nCompiling all touched files to check for syntax errors...")
    all_files = [f for f, _, _ in STANDARD_FILES] + ["qcto_knowledge_module_service.py", "qcto_assessment_service.py"]
    failed_compile = []
    for filename in all_files:
        path = f"{SERVICES_DIR}/{filename}"
        result = subprocess.run([sys.executable, "-m", "py_compile", path], capture_output=True, text=True)
        if result.returncode != 0:
            failed_compile.append((filename, result.stderr))

    if failed_compile:
        print("\nCOMPILE ERRORS FOUND:")
        for filename, err in failed_compile:
            print(f"  {filename}:\n{err}")
        sys.exit(1)
    else:
        print("All files compiled successfully.")


if __name__ == "__main__":
    main()
