"""Export: feedback PDFs (cover page + original submission), a Moodle-ready
ZIP, the filled grading worksheet and an instructor summary of findings."""
from __future__ import annotations

import csv
import html
import json
import io
import zipfile
from datetime import date, datetime
from pathlib import Path

import pymupdf

from .moodle import Worksheet, read_class_list, read_worksheet, safe_filename, write_worksheet
from .pack import Pack
from .scoring import compute, fmt

CSS = """
* { font-family: sans-serif; }
body { font-size: 10pt; color: #1d1d1f; }
h1 { font-size: 16pt; margin: 0 0 2pt 0; }
.sub { color: #555; font-size: 9.5pt; margin-bottom: 10pt; }
table { border-collapse: collapse; width: 100%; margin-top: 4pt; }
th { background: #eef0f3; text-align: left; font-size: 9pt; padding: 4pt; border-bottom: 1px solid #c8ccd2; }
td { padding: 4pt; border-bottom: 1px solid #e3e5e8; vertical-align: top; font-size: 9.5pt; }
td.num { text-align: right; white-space: nowrap; }
tr.group td { background: #f7f8fa; font-weight: bold; font-size: 9pt; color: #333; }
.total td { font-weight: bold; font-size: 11pt; border-top: 1.5px solid #333; border-bottom: none; }
h2 { font-size: 11.5pt; margin: 14pt 0 2pt 0; }
.note { color: #555; font-size: 9pt; }
.finding { margin: 4pt 0; }
"""


def _esc(s: str) -> str:
    return html.escape(s or "").replace("\n", "<br/>")


def cover_html(pack: Pack, sub: dict, review: dict, result: dict, grader: str) -> str:
    rows_html = []
    last_group = None
    comments = review.get("comments", {})
    for r in result["rows"]:
        if r["group"] != last_group:
            rows_html.append(f'<tr class="group"><td colspan="3">{_esc(r["group"])}</td></tr>')
            last_group = r["group"]
        note = _esc(comments.get(r["id"], ""))
        if r["capped"]:
            cap_note = f"Limited to {fmt(r['cap_pct'])}% because of an integrity finding below."
            note = f"{note}<br/><i>{cap_note}</i>" if note else f"<i>{cap_note}</i>"
        rows_html.append(f'<tr><td>{_esc(r["label"])}</td><td class="num">{fmt(r["score"])} / {fmt(r["max"])}</td>'
                         f'<td>{note}</td></tr>')

    ded_rows = ""
    findings_html = ""
    confirmed = [f for f in review.get("findings", []) if f.get("decision") in ("full", "half", "none")]
    if confirmed:
        items = []
        ded_by_uid = {d["uid"]: d["points"] for d in result["deductions"]}
        for f in confirmed:
            cat = pack.category(f.get("category"))
            label = cat.label if cat else f.get("category", "")
            text = cat.student_text if cat else ""
            pts = ded_by_uid.get(f["uid"], 0)
            overlap = next((d.get("overlap") for d in result["deductions"] if d["uid"] == f["uid"]), None)
            pen = (f"{fmt(pts)} points" if pts else
                   f"counted under \"{overlap}\"" if overlap else "no point deduction")
            extra = f"<br/><span class='note'>Grader note: {_esc(f.get('comment', ''))}</span>" if f.get("comment") else ""
            items.append(f"<p class='finding'><b>{_esc(label)}</b> ({pen}). {_esc(text)}{extra}</p>")
        findings_html = "<h2>Integrity findings</h2>" + "".join(items)
        if result["deduction_sum"] > result["deduction_total"] and pack.integrity_cap < pack.total_max:
            findings_html += (f"<p class='note'>Integrity deductions are capped at {fmt(pack.integrity_cap)} points.</p>")
    if result["deduction_total"]:
        ded_rows = (f'<tr><td>Integrity deductions</td><td class="num">-{fmt(result["deduction_total"])}</td>'
                    f'<td></td></tr>')

    overall = review.get("overall_comment", "").strip()
    overall_html = f"<h2>Comments</h2><p>{_esc(overall)}</p>" if overall else ""
    for req in review.get("regrade") or []:
        from .regrade import changes, summary
        ch = changes(pack, req)
        overall_html += ("<h2>Regrade request</h2>"
                         f"<p class='note'>You asked: {_esc(req.get('request', ''))}</p>"
                         f"<p>{_esc(req.get('reply', ''))}</p>"
                         f"<p class='note'>{_esc(summary(pack, req))}"
                         + (" " + _esc(". ".join(ch)) + "." if ch else "") + "</p>")
    info = _info(sub)
    if info.get("id_number"):
        idline = f"Student ID {info['id_number']}"
    elif sub.get("layout") in ("folder", "flat"):
        idline = f"Moodle participant {sub['sub_id']}"
    else:
        idline = sub["sub_id"]
    name = info.get("full_name") or sub.get("name") or sub.get("sub_id")
    grader_line = f" &nbsp;·&nbsp; Graded by {_esc(grader)}" if grader else ""
    return f"""
<h1>{_esc(pack.title)}: Feedback</h1>
<div class="sub">{_esc(name)} &nbsp;·&nbsp; {_esc(idline)}{grader_line} &nbsp;·&nbsp; {date.today().isoformat()}</div>
<table>
<tr><th>Rubric item</th><th>Score</th><th>Comment</th></tr>
{''.join(rows_html)}
{ded_rows}
<tr class="total"><td>Total</td><td class="num">{fmt(result["total"])} / {fmt(result["max"])}</td><td></td></tr>
</table>
{findings_html}
{overall_html}
<p class="note" style="margin-top:16pt">Your original submission follows this page.</p>
"""


def make_cover_pdf(html_body: str) -> bytes:
    buf = io.BytesIO()
    story = pymupdf.Story(html=html_body, user_css=CSS, archive=None)
    writer = pymupdf.DocumentWriter(buf)
    mediabox = pymupdf.paper_rect("a4")
    where = mediabox + (50, 50, -50, -50)
    more = True
    while more:
        dev = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    return buf.getvalue()


def feedback_pdf(pack: Pack, sub: dict, review: dict, grader: str) -> bytes:
    result = compute(pack, review)
    cover = pymupdf.open("pdf", make_cover_pdf(cover_html(pack, sub, review, result, grader)))
    try:
        orig = pymupdf.open(sub["pdf_path"])
        cover.insert_pdf(orig)
        orig.close()
    except Exception:
        pass
    data = cover.tobytes(garbage=3, deflate=True)
    cover.close()
    return data


def _info(sub: dict) -> dict:
    try:
        return json.loads(sub.get("info") or "{}")
    except Exception:
        return {}


def feedback_filename(pack: Pack, sub: dict) -> str:
    """Name built from Moodle's identifying prefix, not the student's own file name.

    Moodle layouts keep the exact 'Full Name_participant_assignsubmission_file_' prefix that
    Moodle generated (which its feedback ZIP import also relies on) and add the assignment tag:
      'Ayşe Yılmaz_1001_assignsubmission_file_MATH241-A1_feedback.pdf'
    Other layouts use the name and ID found in the PDF."""
    tag = pack.data.get("short_name") or pack.id
    if sub.get("layout") in ("folder", "flat") and sub.get("moodle_prefix"):
        prefix = sub["moodle_prefix"]
        if not prefix.endswith("_"):
            prefix += "_"
        return safe_filename(f"{prefix}{tag}_feedback.pdf")
    who = "_".join(x for x in (sub.get("name") or "", sub["sub_id"]) if x)
    return safe_filename(f"{who}_{tag}_feedback.pdf")


def feedback_comment_text(pack: Pack, review: dict, result: dict) -> str:
    parts = [f"{r['label']}: {fmt(r['score'])}/{fmt(r['max'])}" for r in result["rows"]]
    if result["deduction_total"]:
        parts.append(f"Integrity deductions: -{fmt(result['deduction_total'])}")
    parts.append(f"Total: {fmt(result['total'])}/{fmt(result['max'])}")
    text = "; ".join(parts) + ". See the attached feedback PDF for details."
    return text


def export_all(pack: Pack, subs: list[dict], reviews: dict[str, dict], out_dir: Path, grader: str,
               worksheet_path: Path | None, only_reviewed: bool = True, progress=None,
               only_ids: set | None = None) -> dict:
    out_dir = Path(out_dir)
    pdf_dir = out_dir / "feedback_pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / "moodle_feedback_files.zip"
    written, skipped = [], []
    grade_rows = []
    findings_rows = []

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for i, sub in enumerate(subs):
            rev = reviews.get(sub["sub_id"])
            if rev is None or (only_reviewed and not rev.get("reviewed")) \
                    or (only_ids is not None and sub["sub_id"] not in only_ids):
                skipped.append(sub["sub_id"])
                continue
            result = compute(pack, rev)
            data = feedback_pdf(pack, sub, rev, grader)
            fname = feedback_filename(pack, sub)
            local_name = fname
            (pdf_dir / local_name).write_bytes(data)
            if sub.get("layout") == "folder":
                arc = f"{sub['moodle_prefix']}/{fname}"
            elif sub.get("layout") == "flat":
                arc = fname
            else:
                arc = local_name
            z.writestr(arc, data)
            written.append(sub["sub_id"])
            grade_rows.append((sub, rev, result))
            for f in rev.get("findings", []):
                cat = pack.category(f.get("category"))
                ded = next((d["points"] for d in result["deductions"] if d["uid"] == f["uid"]), 0)
                findings_rows.append({
                    "participant": sub["sub_id"], "name": sub.get("name", ""),
                    "category": cat.label if cat else f.get("category"), "origin": f.get("origin", ""),
                    "decision": f.get("decision"), "points": ded,
                    "affected_rows": ",".join(f.get("affected_rows", [])),
                    "summary": f.get("summary", ""), "ta_comment": f.get("comment", ""),
                })
            if progress:
                progress(i + 1, len(subs))

    # grades CSV (always) ----------------------------------------------------
    grades_csv = out_dir / "grades_detailed.csv"
    with open(grades_csv, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["Participant", "Name", "ID number", "Email", "Original file", "Feedback file"]
                   + [r.label for r in pack.rubric]
                   + ["Rubric total", "Integrity deductions", "Total", "Max", "Reviewer"])
        for sub, rev, res in grade_rows:
            inf = _info(sub)
            w.writerow([sub["sub_id"], inf.get("full_name") or sub.get("name", ""), inf.get("id_number", ""),
                        inf.get("email", ""), inf.get("original_file", Path(sub["pdf_path"]).name),
                        feedback_filename(pack, sub)] + [fmt(r["score"]) for r in res["rows"]]
                       + [fmt(res["rubric_total"]), fmt(res["deduction_total"]), fmt(res["total"]),
                          fmt(res["max"]), rev.get("reviewer", "")])

    findings_csv = out_dir / "integrity_findings_for_instructor.csv"
    with open(findings_csv, "w", newline="", encoding="utf-8-sig") as fh:
        cols = ["participant", "name", "category", "origin", "decision", "points", "affected_rows",
                "summary", "ta_comment"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(findings_rows)

    # Moodle worksheet --------------------------------------------------------
    ws_out = None
    ws_note = ""
    is_roster = False
    if worksheet_path and Path(worksheet_path).exists():
        try:
            is_roster = read_class_list(Path(worksheet_path))["kind"] == "roster"
        except Exception:
            is_roster = False
    if is_roster:
        # gradebook export: write a file for Moodle's gradebook CSV import, matched by ID number
        tag = pack.data.get("short_name") or pack.id
        ws_out = out_dir / f"moodle_gradebook_import_{safe_filename(tag)}.csv"
        n = 0
        with open(ws_out, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["ID number", "Email address", "Full name", f"{tag} grade", f"{tag} feedback"])
            for sub, rev, res in grade_rows:
                inf = _info(sub)
                if not inf.get("id_number"):
                    continue
                w.writerow([inf["id_number"], inf.get("email", ""), inf.get("full_name", sub.get("name", "")),
                            fmt(res["total"]) if res["complete"] else "", feedback_comment_text(pack, rev, res)
                            if res["complete"] else "Not graded yet."])
                n += 1
        missing = len(grade_rows) - n
        ws_note = (f"{n} grades written for Moodle's gradebook import (Grades > Import > CSV file, identify users "
                   f"by ID number).") + (f" {missing} students had no class-list match and are only in "
                                         "grades_detailed.csv." if missing else "")
    elif worksheet_path and Path(worksheet_path).exists():
        ws: Worksheet = read_worksheet(Path(worksheet_path))
        gcol = ws.col("Grade")
        fcol = ws.col("Feedback comments")
        mx = ws.max_grade()
        scale = (mx / pack.total_max) if mx and pack.total_max and abs(mx - pack.total_max) > 1e-9 else 1.0
        by_pid = {sub["sub_id"]: (sub, rev, res) for sub, rev, res in grade_rows}
        matched = 0
        for row in ws.rows:
            pid = ws.pid_of(row)
            if pid in by_pid and gcol:
                sub, rev, res = by_pid[pid]
                if not res["complete"]:
                    continue                      # never write a grade for a student who is not fully graded
                row[gcol] = fmt(res["total"] * scale)
                if fcol:
                    row[fcol] = feedback_comment_text(pack, rev, res)
                matched += 1
        ws_out = out_dir / (Path(worksheet_path).stem + "_graded.csv")
        write_worksheet(ws, ws_out)
        ws_note = f"{matched} rows filled in the Moodle worksheet."
        if scale != 1.0:
            ws_note += f" Grades scaled to the Moodle maximum of {fmt(mx)}."
        if not gcol:
            ws_note += " Warning: no 'Grade' column found in the worksheet."
    # regrade requests log ---------------------------------------------------------
    regrade_csv = None
    req_rows = [(sub, req) for sub in subs for req in (reviews.get(sub["sub_id"]) or {}).get("regrade_all", [])]
    if req_rows:
        from .regrade import changes, summary
        regrade_csv = out_dir / "regrade_requests.csv"
        with open(regrade_csv, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["Participant", "Name", "Opened", "Closed", "Total before", "Total after", "Changes",
                        "Request", "Reply"])
            for sub, req in req_rows:
                stamp = lambda t: datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M") if t else ""
                w.writerow([sub["sub_id"], sub.get("name", ""), stamp(req.get("opened_at")),
                            stamp(req.get("closed_at")), fmt((req.get("before") or {}).get("total")),
                            fmt((req.get("after") or {}).get("total")) if req.get("after") else "",
                            ", ".join(changes(pack, req)) if req.get("after") else "",
                            req.get("request", ""), req.get("reply", "")])
    agreement = agreement_report(pack, subs, reviews, out_dir)
    return {"agreement": agreement, "written": written, "skipped": skipped, "zip": str(zip_path), "pdf_dir": str(pdf_dir),
            "grades_csv": str(grades_csv), "findings_csv": str(findings_csv),
            "regrade_csv": str(regrade_csv) if regrade_csv else None,
            "worksheet": str(ws_out) if ws_out else None, "worksheet_note": ws_note,
            "grades_kind": ("gradebook" if is_roster else "worksheet") if ws_out else None}


# AI-vs-TA agreement ----------------------------------------------------------

def agreement_report(pack: Pack, subs: list[dict], reviews: dict[str, dict], out_dir: Path) -> dict:
    """Compare the AI pre-screen with the TA's final decisions for reviewed students.

    'missed': the AI said nothing (green) but the TA gave 50% or less on that row.
    'false alarm': the AI said 'likely problem' (red) but the TA gave 100%.
    Integrity: share of AI findings the TA rejected, and findings the TA had to add."""
    import json as _json
    rows_out = []
    per_row = {r.id: {"n": 0, "missed": 0, "false_alarm": 0, "flagged": 0, "low_conf": 0} for r in pack.rubric}
    integ = {"ai_findings": 0, "confirmed": 0, "rejected": 0, "ta_added": 0}
    n_students = 0
    for sub in subs:
        rev = reviews.get(sub["sub_id"])
        if not rev or not rev.get("reviewed") or not sub.get("screen"):
            continue
        screen = _json.loads(sub["screen"])
        if screen.get("_meta", {}).get("model") == "offline":
            continue
        n_students += 1
        srows = {x["row_id"]: x for x in screen.get("rows", [])}
        for r in pack.rubric:
            s = srows.get(r.id, {})
            lvl = rev.get("levels", {}).get(r.id)
            st, conf = s.get("status", "gray"), s.get("confidence", "")
            verdict = ""
            if st == "green" and lvl is not None and lvl <= 50:
                verdict = "missed"
            elif st == "red" and lvl == 100:
                verdict = "false alarm"
            c = per_row[r.id]
            c["n"] += 1
            c["flagged"] += st in ("yellow", "red")
            c["low_conf"] += conf == "low"
            if verdict == "missed":
                c["missed"] += 1
            elif verdict == "false alarm":
                c["false_alarm"] += 1
            rows_out.append({"participant": sub["sub_id"], "row": r.label, "ai_status": st, "ai_confidence": conf,
                             "ta_level": lvl, "verdict": verdict, "ai_reason": s.get("reason", "")})
        for f in rev.get("findings", []):
            if f.get("origin") == "ta":
                integ["ta_added"] += 1
            elif f.get("origin") == "ai":
                integ["ai_findings"] += 1
                if f.get("decision") == "rejected":
                    integ["rejected"] += 1
                elif f.get("decision") in ("full", "half", "none"):
                    integ["confirmed"] += 1
    path = Path(out_dir) / "ai_vs_ta_agreement.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["participant", "row", "ai_status", "ai_confidence", "ta_level",
                                           "verdict", "ai_reason"])
        w.writeheader()
        w.writerows(rows_out)
    lines = [f"AI pre-screen compared with TA decisions ({n_students} reviewed students with an AI pre-screen)."]
    for r in pack.rubric:
        c = per_row[r.id]
        if c["n"]:
            lines.append(f"{r.label}: flagged {c['flagged']}/{c['n']}, missed {c['missed']}, "
                         f"false alarms {c['false_alarm']}, AI unsure {c['low_conf']}.")
    if integ["ai_findings"] or integ["ta_added"]:
        lines.append(f"Integrity: {integ['ai_findings']} AI findings, {integ['confirmed']} confirmed, "
                     f"{integ['rejected']} rejected. {integ['ta_added']} added by graders.")
    summary = "\n".join(lines)
    (Path(out_dir) / "ai_vs_ta_agreement_summary.txt").write_text(summary + "\n", encoding="utf-8")
    table = [{"label": r.label, **per_row[r.id]} for r in pack.rubric if per_row[r.id]["n"]]
    return {"csv": str(path), "summary": summary, "students": n_students, "rows": table, "integrity": integ}
