"""Diagram generation (matplotlib, no AI cost) and stock photo fetching (Unsplash, free tier)."""
import io
import requests
import matplotlib
matplotlib.use("Agg")  # headless backend, no display needed
import matplotlib.pyplot as plt
from flask import current_app


def generate_flow_diagram(steps: list, primary_hex: str = "1A5276", accent_hex: str = "F39C12") -> bytes:
    """Renders a simple top-to-bottom flow diagram from a list of step labels.
    Returns PNG bytes. No AI call — pure matplotlib rendering."""
    primary = f"#{primary_hex.lstrip('#')}"
    accent = f"#{accent_hex.lstrip('#')}"

    fig_height = max(2, len(steps) * 1.2)
    fig, ax = plt.subplots(figsize=(6, fig_height))
    ax.axis("off")

    box_height = 0.7
    gap = 0.5
    y = len(steps) * (box_height + gap)

    for i, step in enumerate(steps):
        y_pos = y - i * (box_height + gap)
        rect = plt.Rectangle((0.1, y_pos), 0.8, box_height, facecolor=primary, edgecolor=primary, alpha=0.9)
        ax.add_patch(rect)
        ax.text(0.5, y_pos + box_height / 2, step, ha="center", va="center",
                 color="white", fontsize=10, fontweight="bold", wrap=True)

        if i < len(steps) - 1:
            arrow_y_start = y_pos
            arrow_y_end = y_pos - gap
            ax.annotate("", xy=(0.5, arrow_y_end), xytext=(0.5, arrow_y_start),
                        arrowprops=dict(arrowstyle="-|>", color=accent, lw=2))

    ax.set_xlim(0, 1)
    ax.set_ylim(0, y + box_height)

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