"""Renders well-known named models and frameworks (OSI model, Maslow's hierarchy, PDCA,
SWOT, Porter's Five Forces, ADDIE, ...) as clean diagrams. The AI only supplies structured
data (a diagram kind plus labelled items); all drawing is done here with matplotlib, so there
is no extra AI cost and no new dependency."""
import io
import math
import matplotlib
matplotlib.use("Agg")  # headless backend, no display needed
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle

SUPPORTED_KINDS = ("layers", "pyramid", "cycle", "matrix", "hub", "chevrons")


# ---------- helpers ----------

def _hex(value: str, default: str) -> str:
    value = (value or default).lstrip("#")
    if len(value) != 6:
        value = default
    return f"#{value}"


def _blend(color_hex: str, factor: float) -> str:
    """Mixes a colour with white. factor 0 = original colour, 1 = white."""
    c = color_hex.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"#{r:02X}{g:02X}{b:02X}"


def _text_color(bg_hex: str) -> str:
    c = bg_hex.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    return "#FFFFFF" if (0.299 * r + 0.587 * g + 0.114 * b) < 150 else "#1B2631"


def _wrap(text: str, width: int) -> str:
    """Wraps text onto lines of at most `width` chars, splitting over-long single words."""
    words = str(text).split()
    lines, current = [], ""
    for word in words:
        while len(word) > width:
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:width - 1] + "-")
            word = word[width - 1:]
        if len(current) + len(word) + (1 if current else 0) <= width:
            current = f"{current} {word}".strip()
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return "\n".join(lines)


def _normalise(items, limit=9) -> list:
    """Accepts a list of strings or {"label":..., "detail":...} dicts, returns clean dicts."""
    out = []
    for item in items or []:
        if isinstance(item, dict):
            label = str(item.get("label") or "").strip()
            detail = str(item.get("detail") or "").strip()
        else:
            label, detail = str(item or "").strip(), ""
        if label:
            out.append({"label": label, "detail": detail})
    return out[:limit]


def _finish(fig, title: str, ax, top_y: float) -> bytes:
    if title:
        ax.text(ax.get_xlim()[0] + (ax.get_xlim()[1] - ax.get_xlim()[0]) / 2, top_y, title,
                ha="center", va="bottom", fontsize=11, fontweight="bold", color="#1B2631")
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150, bbox_inches="tight", transparent=False, facecolor="white")
    plt.close(fig)
    buffer.seek(0)
    return buffer.read()


# ---------- renderers ----------

def _layers(items, title, primary, accent) -> bytes:
    n = len(items)
    has_detail = any(i["detail"] for i in items)
    band_h = 0.78 if has_detail else 0.6
    gap = 0.12
    height = n * band_h + (n - 1) * gap
    fig, ax = plt.subplots(figsize=(6.5, height * 0.62 + (0.6 if title else 0.2)))
    ax.axis("off")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, height)
    for idx, item in enumerate(items):
        y = height - (idx + 1) * band_h - idx * gap
        shade = _blend(primary, 0.5 * idx / max(1, n - 1))
        ax.add_patch(FancyBboxPatch((0.1, y), 9.8, band_h, boxstyle="round,pad=0.0,rounding_size=0.12",
                                    facecolor=shade, edgecolor="white", linewidth=1))
        fg = _text_color(shade)
        if has_detail:
            ax.text(0.45, y + band_h * 0.66, item["label"], ha="left", va="center", fontsize=9.5,
                    fontweight="bold", color=fg)
            ax.text(0.45, y + band_h * 0.28, _wrap(item["detail"], 95)[:200].split("\n")[0], ha="left",
                    va="center", fontsize=7.5, color=fg)
        else:
            ax.text(5, y + band_h / 2, item["label"], ha="center", va="center", fontsize=10,
                    fontweight="bold", color=fg)
    return _finish(fig, title, ax, height + 0.1)


def _pyramid(items, title, primary, accent) -> bytes:
    n = len(items)
    has_detail = any(i["detail"] for i in items)
    level_h = 0.95
    height = n * level_h
    base_w, top_w = (6.4, 3.4) if has_detail else (9.4, 4.4)
    cx = 3.5 if has_detail else 5.0
    fig, ax = plt.subplots(figsize=(6.5, height * 0.7 + (0.6 if title else 0.2)))
    ax.axis("off")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, height)

    def width_at(dist_from_top):
        return top_w + (base_w - top_w) * dist_from_top / height

    for idx, item in enumerate(items):
        y_top = height - idx * level_h
        y_bot = y_top - level_h
        w_top, w_bot = width_at(height - y_top), width_at(height - y_bot)
        shade = _blend(primary, 0.55 * (n - 1 - idx) / max(1, n - 1))
        ax.add_patch(Polygon([(cx - w_top / 2, y_top - 0.03), (cx + w_top / 2, y_top - 0.03),
                              (cx + w_bot / 2, y_bot + 0.03), (cx - w_bot / 2, y_bot + 0.03)],
                             closed=True, facecolor=shade, edgecolor="white", linewidth=1.2))
        mid_w = (w_top + w_bot) / 2
        longest = max(len(word) for word in item["label"].split())
        label_font = max(6.5, min(9.0, mid_w * 46.8 * 0.9 / (0.62 * max(longest, 1))))
        ax.text(cx, (y_top + y_bot) / 2, _wrap(item["label"], max(int(mid_w * 4.8), longest)), ha="center",
                va="center", fontsize=label_font, fontweight="bold", color=_text_color(shade))
        if has_detail and item["detail"]:
            ax.text(cx + base_w / 2 + 0.3, (y_top + y_bot) / 2, _wrap(item["detail"], 30), ha="left",
                    va="center", fontsize=7.5, color="#1B2631")
    return _finish(fig, title, ax, height + 0.1)


def _cycle(items, title, primary, accent) -> bytes:
    items = items[:8]
    n = len(items)
    box_w, box_h = 2.5, 1.25
    radius = max(2.9, 0.5 * (box_w + 0.4) / math.sin(math.pi / n))
    lim = radius + box_w / 2 + 0.4
    fig, ax = plt.subplots(figsize=(6.5, 6.5))
    ax.axis("off")
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim + (0.5 if title else 0))
    ax.set_aspect("equal")
    centres = []
    for idx in range(n):
        angle = math.pi / 2 - 2 * math.pi * idx / n  # start at the top, go clockwise
        centres.append((radius * math.cos(angle), radius * math.sin(angle)))
    boxes = []
    for idx, (x, y) in enumerate(centres):
        shade = _blend(primary, 0.35 * idx / max(1, n - 1))
        box = FancyBboxPatch((x - box_w / 2, y - box_h / 2), box_w, box_h,
                             boxstyle="round,pad=0.02,rounding_size=0.15",
                             facecolor=shade, edgecolor="white", linewidth=1.2, zorder=3)
        ax.add_patch(box)
        boxes.append(box)
        fg = _text_color(shade)
        if items[idx]["detail"]:
            ax.text(x, y + 0.3, _wrap(items[idx]["label"], 22), ha="center", va="center", fontsize=8.5,
                    fontweight="bold", color=fg, zorder=4)
            ax.text(x, y - 0.17, "\n".join(_wrap(items[idx]["detail"], 24).split("\n")[:2]), ha="center",
                    va="center", fontsize=6.6, color=fg, zorder=4)
        else:
            ax.text(x, y, _wrap(items[idx]["label"], max(15, max(len(w_) for w_ in items[idx]["label"].split()))), ha="center",
                    va="center", fontsize=9 if max(len(w_) for w_ in items[idx]["label"].split()) <= 15 else 7.6,
                    fontweight="bold", color=fg, zorder=4)
    for idx in range(n):
        ax.annotate("", xy=centres[(idx + 1) % n], xytext=centres[idx],
                    arrowprops=dict(arrowstyle="-|>", color=accent, lw=2.2, shrinkA=2, shrinkB=2,
                                    patchA=boxes[idx], patchB=boxes[(idx + 1) % n],
                                    connectionstyle="arc3,rad=-0.25"), zorder=2)
    return _finish(fig, title, ax, lim + 0.05)


def _matrix(items, title, primary, accent, axes=None) -> bytes:
    items = items[:4]
    while len(items) < 4:
        items.append({"label": "", "detail": ""})
    axes = axes or {}
    cols = (axes.get("columns") or [])[:2]
    rows = (axes.get("rows") or [])[:2]
    cell_w, cell_h = 4.6, 2.5
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.axis("off")
    ax.set_xlim(-0.8, cell_w * 2 + 0.1)
    ax.set_ylim(-0.1, cell_h * 2 + 0.6)
    positions = [(0, cell_h), (cell_w, cell_h), (0, 0), (cell_w, 0)]
    shades = [primary, _blend(primary, 0.25), _blend(primary, 0.25), primary]
    for (x, y), item, shade in zip(positions, items, shades):
        ax.add_patch(Rectangle((x + 0.05, y + 0.05), cell_w - 0.1, cell_h - 0.1, facecolor=_blend(shade, 0.82),
                               edgecolor=shade, linewidth=1.6))
        ax.add_patch(Rectangle((x + 0.05, y + cell_h - 0.62), cell_w - 0.1, 0.57, facecolor=shade, edgecolor=shade))
        ax.text(x + cell_w / 2, y + cell_h - 0.335, item["label"], ha="center", va="center", fontsize=9.5,
                fontweight="bold", color=_text_color(shade))
        if item["detail"]:
            ax.text(x + cell_w / 2, y + (cell_h - 0.62) / 2, _wrap(item["detail"], 38), ha="center", va="center",
                    fontsize=7.6, color="#1B2631")
    for idx, label in enumerate(cols):
        ax.text(positions[idx][0] + cell_w / 2, cell_h * 2 + 0.2, label, ha="center", va="center", fontsize=8.5,
                fontweight="bold", color=accent)
    for idx, label in enumerate(rows):
        ax.text(-0.35, positions[idx * 2][1] + cell_h / 2, label, ha="center", va="center", rotation=90,
                fontsize=8.5, fontweight="bold", color=accent)
    return _finish(fig, title, ax, cell_h * 2 + 0.45)


def _hub(items, title, primary, accent) -> bytes:
    centre, spokes = items[0], items[1:9]
    n = max(1, len(spokes))
    rx, ry = 4.0, 2.9
    fig, ax = plt.subplots(figsize=(6.5, 5.6))
    ax.axis("off")
    ax.set_xlim(-rx - 1.8, rx + 1.8)
    ax.set_ylim(-ry - 1.0, ry + 1.0 + (0.5 if title else 0))
    pts = []
    for idx in range(len(spokes)):
        angle = math.pi / 2 - 2 * math.pi * idx / n
        pts.append((rx * math.cos(angle), ry * math.sin(angle)))
    centre_box = FancyBboxPatch((-1.6, -0.8), 3.2, 1.6, boxstyle="round,pad=0.02,rounding_size=0.2",
                                facecolor=primary, edgecolor="white", linewidth=1.5, zorder=3)
    ax.add_patch(centre_box)
    ax.text(0, 0.25 if centre["detail"] else 0, _wrap(centre["label"], 18), ha="center", va="center", fontsize=9.5,
            fontweight="bold", color=_text_color(primary), zorder=4)
    if centre["detail"]:
        ax.text(0, -0.28, "\n".join(_wrap(centre["detail"], 32).split("\n")[:2]), ha="center", va="center",
                fontsize=6.6, color=_text_color(primary), zorder=4)
    for (x, y), item in zip(pts, spokes):
        shade = _blend(primary, 0.4)
        box = FancyBboxPatch((x - 1.55, y - 0.7), 3.1, 1.4, boxstyle="round,pad=0.02,rounding_size=0.15",
                             facecolor=shade, edgecolor="white", linewidth=1.2, zorder=3)
        ax.add_patch(box)
        fg = _text_color(shade)
        if item["detail"]:
            ax.text(x, y + 0.28, _wrap(item["label"], 16), ha="center", va="center", fontsize=8.5,
                    fontweight="bold", color=fg, zorder=4)
            ax.text(x, y - 0.3, "\n".join(_wrap(item["detail"], 30).split("\n")[:2]), ha="center", va="center",
                    fontsize=6.4, color=fg, zorder=4)
        else:
            ax.text(x, y, _wrap(item["label"], 16), ha="center", va="center", fontsize=8.8, fontweight="bold",
                    color=fg, zorder=4)
        ax.annotate("", xy=(0, 0), xytext=(x, y),
                    arrowprops=dict(arrowstyle="-|>", color=accent, lw=2.2, shrinkA=2, shrinkB=2,
                                    patchA=box, patchB=centre_box), zorder=2)
    return _finish(fig, title, ax, ry + 1.05)


def _chevrons(items, title, primary, accent) -> bytes:
    """Numbered chevrons left to right, with each stage's name and detail written beneath
    so long stage names never get squeezed or hyphenated inside the arrow."""
    items = items[:7]
    n = len(items)
    has_detail = any(i["detail"] for i in items)
    w = 10.0 / n
    h = 1.0
    fig, ax = plt.subplots(figsize=(6.5, 2.1 + (0.9 if has_detail else 0.2)))
    ax.axis("off")
    ax.set_xlim(0, 10.3)
    ax.set_ylim(-(2.6 if has_detail else 1.1), h + 0.2)
    tip = min(0.4, w * 0.25)
    for idx, item in enumerate(items):
        x0 = idx * w
        shade = _blend(primary, 0.45 * idx / max(1, n - 1))
        pts = [(x0, 0), (x0 + w - tip, 0), (x0 + w, h / 2), (x0 + w - tip, h), (x0, h)]
        if idx > 0:
            pts.append((x0 + tip, h / 2))
        ax.add_patch(Polygon(pts, closed=True, facecolor=shade, edgecolor="white", linewidth=1.5))
        ax.text(x0 + w / 2, h / 2, str(idx + 1), ha="center", va="center", fontsize=15, fontweight="bold",
                color=_text_color(shade))
        ax.text(x0 + w / 2, -0.15, _wrap(item["label"], max(int(w * 6.2), max(len(x) for x in item["label"].split()))), ha="center", va="top", fontsize=7.8,
                fontweight="bold", color="#1B2631")
        if has_detail and item["detail"]:
            label_lines = _wrap(item["label"], max(int(w * 6.2), max(len(x) for x in item["label"].split()))).count("\n") + 1
            ax.text(x0 + w / 2, -0.15 - 0.34 * label_lines - 0.08, _wrap(item["detail"], max(12, int(w * 7.5))),
                    ha="center", va="top", fontsize=7, color="#3B4A57")
    return _finish(fig, title, ax, h + 0.15)


_RENDERERS = {"layers": _layers, "pyramid": _pyramid, "cycle": _cycle, "hub": _hub, "chevrons": _chevrons}


def generate_model_diagram(kind: str, items: list, title: str = "", primary_hex: str = "1A5276",
                           accent_hex: str = "F39C12", axes: dict | None = None) -> bytes | None:
    """Returns PNG bytes for a named model/framework diagram, or None when the data isn't usable
    (callers then simply skip the block, so a bad diagram never breaks document generation)."""
    kind = (kind or "").strip().lower()
    if kind not in SUPPORTED_KINDS:
        return None
    clean = _normalise(items)
    minimum = {"layers": 3, "pyramid": 3, "cycle": 3, "matrix": 4, "hub": 3, "chevrons": 3}[kind]
    if len(clean) < minimum:
        return None
    primary, accent = _hex(primary_hex, "1A5276"), _hex(accent_hex, "F39C12")
    title = (title or "").strip()
    if kind == "matrix":
        return _matrix(clean, title, primary, accent, axes)
    return _RENDERERS[kind](clean, title, primary, accent)


# ---------- PowerPoint helpers ----------

def _png_size(png_bytes: bytes):
    import struct
    return struct.unpack(">II", png_bytes[16:24])


def slide_model_diagram_png(spec, primary_hex="1A5276", accent_hex="F39C12", deck=None):
    """Builds a slide-sized diagram PNG from a slide's model_diagram object, or None if the slide
    has none / it is unusable. Small detail captions are dropped (too small to read when projected),
    except in matrix diagrams where the quadrant text is the content."""
    if not isinstance(spec, dict):
        return None
    kind = str(spec.get("kind") or "").strip().lower()
    if deck is not None:
        # a model may appear only once per deck: repeats fall back to the slide photo
        seen = getattr(deck, "_seen_model_diagrams", None)
        if seen is None:
            seen = set()
            try:
                deck._seen_model_diagrams = seen
            except Exception:
                seen = None
        if seen is not None:
            first = ""
            for it in spec.get("items") or []:
                first = str(it.get("label") if isinstance(it, dict) else it or "")
                break
            key = (str(spec.get("title") or "") or first).strip().lower()
            if key and key in seen:
                return None
            if key:
                seen.add(key)
    items = []
    for item in spec.get("items") or []:
        if isinstance(item, dict):
            items.append({"label": item.get("label"), "detail": item.get("detail") if kind == "matrix" else ""})
        else:
            items.append({"label": item, "detail": ""})
    try:
        return generate_model_diagram(kind, items, spec.get("title", ""), primary_hex=str(primary_hex),
                                      accent_hex=str(accent_hex), axes=spec.get("axes"))
    except Exception as exc:
        print(f"[DEBUG] slide model_diagram failed: {exc}")
        return None


def add_fitted_picture(slide, png_bytes, left, top, box_w, box_h):
    """Places a PNG inside the given box, centred, keeping its proportions (never stretched)."""
    from io import BytesIO
    px_w, px_h = _png_size(png_bytes)
    scale = min(box_w / px_w, box_h / px_h)
    w, h = int(px_w * scale), int(px_h * scale)
    return slide.shapes.add_picture(BytesIO(png_bytes), int(left + (box_w - w) / 2), int(top + (box_h - h) / 2),
                                    width=w, height=h)


def add_cover_picture(slide, image_bytes, left, top, box_w, box_h):
    """Fills the box with the photo WITHOUT stretching it: the photo is scaled to cover the box and
    the overflow is cropped evenly from the edges. Falls back to a plain placement if the photo's
    size cannot be read."""
    from io import BytesIO
    try:
        from PIL import Image
        px_w, px_h = Image.open(BytesIO(image_bytes)).size
    except Exception:
        return slide.shapes.add_picture(BytesIO(image_bytes), left, top, width=box_w, height=box_h)
    pic = slide.shapes.add_picture(BytesIO(image_bytes), left, top, width=box_w, height=box_h)
    box_ratio, img_ratio = box_w / box_h, px_w / px_h
    if img_ratio > box_ratio:
        crop = (1 - box_ratio / img_ratio) / 2
        pic.crop_left = crop
        pic.crop_right = crop
    elif img_ratio < box_ratio:
        crop = (1 - img_ratio / box_ratio) / 2
        pic.crop_top = crop
        pic.crop_bottom = crop
    return pic
