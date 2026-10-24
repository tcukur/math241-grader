"""Score arithmetic: TA-selected rubric levels, confirmed integrity findings,
row caps and capped deductions."""
from __future__ import annotations

import uuid

from .pack import Pack

DECISIONS = {
    "pending": "Pending decision",
    "rejected": "Rejected (not a real issue)",
    "full": "Confirmed: full penalty",
    "half": "Confirmed: half penalty",
    "none": "Confirmed: no penalty",
}


def new_review_from_screen(pack: Pack, screen: dict | None, reviewer: str = "") -> dict:
    findings = []
    screen = screen or {}
    offline = screen.get("_meta", {}).get("model") == "offline"
    items = [(f, "auto" if offline else "ai") for f in screen.get("integrity", [])]
    have = {f.get("category") for f, _ in items}
    # automatic findings are added for any category the AI did not report itself
    items += [(f, "auto") for f in screen.get("auto_integrity", [])
              if f.get("category") not in have or f.get("always")]
    for f, origin in items:
        findings.append({
            "uid": uuid.uuid4().hex[:10],
            "origin": origin,
            "category": f.get("category", "other"),
            "suggested_category": f.get("category", "other"),
            "summary": f.get("summary", ""),
            "ta_check": f.get("ta_check", ""),
            "affected_rows": list(f.get("affected_rows", [])),
            "evidence": f.get("evidence", []),
            "decision": "pending",
            "comment": "",
        })
    return {"levels": {r.id: None for r in pack.rubric}, "comments": {r.id: "" for r in pack.rubric},
            "findings": findings, "overall_comment": "", "reviewed": False, "reviewer": reviewer}


def compute(pack: Pack, review: dict) -> dict:
    caps: dict[str, float] = {}
    deductions = []
    for f in review.get("findings", []):
        dec = f.get("decision")
        if dec not in ("full", "half", "none"):
            continue
        cat = pack.category(f.get("category", "other"))
        if cat is None:
            continue
        factor = {"full": 1.0, "half": 0.5, "none": 0.0}[dec]
        pts = round(cat.points * factor, 2)
        if pts:
            deductions.append({"uid": f["uid"], "category": cat.id, "label": cat.label, "points": pts})
        cap = cat.row_cap_pct if dec == "full" else cat.half_row_cap_pct if dec == "half" else None
        if cap is not None:
            for rid in f.get("affected_rows", []):
                caps[rid] = min(caps.get(rid, 100.0), float(cap))

    # findings that describe the same problem (for example "AI record missing" and "given only as a link")
    # count once: only the largest deduction in each group is kept
    notes = []
    for group in pack.exclusive_groups:
        inside = [d for d in deductions if d["category"] in group]
        if len(inside) > 1:
            keep = max(inside, key=lambda d: d["points"])
            for d in inside:
                if d is not keep:
                    d["points"] = 0.0
                    d["overlap"] = keep["label"]
            notes.append(f"Counted once: {', '.join(x['label'] for x in inside)} describe the same problem.")

    rows = []
    rubric_total = 0.0
    for r in pack.rubric:
        level = review.get("levels", {}).get(r.id)
        raw = None if level is None else r.max * level / 100.0
        cap = caps.get(r.id)
        score = raw
        capped = False
        if raw is not None and cap is not None and raw > r.max * cap / 100.0:
            score = r.max * cap / 100.0
            capped = True
        rows.append({"id": r.id, "label": r.label, "group": r.group, "max": r.max, "level": level,
                     "raw": raw, "cap_pct": cap, "capped": capped, "score": score})
        rubric_total += score or 0.0

    ded_sum = sum(d["points"] for d in deductions)
    cap_total = pack.integrity_cap
    ded_total = min(ded_sum, cap_total) if cap_total else ded_sum
    total = max(0.0, rubric_total - ded_total)
    return {"rows": rows, "deductions": deductions, "deduction_sum": ded_sum, "deduction_total": ded_total,
            "rubric_total": rubric_total, "total": total, "max": pack.total_max, "notes": notes,
            "complete": all(x["level"] is not None for x in rows)}


def readiness_problems(pack: Pack, review: dict) -> list[str]:
    probs = []
    for r in pack.rubric:
        if review.get("levels", {}).get(r.id) is None:
            probs.append(f"Choose a level for \"{r.label}\".")
    for f in review.get("findings", []):
        cat = pack.category(f.get("category"))
        name = cat.label if cat else f.get("category")
        if f.get("decision", "pending") == "pending":
            probs.append(f"Decide on the finding \"{name}\".")
        elif f.get("decision") in ("half", "none") and not f.get("comment", "").strip():
            probs.append(f"Add a comment explaining the reduced penalty for \"{name}\".")
        if (f.get("decision") in ("full", "half") and cat and cat.row_cap_pct is not None
                and not f.get("affected_rows")):
            probs.append(f"Select the affected rubric rows for \"{name}\".")
    return probs


def fmt(x: float | None) -> str:
    if x is None:
        return "-"
    return f"{x:.2f}".rstrip("0").rstrip(".")
