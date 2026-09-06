"""Diagram generation (matplotlib, no AI cost) and stock photo fetching (Unsplash, free tier)."""
import io
import requests
import matplotlib
matplotlib.use("Agg")  # headless backend, no display needed
import matplotlib.pyplot as plt
from flask import current_app


def generate_flow_diagram(steps: list, primary_hex: str = "1A5276", accent_hex: str = "F39C12") -> bytes:
    """Renders a flow diagram from a list of step labels, with boxes sized to fit their
    text and varied shapes (rounded rect / diamond / oval) to distinguish step types.
    No AI call — pure matplotlib rendering."""
    primary = f"#{primary_hex.lstrip('#')}"
    accent = f"#{accent_hex.lstrip('#')}"

    def _wrap_text(text, max_chars_per_line=22):
        """Wraps long labels onto multiple lines instead of letting them overflow the box."""
        words = text.split()
        lines, current = [], ""
        for word in words:
            if len(current) + len(word) + 1 <= max_chars_per_line:
                current = f"{current} {word}".strip()
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return "\n".join(lines)

    def _shape_for_step(index, total, label):
        """Decides shape based on position/content: oval for start/end, diamond for
        decision-sounding steps (containing '?' or starting with common decision words),
        rounded rectangle for everything else."""
        label_lower = label.lower()
        if index == 0 or index == total - 1:
            return "oval"
        if "?" in label or any(label_lower.startswith(w) for w in ("if ", "check ", "decide", "is ")):
            return "diamond"
        return "rect"

    wrapped_steps = [_wrap_text(s) for s in steps]
    line_counts = [w.count("\n") + 1 for w in wrapped_steps]

    box_height_base = 0.55
    box_heights = [box_height_base + (lc - 1) * 0.22 for lc in line_counts]  # grow box with line count
    gap = 0.5

    fig_height = sum(box_heights) + gap * (len(steps) - 1) + 1

    # Cap the figure height so a diagram with many steps never ends up taller than a
    # single page once inserted at its fixed 4.5in width — without this, a long flowchart
    # could produce an image that gets visually cut off at the page boundary. If the
    # natural size would exceed the cap, shrink box heights and the gap between them
    # proportionally so everything still fits, rather than letting it overflow.
    MAX_FIG_HEIGHT = 8.96  # keeps on-page height at ~6.2in at the 4.5in insertion width
    scale = 1.0
    if fig_height > MAX_FIG_HEIGHT:
        scale = (MAX_FIG_HEIGHT - 1) / (fig_height - 1)
        box_heights = [h * scale for h in box_heights]
        gap = gap * scale
        fig_height = MAX_FIG_HEIGHT
    fig, ax = plt.subplots(figsize=(6.5, fig_height))
    ax.axis("off")

    y = fig_height - 0.5
    box_width = 0.75

    for i, (label, height) in enumerate(zip(wrapped_steps, box_heights)):
        y_pos = y - height
        shape_type = _shape_for_step(i, len(steps), steps[i])
        cx, cy = 0.5, y_pos + height / 2

        if shape_type == "oval":
            patch = plt.matplotlib.patches.Ellipse((cx, cy), box_width, height, facecolor=primary, edgecolor=primary, alpha=0.9)
        elif shape_type == "diamond":
            # slightly taller diamond so wrapped text fits within the point-to-point width
            half_w, half_h = box_width / 2, height / 2 + 0.15
            patch = plt.matplotlib.patches.Polygon(
                [(cx, cy + half_h), (cx + half_w, cy), (cx, cy - half_h), (cx - half_w, cy)],
                closed=True, facecolor=accent, edgecolor=accent, alpha=0.9,
            )
        else:
            patch = plt.matplotlib.patches.FancyBboxPatch(
                (cx - box_width / 2, y_pos), box_width, height,
                boxstyle="round,pad=0.02,rounding_size=0.08",
                facecolor=primary, edgecolor=primary, alpha=0.9,
            )

        ax.add_patch(patch)
        ax.text(cx, cy, label, ha="center", va="center", color="white", fontsize=max(6, 9 * scale), fontweight="bold")

        if i < len(steps) - 1:
            next_height = box_heights[i + 1]
            arrow_y_start = y_pos
            arrow_y_end = y_pos - gap
            ax.annotate("", xy=(cx, arrow_y_end), xytext=(cx, arrow_y_start),
                        arrowprops=dict(arrowstyle="-|>", color=accent, lw=2))

        y = y_pos - gap

    ax.set_xlim(0, 1)
    ax.set_ylim(0, fig_height)

    buffer = io.BytesIO()
    plt.savefig(buffer, format="png", dpi=150, bbox_inches="tight", transparent=True)
    plt.close(fig)
    buffer.seek(0)
    return buffer.read()

def fetch_stock_photo(search_term: str) -> bytes | None:
    """Fetches one relevant photo from Unsplash for the given search term.
    Returns JPEG bytes, or None if no key configured or nothing found — callers
    must handle None gracefully rather than failing the whole document."""
    access_key = current_app.config.get("UNSPLASH_ACCESS_KEY")
    if not access_key:
        return None

    try:
        search_resp = requests.get(
            "https://api.unsplash.com/search/photos",
            params={"query": search_term, "per_page": 1, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {access_key}"},
            timeout=10,
        )
        search_resp.raise_for_status()
        results = search_resp.json().get("results", [])
        if not results:
            return None

        image_url = results[0]["urls"]["regular"]
        image_resp = requests.get(image_url, timeout=10)
        image_resp.raise_for_status()
        return image_resp.content
    except Exception:
        return None  # never let an image fetch failure break document generation