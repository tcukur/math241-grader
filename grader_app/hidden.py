"""Hidden text: text in a PDF that a person reading the page cannot see but that a text extractor, and so the
AI, would read. For example white text on a white page, microscopic text, text made invisible with the PDF's
'invisible' setting. It can be used to slip instructions to an AI grader.

Hidden text is found here, kept away from the AI, and reported to the grader, who decides what it means.
Text that only looks unusual but is visible stays: light text on a dark box (code blocks in chat exports) and
the invisible text layer that scanners and OCR place over a scanned image."""
from __future__ import annotations

import pymupdf

MIN_SIZE = 2.0          # points; real footnotes and subscripts are well above this
MIN_CHARS = 3           # ignore stray single characters


def _luminance(rgb) -> float:
    r, g, b = (list(rgb) + [0, 0, 0])[:3]
    return 0.299 * r + 0.587 * g + 0.114 * b


def _backgrounds(page) -> list[pymupdf.Rect]:
    """Areas where text is drawn on top of something: dark filled shapes and images."""
    out = []
    try:
        for d in page.get_drawings():
            fill = d.get("fill")
            if fill is not None and _luminance(fill) < 0.75 and d.get("rect") is not None:
                out.append(pymupdf.Rect(d["rect"]))
    except Exception:  # noqa: BLE001
        pass
    try:
        for im in page.get_image_info():
            out.append(pymupdf.Rect(im["bbox"]))
    except Exception:  # noqa: BLE001
        pass
    return out


def _over(rect: pymupdf.Rect, areas: list[pymupdf.Rect]) -> bool:
    c = pymupdf.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
    return any(c in a for a in areas)


def find_hidden(page) -> list[dict]:
    """Hidden text runs on one page: [{'rect', 'text', 'reason'}]."""
    try:
        traces = page.get_texttrace()
    except Exception:  # noqa: BLE001
        return []
    if not traces:
        return []
    bg = None
    page_rect = page.rect
    out = []
    for t in traces:
        text = "".join(chr(c[0]) for c in t.get("chars", []))
        if len(text.strip()) < MIN_CHARS:
            continue
        rect = pymupdf.Rect(t["bbox"])
        reason = ""
        if not rect.intersects(page_rect):
            continue      # outside the page: text extraction never reads it (and long code lines often run off)
        if t.get("type") == 3 or (t.get("opacity") is not None and t.get("opacity") < 0.05):
            if bg is None:
                bg = _backgrounds(page)
            if not _over(rect, bg):          # over a scanned image it is an OCR layer, which is fine
                reason = "set to be invisible"
        elif t.get("size", 10) < MIN_SIZE:
            reason = f"microscopic font ({t.get('size', 0):.1f} pt)"
        elif _luminance(t.get("color", (0, 0, 0))) > 0.94:
            if bg is None:
                bg = _backgrounds(page)
            if not _over(rect, bg):          # light text on a dark box is visible
                reason = "white text on a white background"
        if reason:
            out.append({"rect": rect, "text": " ".join(text.split()), "reason": reason})
    return out


def strip_hidden(doc) -> list[dict]:
    """Remove hidden text from an open document, in memory only (the file on disk is never changed), so that
    nothing read from it afterwards contains it. Returns [{'page', 'text', 'reason'}] for the grader."""
    found = []
    for pno, page in enumerate(doc):
        runs = find_hidden(page)
        if not runs:
            continue
        for r in runs:
            found.append({"page": pno + 1, "text": r["text"][:300], "reason": r["reason"]})
            rect = r["rect"] & page.rect
            if rect.is_empty:
                continue
            # shrink a little so neighbouring visible lines are never touched
            inset = min(rect.height * 0.25, 2)
            page.add_redact_annot(pymupdf.Rect(rect.x0, rect.y0 + inset, rect.x1, rect.y1 - inset))
        try:
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                                  graphics=getattr(pymupdf, "PDF_REDACT_LINE_ART_NONE", 0))
        except Exception:  # noqa: BLE001
            pass
    return found
