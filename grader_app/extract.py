"""Local PDF processing: text per page, section split, redaction, page images.

Nothing in this module talks to the network. The output of extract_submission()
is the only material that is later sent to the model, and it is already
pseudonymized.
"""
from __future__ import annotations

import base64
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from pathlib import Path

import pymupdf

ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff"), None)
# typographic ligatures (LaTeX and many fonts write "fi" as one character): read them as plain letters, so
# "Verification" or "polyfit" in a report is found when searched for
ZERO_WIDTH.update({ord("\ufb00"): "ff", ord("\ufb01"): "fi", ord("\ufb02"): "fl", ord("\ufb03"): "ffi",
                   ord("\ufb04"): "ffl", ord("\ufb05"): "st", ord("\ufb06"): "st"})
ID_RE = re.compile(r"\b2\d{7}\b")          # Bilkent student IDs (8 digits, start with 2)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PATH_USER_RE = re.compile(r"(?i)(/Users/|/home/|C:\\Users\\|C:/Users/)([^/\\\s]+)")

# Characters that may appear in place of each letter of a Turkish name.
_LETTER_VARIANTS = {
    "i": "iIıİ", "g": "gGğĞ", "u": "uUüÜ", "o": "oOöÖ", "s": "sSşŞ", "c": "cCçÇ",
    "a": "aAâÂ", "e": "eE",
}


def clean(text: str) -> str:
    return text.translate(ZERO_WIDTH)


def fold(text: str) -> str:
    """Lower-case and strip diacritics, so 'Güven' and 'Guven' compare equal."""
    text = text.replace("ı", "i").replace("İ", "i").replace("˙", "")
    norm = unicodedata.normalize("NFKD", text)
    return "".join(c for c in norm if not unicodedata.combining(c)).lower()


def _token_regex(token: str) -> str:
    """Regex for a name token. The first letter must be upper case, so a name
    such as 'Can' or 'Ali' does not wipe out ordinary words like 'can'."""
    parts = []
    for k, ch in enumerate(fold(token)):
        variants = _LETTER_VARIANTS.get(ch, ch + ch.upper() if ch.isalpha() else "")
        if not variants:
            parts.append(re.escape(ch))
            continue
        if k == 0:
            variants = "".join(v for v in variants if v.isupper()) or variants
        parts.append("˙?[" + re.escape(variants) + "]")
    return "".join(parts)


@dataclass
class Identity:
    name: str = ""
    student_ids: list[str] = field(default_factory=list)
    usernames: list[str] = field(default_factory=list)

    def name_tokens(self) -> list[str]:
        return [t for t in re.split(r"[\s_\-]+", self.name) if len(fold(t)) >= 3]


class Redactor:
    def __init__(self, identity: Identity):
        self.identity = identity
        patterns = []
        for tok in identity.name_tokens():
            patterns.append(r"(?<![\w])" + _token_regex(tok) + r"(?![\w])")
        self.name_re = re.compile("|".join(patterns)) if patterns else None
        self.user_re = (re.compile("|".join(re.escape(u) for u in identity.usernames), re.I)
                        if identity.usernames else None)

    def text(self, s: str) -> str:
        s = PATH_USER_RE.sub(lambda m: m.group(1) + "[USER]", s)
        s = EMAIL_RE.sub("[EMAIL]", s)
        s = ID_RE.sub("[STUDENT-ID]", s)
        for sid in self.identity.student_ids:
            s = s.replace(sid, "[STUDENT-ID]")
        if self.name_re:
            s = self.name_re.sub("[STUDENT]", s)
        if self.user_re:
            s = self.user_re.sub("[USER]", s)
        return s

    def page(self, page: pymupdf.Page) -> None:
        """Black out identifying strings on a page (used before rendering images)."""
        name_folded = {fold(t) for t in self.identity.name_tokens()}
        ids = set(self.identity.student_ids)
        users = {u.lower() for u in self.identity.usernames}
        hit = False
        for x0, y0, x1, y1, word, *_ in page.get_text("words"):
            w = word.strip(".,;:()[]{}\"'`")
            if not w:
                continue
            is_name = (w[:1].isupper() or w.startswith("˙")) and fold(w) in name_folded
            is_id = bool(ID_RE.search(w)) or any(i in w for i in ids)
            is_user = any(u in w.lower() for u in users)
            if is_name or is_id or is_user:
                page.add_redact_annot(pymupdf.Rect(x0, y0, x1, y1), fill=(0, 0, 0))
                hit = True
        if hit:
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)


def detect_identity(doc: pymupdf.Document, known_name: str = "", known_ids: list[str] | None = None) -> Identity:
    ident = Identity(name="")
    first = clean(doc[0].get_text()) if len(doc) else ""
    ids = ID_RE.findall(first)
    ident.student_ids = sorted(set(ids) | {i for i in (known_ids or []) if i})
    if True:
        m = re.search(r"(?im)^\s*(?:name|ad\s*soyad|full name)\s*[:：]\s*(.+?)\s*(?:student\s*id.*)?$", first)
        if m:
            ident.name = re.split(r"\s{2,}|student\s*id|section", m.group(1), flags=re.I)[0].strip()
        elif ids:
            for line in first.splitlines():
                if ids[0] in line:
                    before = line.split(ids[0])[0].strip()
                    words = [w for w in before.split() if w[:1].isupper() or w.startswith("˙")]
                    ident.name = " ".join(words[-3:])
                    break
    # combine the known name (class list or file name) with the name written in the PDF, so that
    # redaction still works when one of them is incomplete (file names lose Turkish letters)
    tokens = []
    for t in re.split(r"[\s_]+", f"{known_name} {ident.name}"):
        if len(fold(t)) >= 2 and fold(t) not in {fold(x) for x in tokens}:
            tokens.append(t)
    ident.name = " ".join(tokens)
    users = set()
    for page in doc:
        for m in PATH_USER_RE.finditer(page.get_text()):
            users.add(m.group(2))
    ident.usernames = sorted(u for u in users if len(u) >= 3)
    return ident


@dataclass
class PageInfo:
    number: int                 # 1-based PDF page number
    section: str                # "report", "chat", "code" or mixed like "report+chat"
    needs_image: bool = False
    image_reason: str = ""


@dataclass
class Extraction:
    page_count: int
    pages: list[PageInfo]
    report_text: str
    chat_text: str
    code_text: str
    report_pages_used: float
    chat_found: bool
    code_found: bool
    warnings: list[str]
    identity: dict
    raw_report_text: str = ""   # unredacted, kept locally for checks only
    raw_code_text: str = ""
    raw_chat_text: str = ""
    appendix_image_pages: list = field(default_factory=list)   # [(page, "chat"|"code")] with no text layer
    report_image_pages: list = field(default_factory=list)     # report pages with no text layer
    hidden_text: list = field(default_factory=list)            # [{page, text, reason}] removed before the AI
    hidden_checked: bool = False                               # False for extractions by older versions

    def to_json(self) -> dict:
        d = asdict(self)
        return d

    @staticmethod
    def from_json(d: dict) -> "Extraction":
        d = dict(d)
        d["pages"] = [PageInfo(**p) for p in d["pages"]]
        return Extraction(**d)


def _heading_positions(doc: pymupdf.Document, pattern: str) -> list[tuple[int, int, float]]:
    """Return (page_index, line_index, y_fraction) for lines that look like headings."""
    rx = re.compile(pattern, re.I)
    hits = []
    for pi, page in enumerate(doc):
        lines = [l for l in clean(page.get_text()).splitlines()]
        for li, line in enumerate(lines):
            s = line.strip()
            if len(s) <= 70 and rx.search(s):
                y = 0.0
                rects = page.search_for(s[:40]) if s else []
                if rects:
                    y = rects[0].y0 / max(1.0, page.rect.height)
                hits.append((pi, li, y))
    return hits


CHAT_URL_RE = re.compile(r"(?i)(chatgpt\.com|chat\.openai\.com|claude\.ai|gemini\.google\.com|chat\.deepseek\.com|"
                         r"copilot\.microsoft\.com|perplexity\.ai|grok\.com|poe\.com|aistudio\.google\.com)")
_PREFIX = r"^(?:\d+[.)]?\s*|[a-z][.)]\s*)?"
CHAT_HEAD_RE = re.compile(_PREFIX + r"(?:appendix\s*[-:–]?\s*)?(?:ai\s+chats?|chat\s*history|chat\s*logs?|"
                          r"ai\s+(?:chat|conversation|interaction|usage)s?(?:\s+(?:history|record|log|transcript))?|"
                          r"conversation\s+(?:history|log|transcript)|(?:full\s+)?(?:chat|ai)\s+transcripts?)\s*:?\s*$", re.I)
CODE_HEAD_RE = re.compile(_PREFIX + r"(?:appendix\s*[-:–]?\s*)?(?:code|python\s+code|source\s+code|full\s+code|"
                          r"code\s+listing|implementation\s+code)\s*:?\s*$", re.I)
BARE_APPENDIX_RE = re.compile(_PREFIX + r"appendi(?:x|ces)\s*:?\s*$", re.I)
CODE_LINE_RE = re.compile(r"^\s*(?:\d{1,4}\s+)?(?:def |import |from \S+ import|for .+:$|if .+:$|return\b|print\(|#|class |while .+:$|"
                          r"\w+\s*=\s*\S|\w+\[.+\]\s*=|\)\s*$)")


def _lines(page) -> list[str]:
    return clean(page.get_text()).splitlines()


def _looks_like_code(lines: list[str]) -> bool:
    ls = [l for l in lines if l.strip() and not l.strip().isdigit()][:40]   # skip bare line numbers
    return bool(ls) and sum(1 for l in ls if CODE_LINE_RE.match(l)) / len(ls) >= 0.3


def _is_chat_print_page(lines: list[str]) -> bool:
    edge = [l for l in lines if l.strip()]
    edge = edge[:3] + edge[-3:]
    return any(CHAT_URL_RE.search(l) for l in edge)


def find_sections(doc, chat_pat: str, code_pat: str):
    """Locate the start of the AI record and of the code appendix as (page, line, y).

    Tries, in order: the pack's Appendix A/B patterns, common alternative headings
    ("AI Chats", "Chat History", "Code"), a bare "Appendix" heading classified by what follows,
    and pages printed from a chatbot website (URL in the page header or footer)."""
    chat_rx, code_rx = re.compile(chat_pat, re.I), re.compile(code_pat, re.I)
    chat_h, code_h, bare_h, url_pages = [], [], [], []
    for pi, page in enumerate(doc):
        lines = _lines(page)
        for li, line in enumerate(lines):
            st = line.strip()
            if not st or len(st) > 70:
                continue
            nxt = [l for l in lines[li + 1: li + 40]]
            if pi + 1 < len(doc) and len(nxt) < 15:
                nxt += _lines(doc[pi + 1])[:30]
            if chat_rx.search(st):
                chat_h.append((pi, li, 1))
            elif code_rx.search(st):
                code_h.append((pi, li, 1))
            elif CHAT_HEAD_RE.search(st):
                chat_h.append((pi, li, 2))
            elif CODE_HEAD_RE.search(st) and _looks_like_code(nxt):
                code_h.append((pi, li, 2))
            elif BARE_APPENDIX_RE.search(st):
                bare_h.append((pi, li, "code" if _looks_like_code(nxt) else "chat"))
        if pi > 0 and _is_chat_print_page(lines):
            url_pages.append(pi)

    note = ""
    first_page_min = 1 if len(doc) > 2 else 0
    chat_h = [h for h in chat_h if h[0] >= first_page_min]
    code_h = [h for h in code_h if h[0] >= first_page_min]
    chat = min(chat_h, key=lambda h: (h[2], h[0], h[1])) if chat_h else None
    if chat is None and bare_h and bare_h[0][2] == "chat":
        chat, note = bare_h[0], "AI record found under a plain 'Appendix' heading."
    if chat is None and url_pages:
        chat = (url_pages[0], 0, 3)
        note = ("AI record located from pages printed from a chatbot website (no 'Appendix A' heading). "
                "Check where the main report ends.")
    if chat is None:
        # a block of image-only pages after the report: printed or screenshotted appendices
        blank = [len(clean(p.get_text()).strip()) < 40 and (bool(p.get_images()) or len(p.get_drawings()) >= 50)
                 for p in doc]
        for pi in range(1, len(doc) - 2):
            if blank[pi] and blank[pi + 1] and blank[pi + 2] and not any(blank[:pi]):
                chat = (pi, 0, 4)
                note = (f"No appendix headings found. Pages {pi + 1} onwards are images with no selectable text "
                        "and are treated as the AI record (they may also contain code).")
                break
    code_cands = [h for h in code_h if chat is None or (h[0], h[1]) > (chat[0], chat[1])]
    code = min(code_cands, key=lambda h: (h[2], h[0], h[1])) if code_cands else None
    if code is None:
        bare_code = [h for h in bare_h if h[2] == "code" and (chat is None or (h[0], h[1]) > (chat[0], chat[1]))]
        if bare_code:
            code = bare_code[0]
            note = (note + " " if note else "") + "Code found under a plain 'Appendix' heading."

    def pos(h):
        if h is None:
            return None
        page = doc[h[0]]
        text = _lines(page)[h[1]].strip() if h[1] < len(_lines(page)) else ""
        rects = page.search_for(text[:40]) if text else []
        y = rects[0].y0 / max(1.0, page.rect.height) if rects else 0.0
        return (h[0], h[1], y)
    return pos(chat), pos(code), note


def _page_features(page: pymupdf.Page) -> tuple[bool, str]:
    text = clean(page.get_text())
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return (len(page.get_images()) > 0, "image only")
    words = sum(len(l.split()) for l in lines)
    wpl = words / len(lines)
    math_chars = sum(1 for c in text if 0x1D400 <= ord(c) <= 0x1D7FF)
    num_lines = sum(1 for l in lines if re.fullmatch(r"[-+0-9.,()\s×⋅*eE−⎡⎢⎣⎤⎥⎦]+", l))
    if page.get_images():
        return True, "contains a figure"
    if math_chars >= 30:
        return True, "equations may not extract cleanly"
    if num_lines / len(lines) > 0.4 and len(lines) > 20:
        return True, "numerical table"
    if wpl < 3.5 and len(lines) > 25:
        return True, "fragmented text layout"
    return False, ""


def extract_submission(pdf_path: str | Path, known_name: str = "", report_pattern_cfg: dict | None = None,
                       max_images: int = 8, known_ids: list[str] | None = None) -> Extraction:
    cfg = report_pattern_cfg or {}
    chat_pat = cfg.get("appendix_chat_pattern", r"^(\d+\s+)?appendix\s*a\b")
    code_pat = cfg.get("appendix_code_pattern", r"^(\d+\s+)?appendix\s*b\b")
    warnings: list[str] = []

    doc = pymupdf.open(pdf_path)
    # text a reader cannot see (white on white, microscopic, invisible) is removed before anything is read,
    # so it never reaches the AI; the grader is told about it
    try:
        from .hidden import strip_hidden
        hidden = strip_hidden(doc)
    except Exception:  # noqa: BLE001
        hidden = []
    identity = detect_identity(doc, known_name, known_ids)
    red = Redactor(identity)

    chat_start, code_start, how = find_sections(doc, chat_pat, code_pat)
    if how:
        warnings.append(how)

    boundaries = []
    if chat_start:
        boundaries.append((chat_start[0], chat_start[1], "chat"))
    else:
        warnings.append("No AI record (Appendix A) could be located.")
    if code_start:
        boundaries.append((code_start[0], code_start[1], "code"))
    else:
        warnings.append("No code appendix (Appendix B) could be located.")
    boundaries.sort()

    sections = {"report": [], "chat": [], "code": []}
    raw_sections = {"report": [], "chat": [], "code": []}
    pages: list[PageInfo] = []
    for pi, page in enumerate(doc):
        lines = clean(page.get_text()).splitlines()
        current = "report"
        for b in boundaries:
            if (b[0], b[1]) <= (pi, 0):
                current = b[2]
        page_sections = []
        chunk: list[str] = []

        def flush(sec, ch):
            if ch:
                raw = "\n".join(ch)
                raw_sections[sec].append(f"[page {pi + 1}]\n{raw}")
                sections[sec].append(f"[page {pi + 1}]\n{red.text(raw)}")
                if sec not in page_sections:
                    page_sections.append(sec)

        for li, line in enumerate(lines):
            for b in boundaries:
                if (b[0], b[1]) == (pi, li) and b[2] != current:
                    flush(current, chunk)
                    chunk = []
                    current = b[2]
            chunk.append(line)
        flush(current, chunk)
        pages.append(PageInfo(number=pi + 1, section="+".join(page_sections) or current))

    # main report length in pages
    if chat_start:
        used = chat_start[0] + (chat_start[2] if chat_start[1] > 0 else 0.0)
    elif code_start:
        used = code_start[0] + code_start[2]
    else:
        used = float(len(doc))

    # decide which report pages get an image
    candidates = []
    for p in pages:
        if "report" not in p.section:
            continue
        need, why = _page_features(doc[p.number - 1])
        if need:
            p.needs_image, p.image_reason = True, why
            candidates.append(p)
    if len(candidates) > max_images:
        # keep figures and tables first, then equation pages
        order = {"contains a figure": 0, "numerical table": 1}
        keep = sorted(candidates, key=lambda p: order.get(p.image_reason, 2))[:max_images]
        for p in candidates:
            if p not in keep:
                p.needs_image = False
                p.image_reason = ""
        warnings.append(f"{len(candidates)} report pages qualified for images; sent the first {max_images}.")

    def image_page(pg, appendix: bool) -> bool:
        """A page whose content is a picture rather than text: a screenshot, scan or printout.

        No real text plus a picture or outlined text counts everywhere. In the appendices, a page that is mostly
        picture with only a little text (for example a running header above a screenshot) also counts. In the
        report that second rule is not used, since a large figure with a caption is normal there."""
        n_text = len(clean(pg.get_text()).strip())
        if n_text < 40 and (bool(pg.get_images()) or len(pg.get_drawings()) >= 50):
            return True
        if appendix and n_text < 300:
            area = pg.rect.width * pg.rect.height or 1.0
            covered = 0.0
            for info in pg.get_image_info():
                b = pymupdf.Rect(info.get("bbox", (0, 0, 0, 0))) & pg.rect
                covered += max(0.0, b.width) * max(0.0, b.height)
            return covered / area >= 0.5
        return False

    img_pages, rep_img = [], []
    for p in pages:
        sec = p.section.split("+")[-1]
        empty = image_page(doc[p.number - 1], sec in ("chat", "code"))
        if sec in ("chat", "code") and empty:
            img_pages.append((p.number, sec))
        elif p.section == "report" and empty:
            rep_img.append(p.number)
    if img_pages:
        warnings.append(f"{len(img_pages)} appendix pages are images with no selectable text "
                        "(screenshots or printed pages).")

    ext = Extraction(
        page_count=len(doc), pages=pages, appendix_image_pages=img_pages, report_image_pages=rep_img,
        report_text="\n".join(sections["report"]),
        chat_text="\n".join(sections["chat"]),
        code_text="\n".join(sections["code"]),
        report_pages_used=round(used, 2),
        chat_found=bool(chat_start), code_found=bool(code_start),
        warnings=warnings, identity=asdict(identity),
        raw_report_text="\n".join(raw_sections["report"]),
        raw_code_text="\n".join(raw_sections["code"]),
        raw_chat_text="\n".join(raw_sections["chat"]),
        hidden_text=hidden, hidden_checked=True,
    )
    doc.close()
    return ext


def render_redacted_pages(pdf_path: str | Path, page_numbers: list[int], identity: dict,
                          dpi: int = 110) -> list[tuple[int, str]]:
    """Return [(page_number, base64 JPEG)] with identifying text blacked out."""
    if not page_numbers:
        return []
    ident = Identity(**identity)
    red = Redactor(ident)
    out = []
    src = pymupdf.open(pdf_path)
    for n in page_numbers:
        tmp = pymupdf.open()
        tmp.insert_pdf(src, from_page=n - 1, to_page=n - 1)
        page = tmp[0]
        try:
            red.page(page)
        except Exception:
            pass
        pix = page.get_pixmap(dpi=dpi)
        jpg = pix.tobytes("jpeg", jpg_quality=72)
        out.append((n, base64.b64encode(jpg).decode("ascii")))
        tmp.close()
    src.close()
    return out
