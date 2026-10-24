"""Regrade requests after grades were released.

Each request is kept in the workspace settings under 'regrade:<student>' with what the student asked, the
grade before, the grader's reply and the grade after. Opening a request takes the student out of 'reviewed'
until the grader has looked again and written a reply."""
from __future__ import annotations

import time
import uuid

from .scoring import compute, fmt


def _key(sid: str) -> str:
    return f"regrade:{sid}"


def requests(store, sid: str) -> list[dict]:
    v = store.get_meta_raw(_key(sid))
    return list(v.get("requests", [])) if isinstance(v, dict) else []


def _save(store, sid: str, reqs: list[dict]) -> None:
    store.set_meta(_key(sid), {"requests": reqs} if reqs else None)


def open_request(store, sid: str) -> dict | None:
    return next((r for r in requests(store, sid) if not r.get("closed_at")), None)


def _snapshot(pack, review: dict) -> dict:
    res = compute(pack, review)
    return {"total": res["total"], "rows": {r["id"]: r["score"] for r in res["rows"]},
            "deductions": res["deduction_total"]}


def start(store, pack, sid: str, text: str) -> dict:
    rev = store.review(sid) or {}
    req = {"id": uuid.uuid4().hex[:8], "opened_at": time.time(), "request": text.strip(), "reply": "",
           "before": _snapshot(pack, rev)}
    _save(store, sid, requests(store, sid) + [req])
    if rev:
        rev["reviewed"] = False
        store.save_review(sid, rev)
    return req


def set_reply(store, sid: str, text: str) -> None:
    reqs = requests(store, sid)
    for r in reqs:
        if not r.get("closed_at"):
            r["reply"] = text
    _save(store, sid, reqs)


def close(store, pack, sid: str) -> dict | None:
    reqs = requests(store, sid)
    cur = next((r for r in reqs if not r.get("closed_at")), None)
    if cur is None:
        return None
    cur["closed_at"] = time.time()
    cur["after"] = _snapshot(pack, store.review(sid) or {})
    _save(store, sid, reqs)
    return cur


def cancel(store, sid: str) -> None:
    """Withdraw the open request, as if it had not been made."""
    _save(store, sid, [r for r in requests(store, sid) if r.get("closed_at")])


def mark_exported(store, sid: str) -> None:
    reqs = requests(store, sid)
    changed = False
    for r in reqs:
        if r.get("closed_at") and not r.get("exported_at"):
            r["exported_at"] = time.time()
            changed = True
    if changed:
        _save(store, sid, reqs)


def not_exported(store, sid: str) -> bool:
    return any(r.get("closed_at") and not r.get("exported_at") for r in requests(store, sid))


def changes(pack, req: dict) -> list[str]:
    """What changed between before and after, item by item."""
    b, a = req.get("before") or {}, req.get("after") or {}
    out = []
    for row in pack.rubric:
        x, y = (b.get("rows") or {}).get(row.id), (a.get("rows") or {}).get(row.id)
        if x != y:
            out.append(f"{row.label}: {fmt(x) if x is not None else '?'} → {fmt(y) if y is not None else '?'}")
    if (b.get("deductions") or 0) != (a.get("deductions") or 0):
        out.append(f"Integrity deductions: {fmt(b.get('deductions') or 0)} → {fmt(a.get('deductions') or 0)}")
    return out


def summary(pack, req: dict) -> str:
    b = (req.get("before") or {}).get("total")
    a = (req.get("after") or {}).get("total")
    if a is None:
        return f"Total before the request: {fmt(b)}." if b is not None else ""
    if b == a:
        return f"Total unchanged at {fmt(a)}."
    return f"Total changed from {fmt(b)} to {fmt(a)}."
