"""Make feedback PDFs light enough to upload for a whole class.

The feedback PDF repeats the student's submission only so the comments can point at places in it, and the
original is already in Moodle. So large pictures in it (scans, screenshots, photos) are scaled down to a
resolution that still reads well on screen and saved as JPEG. Text, formulas typeset as text, the numbered marks
and the cover are not touched, so they stay sharp. A picture is only replaced when that makes it smaller, and a
picture with transparency is left alone."""
from __future__ import annotations

import pymupdf

TARGET_DPI = 100          # on-screen reading; text inside a screenshot stays legible
QUALITY = 60              # JPEG quality
MIN_BYTES = 8_000          # tiny pictures are not worth touching


def _shown_size_pt(pages, xref: int) -> float:
    """The longer side of the largest box the picture is shown in, in points."""
    longest = 0.0
    for page in pages:
        try:
            for r in page.get_image_rects(xref):
                longest = max(longest, abs(r.width), abs(r.height))
        except Exception:  # noqa: BLE001
            continue
    return longest


def lighten(doc, dpi: int | None = None, quality: int | None = None) -> int:
    """Scale down and recompress large pictures in `doc`, in place. Returns the number of bytes saved."""
    dpi, quality = dpi or TARGET_DPI, quality or QUALITY
    saved = 0
    done = set()
    uses: dict[int, list] = {}
    for page in doc:
        for im in page.get_images(full=True):
            uses.setdefault(im[0], []).append(page)
    for xref, pages in uses.items():
        if xref in done:
            continue
        done.add(xref)
        try:
            raw = doc.xref_stream_raw(xref) or b""
            if len(raw) < MIN_BYTES:
                continue
            if doc.xref_get_key(xref, "SMask")[0] != "null" or doc.xref_get_key(xref, "Mask")[0] != "null":
                continue                                  # transparency: keep as it is
            pix = pymupdf.Pixmap(doc, xref)
            if pix.alpha:
                continue
            if pix.colorspace is None or pix.colorspace.n not in (1, 3):
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)  # CMYK and the like
            shown = _shown_size_pt(pages, xref)
            long_px = max(pix.width, pix.height)
            want = int(shown / 72 * dpi) if shown else long_px
            if want < long_px * 0.9:
                f = want / long_px
                pix = pymupdf.Pixmap(pix, max(1, round(pix.width * f)), max(1, round(pix.height * f)), None)
            data = pix.tobytes("jpg", jpg_quality=quality)
            if len(data) >= len(raw) * 0.9:
                continue                                  # not worth it, keep the original
            pages[0].replace_image(xref, stream=data)
            saved += len(raw) - len(data)
        except Exception:  # noqa: BLE001
            continue                                      # one odd picture never stops the feedback
    return saved


HEAVY_PAGE_BYTES = 150_000    # a page whose own drawing takes more than this is turned into one picture
FLAT_DPI, FLAT_QUALITY = 130, 70   # such a page is rendered sharper than pictures, since all its text is in it


def _page_weight(doc, page) -> int:
    """Bytes of the page's own drawing: its content streams and the form objects it draws."""
    n = 0
    try:
        for x in page.get_contents():
            n += len(doc.xref_stream_raw(x) or b"")
        for f in page.get_xobjects():
            n += len(doc.xref_stream_raw(f[0]) or b"")
    except Exception:  # noqa: BLE001
        pass
    return n


def flatten_heavy_pages(doc, first: int = 0, dpi: int | None = None, quality: int | None = None) -> int:
    """Pages from `first` on whose drawing is very large (thousands of tiny strokes from a handwriting app,
    plots exported as vectors) are replaced by one JPEG of the page as it looks, marks included. Only when the
    picture is clearly smaller, and never for rotated pages. Returns the number of pages replaced."""
    dpi, quality = dpi or FLAT_DPI, quality or FLAT_QUALITY
    done = 0
    for i in range(first, len(doc)):
        page = doc[i]
        try:
            if page.rotation:
                continue
            weight = _page_weight(doc, page)
            if weight < HEAVY_PAGE_BYTES:
                continue
            jpg = page.get_pixmap(dpi=dpi).tobytes("jpg", jpg_quality=quality)
            if len(jpg) > weight * 0.6:
                continue
            for x in page.get_contents():
                doc.update_stream(x, b" ")
            doc.xref_set_key(page.xref, "Resources", "<<>>")
            for a in list(page.annots() or []):
                page.delete_annot(a)          # comments and highlights are in the picture already
            page.insert_image(page.rect, stream=jpg)
            done += 1
        except Exception:  # noqa: BLE001
            continue
    return done


def lighten_feedback(doc, first: int = 0) -> None:
    """Everything above, for a feedback PDF whose student pages start at page `first`."""
    try:
        doc.rewrite_images(dpi_threshold=TARGET_DPI + 10, dpi_target=TARGET_DPI, quality=QUALITY)
    except Exception:  # noqa: BLE001
        pass                    # an older PyMuPDF: the pass below still does most of the work
    lighten(doc)
    flatten_heavy_pages(doc, first)
