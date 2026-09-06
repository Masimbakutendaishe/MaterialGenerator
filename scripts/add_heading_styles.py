"""Adds Word Heading 1 style to every section-heading paragraph in a file, detected by
the paragraph variable immediately preceding each _add_bottom_border(var, primary_hex...)
call — this pattern is consistent across the codebase's section-heading sites. Run from
project root: python scripts/add_heading_styles.py <relative_path_to_file>

Safe by design: only inserts a new line, never modifies existing lines. Skips any site
where the style line already exists (so it's safe to re-run). Reports every site found
and whether it was newly styled or already had the style, so nothing is silently missed.
"""
import re
import sys


def process_file(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    pattern = re.compile(r'^(\s*)_add_bottom_border\((\w+),\s*primary_hex')
    new_lines = []
    sites_found = 0
    sites_styled = 0
    sites_already_done = 0

    for i, line in enumerate(lines):
        match = pattern.match(line)
        if match:
            sites_found += 1
            indent, var_name = match.group(1), match.group(2)
            style_line = f'{indent}{var_name}.style = doc.styles["Heading 1"]\n'
            # Check if the immediately preceding non-blank line already has this exact style line
            prev_line = new_lines[-1] if new_lines else ""
            if prev_line.strip() == style_line.strip():
                sites_already_done += 1
            else:
                new_lines.append(style_line)
                sites_styled += 1
        new_lines.append(line)

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print(f"{path}:")
    print(f"  Section heading sites found: {sites_found}")
    print(f"  Newly styled: {sites_styled}")
    print(f"  Already had style (skipped): {sites_already_done}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/add_heading_styles.py <path_to_file>")
        sys.exit(1)
    process_file(sys.argv[1])
