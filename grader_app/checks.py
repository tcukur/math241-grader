"""Deterministic checks that need no AI: reference values, headings, page
limit, appendix presence, and whether reported checks have matching code."""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

from .extract import Extraction
from .pack import Pack

NUM_RE = re.compile(r"(?<![\w.])[-−]?\d+(?:[.,]\s?\d+)?")
PAGE_MARK_RE = re.compile(r"\[page (\d+)\]")


@dataclass
class CheckResult:
    id: str
    row: str            # rubric row id, or "integrity"
    label: str
    status: str         # "pass", "warn", "info"
    detail: str
    page: int | None = None
    integrity_category: str | None = None

    def to_json(self):
        return asdict(self)


def _numbers_with_pages(text: str):
    """Yield (value, page, position) for numbers in text with [page N] markers."""
    page = 1
    marks = [(m.start(), int(m.group(1))) for m in PAGE_MARK_RE.finditer(text)]
    mi = 0
    for m in NUM_RE.finditer(text):
        while mi < len(marks) and marks[mi][0] <= m.start():
            page = marks[mi][1]
            mi += 1
        s = m.group(0).replace("−", "-").replace(" ", "")
        if "," in s and "." not in s:
            s = s.replace(",", ".")
        try:
            yield float(s), page, m.start()
        except ValueError:
            continue


def _page_at(text: str, pos: int) -> int:
    page = 1
    for m in PAGE_MARK_RE.finditer(text):
        if m.start() > pos:
            break
        page = int(m.group(1))
    return page


def _norm_heading(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


# words any genuine verification item talks about; used to recognise the student's own "(d) ..." item
_CHECK_WORDS = ("current", "kirchhoff", "kcl", "residual", "norm", "prescribed", "boundary", "driven",
                "symmetr", "structur", "laplacian", "row sum", "voltage")


def _item_present(tc: dict, low_report: str) -> bool:
    """A check counts as presented when the report has the student's own item for it, for example "(d) For each
    prescribed node I sum ...", whatever the wording."""
    m = re.match(r"\s*\((\w)\)", tc.get("label", ""))
    if not m:
        return False
    marker = f"({m.group(1).lower()})"
    words = tuple(tc.get("near_words") or _CHECK_WORDS)
    start = 0
    while True:
        i = low_report.find(marker, start)
        if i < 0:
            return False
        if any(w in low_report[i:i + 400] for w in words):
            return True
        start = i + 1


def run_checks(pack: Pack, ext: Extraction) -> list[CheckResult]:
    out: list[CheckResult] = []
    hidden = getattr(ext, "hidden_text", None) or []
    if hidden:
        pages = sorted({h["page"] for h in hidden})
        shown = "; ".join(f"p.{h['page']}, {h['reason']}: \u201c{h['text'][:120]}\u201d" for h in hidden[:4])
        out.append(CheckResult("hidden_text", "integrity", "Hidden text in the PDF", "warn",
                               f"Text a reader cannot see was found on page(s) {', '.join(map(str, pages))} and "
                               f"was kept away from the AI. {shown}" + (" …" if len(hidden) > 4 else ""),
                               page=pages[0], integrity_category="other"))
    report = ext.raw_report_text
    code = ext.raw_code_text
    chat = ext.raw_chat_text

    # appendices ---------------------------------------------------------
    chat_imgs = [p for p, sec in (ext.appendix_image_pages or []) if sec == "chat"]
    code_imgs = [p for p, sec in (ext.appendix_image_pages or []) if sec == "code"]
    share_rx = (r"https?://(?:chatgpt\.com/s(?:hare)?/|chat\.openai\.com/share/|claude\.ai/share/|"
                r"g\.co/gemini/share/|gemini\.google\.com/share/|chat\.deepseek\.com/a/chat/s/)\S+")
    share_links = re.findall(share_rx, chat)
    chat_body = re.sub(r"\[page \d+\]|https?://\S+", "", chat)
    has_chat_text = ext.chat_found and len(chat_body.strip()) >= 600
    if not has_chat_text and not share_links:
        # no AI record section: a share link may still be given somewhere else in the PDF
        share_links = re.findall(share_rx, report + "\n" + code)

    def pages_txt(ps):
        ps = sorted(ps)
        return f"page {ps[0]}" if len(ps) == 1 else f"pages {ps[0]}-{ps[-1]} ({len(ps)} pages)"

    # AI record -------------------------------------------------------------
    if share_links and not has_chat_text and not chat_imgs:
        links = " ".join(sorted(set(share_links))[:3])
        out.append(CheckResult("chat_link_only", "integrity", "AI record (Appendix A)", "warn",
                               "The AI record is only a share link, not the conversation in the PDF. The link may "
                               f"or may not open; check it by hand if needed: {links}",
                               page=(_page_at(chat, chat.find(share_links[0])) if share_links[0] in chat
                                     else _page_at(report, report.find(share_links[0])) if share_links[0] in report
                                     else None),
                               integrity_category="link_only_record"))
    elif not has_chat_text and not chat_imgs:
        out.append(CheckResult("chat_present", "integrity", "AI record (Appendix A)", "warn",
                               "No AI interaction record was found in the submission.",
                               integrity_category="missing_record"))
    else:
        out.append(CheckResult("chat_present", "integrity", "AI record (Appendix A)", "pass",
                               f"Found, about {len(chat) // 1000}k characters of text."))
    if chat_imgs:
        whole = not has_chat_text
        out.append(CheckResult("chat_images", "integrity", "AI record as images", "warn",
                               ("The AI record is submitted as images" if whole else
                                "Part of the AI record is submitted as images")
                               + f" (screenshots or printed pages, {pages_txt(chat_imgs)}) instead of selectable "
                               "text, against the instructions.", page=min(chat_imgs),
                               integrity_category="chat_as_images"))

    # code -------------------------------------------------------------------
    has_code_text = ext.code_found and len(code.strip()) >= 100
    if code_imgs:
        out.append(CheckResult("code_images", "integrity", "Code as images", "warn",
                               f"Code is submitted as images ({pages_txt(code_imgs)}) instead of selectable text, "
                               "against the instructions.", page=min(code_imgs),
                               integrity_category="code_as_images"))
    if not has_code_text and not code_imgs:
        if chat_imgs:
            out.append(CheckResult("code_present", "integrity", "Code (Appendix B)", "warn",
                                   "No code was found as text. It may be inside the image pages, which would also "
                                   "break the rule that code must be selectable text. Check by hand.",
                                   integrity_category="code_as_images"))
        else:
            out.append(CheckResult("code_present", "integrity", "Code (Appendix B)", "warn",
                                   "No code appendix was found, or it is nearly empty.",
                                   integrity_category="untraceable_results"))
    elif has_code_text:
        out.append(CheckResult("code_present", "integrity", "Code (Appendix B)", "pass",
                               f"Found, about {len(code.splitlines())} lines."))

    # report pages without text --------------------------------------------------
    rep_imgs = list(ext.report_image_pages or [])
    if rep_imgs:
        out.append(CheckResult("report_images", "info", "Report pages as images", "warn",
                               f"Report {pages_txt(rep_imgs)} have no selectable text. This is allowed only for "
                               "handwritten derivations. Reject this finding if that is what they contain.",
                               page=min(rep_imgs), integrity_category="report_as_images"))

    # placeholders in chat -------------------------------------------------
    for pat in pack.data.get("chat_placeholder_patterns", []):
        for m in re.finditer(pat, chat, re.I):
            snippet = chat[m.start(): m.start() + 110].replace("\n", " ")
            out.append(CheckResult("chat_placeholder", "integrity", "Summarized AI response", "warn",
                                   f"The record describes an AI response instead of showing it: \"{snippet}...\"",
                                   page=_page_at(chat, m.start()),
                                   integrity_category="incomplete_record"))

    # page limit -----------------------------------------------------------
    limit = pack.report.get("page_limit")
    if limit:
        used = ext.report_pages_used
        status = "warn" if used > limit + 0.25 else "pass"
        out.append(CheckResult("page_limit", "info", "Main report length", status,
                               f"Main report runs to about {used:g} pages (limit {limit})."))

    # suggested headings: information only. Students often use their own headings, so a missing one never
    # flags a row; the content is what counts
    norm_report = _norm_heading(report)
    missing = [h["text"] for h in pack.report.get("required_headings", [])
               if _norm_heading(h["text"]) not in norm_report]
    if missing:
        out.append(CheckResult("headings", "info", "Suggested headings not used", "info",
                               "Not found word for word: " + ", ".join(f'"{m}"' for m in missing)
                               + ". Students may use their own headings, so judge by content."))

    # reference values -------------------------------------------------------
    nums = list(_numbers_with_pages(report))
    for rc in pack.data.get("reference_checks", []):
        found_page = None
        t = rc["type"]
        if t == "number":
            v, tol = rc["value"], rc.get("rel_tol", 1e-3)
            for x, pg, _ in nums:
                if abs(x - v) <= tol * abs(v):
                    found_page = pg
                    break
        elif t == "any_number":
            vals = rc["values"]
            for x, pg, _ in nums:
                if any(abs(x - v) < 1e-9 for v in vals):
                    found_page = pg
                    break
        elif t == "number_near":
            v, words, win = rc["value"], rc["near"], rc.get("window", 100)
            low = report.lower()
            for x, pg, pos in nums:
                if abs(x - v) < 1e-9:
                    ctx = low[max(0, pos - win): pos + win]
                    if any(w in ctx for w in words):
                        found_page = pg
                        break
        elif t == "all_patterns":
            pages = []
            for p in rc["patterns"]:
                m = re.search(p, report)
                pages.append(_page_at(report, m.start()) if m else None)
            if all(pages):
                found_page = pages[0]
        if found_page:
            out.append(CheckResult(rc["id"], rc["row"], rc["label"], "pass",
                                   "Matching value found in the report.", page=found_page))
        else:
            pics = [p.number for p in ext.pages if p.needs_image and "report" in p.section]
            out.append(CheckResult(rc["id"], rc["row"], rc["label"], "warn",
                                   "Not found in the report text. Could be a different result, "
                                   "different formatting, or an extraction issue."
                                   + (f" Parts of the report are pictures (p.{', '.join(map(str, pics[:6]))}), so it "
                                      "may be shown in an image. The AI was given those pages." if pics else ""), ))

    # report claims vs code ---------------------------------------------------
    # NFKC turns Word's maths letters (𝐼𝑡𝑜𝑡𝑎𝑙, 𝐴𝑉) into plain ones, so wording in equations is matched too
    import unicodedata
    low_report = unicodedata.normalize("NFKC", report).lower()
    low_code = unicodedata.normalize("NFKC", code).lower()
    trace = pack.data.get("trace_checks", []) if len(code.strip()) >= 100 else []
    status = []
    for tc in trace:
        claimed = any(re.search(p, low_report, re.I) for p in tc["report_patterns"]) or _item_present(tc, low_report)
        in_code = any(re.search(p, low_code, re.I) for p in tc["code_patterns"])
        status.append((tc, claimed, in_code))
    misses = [tc for tc, claimed, in_code in status if claimed and not in_code]
    # A single miss is often just a different (valid) way of doing the check, so it only
    # becomes an integrity hint when most claimed checks have no recognizable code.
    claimed_n = sum(1 for _, c, _ in status if c)
    systematic = claimed_n and len(misses) >= max(2, (claimed_n + 1) // 2)
    for tc, claimed, in_code in status:
        if claimed and not in_code:
            out.append(CheckResult(f"trace:{tc['id']}", tc["row"], tc["label"], "warn",
                                   "The report presents this check, but the automatic scan did not recognize "
                                   "matching code in Appendix B. The student may have used a different method. "
                                   "Confirm whether it is produced by the submitted code or shown in the AI record.",
                                   integrity_category="untraceable_results" if systematic else None))
        elif not claimed:
            out.append(CheckResult(f"trace:{tc['id']}", tc["row"], tc["label"], "warn",
                                   "The report does not appear to present this check."))
        else:
            out.append(CheckResult(f"trace:{tc['id']}", tc["row"], tc["label"], "pass",
                                   "Presented in the report and a matching computation appears in the code."))
    return out


def checks_summary_for_model(results: list[CheckResult]) -> str:
    lines = []
    for r in results:
        if r.id == "hidden_text":
            # never pass the hidden text itself on to the AI
            lines.append("- [INFO] Hidden text was found in the PDF and removed before this pre-screen. The "
                         "grader reviews it. Do not report it yourself.")
            continue
        mark = {"pass": "OK", "warn": "CHECK", "info": "INFO"}.get(r.status, r.status)
        pg = f" (p.{r.page})" if r.page else ""
        lines.append(f"- [{mark}] {r.label}{pg}: {r.detail}")
    return "\n".join(lines)
