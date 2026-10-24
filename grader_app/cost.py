"""What an AI pre-screen costs: spent so far and an estimate before a run.

Prices are per million tokens. The defaults are OpenAI's list prices as published in October 2026; an
assignment can override them in pack.json under model.prices, as {"model-name": {"in": 0.10, "out": 0.50}}.
Repeated material billed at the lower cached rate is counted at the full input price, so the figures err on
the high side."""
from __future__ import annotations

import json

DEFAULT_PRICES = {
    "gpt-6-luna": {"in": 0.10, "out": 0.50},
    "gpt-6-sol": {"in": 2.00, "out": 10.00},
}
# a first guess per student before anything has been screened, from earlier runs of this assignment
GUESS_IN, GUESS_OUT = 25000, 6000


def prices(pack) -> dict:
    p = {k: dict(v) for k, v in DEFAULT_PRICES.items()}
    for k, v in ((pack.model or {}).get("prices") or {}).items():
        if isinstance(v, dict) and "in" in v and "out" in v:
            p[k] = {"in": float(v["in"]), "out": float(v["out"])}
    return p


def price_of(pack, model: str, tin: float, tout: float) -> float | None:
    pr = prices(pack).get(model or "")
    if not pr:
        return None
    return (tin * pr["in"] + tout * pr["out"]) / 1e6


def _ai_rows(store):
    for r in store.submissions():
        try:
            meta = json.loads(r["screen"] or "{}").get("_meta", {})
        except (ValueError, TypeError):
            meta = {}
        if r["status"] == "screened" and meta.get("model") not in (None, "offline") and (r["input_tokens"] or 0) > 50:
            yield r, meta


def spent(store, pack) -> float | None:
    """Cost of the AI results currently in the workspace (earlier runs that were replaced are not counted)."""
    total, any_known = 0.0, False
    for r, meta in _ai_rows(store):
        c = price_of(pack, meta.get("model"), r["input_tokens"] or 0, r["output_tokens"] or 0)
        if c is not None:
            total += c
            any_known = True
    return total if any_known else None


def pending_for_ai(store) -> list[dict]:
    """The students Start would send to the AI (same rule as the batch runner)."""
    out = []
    for r in store.submissions():
        if r["rerun_requested"]:
            out.append(r)
            continue
        if r["status"] == "screened":
            meta = json.loads(r["screen"] or "{}").get("_meta", {})
            if meta.get("model") != "offline":
                continue
        out.append(r)
    return out


def per_student(store, pack, model: str | None = None, effort: str | None = None) -> dict:
    """Average tokens per student, from students already screened with the AI when there are any. With an
    effort level, students done at that level are used when there are any, since higher effort means more
    (billed) thinking."""
    model = model or (pack.model or {}).get("name", "gpt-6-luna")
    rows = list(_ai_rows(store))
    if effort:
        same = [(r, m) for r, m in rows if m.get("effort", (pack.model or {}).get("reasoning_effort")) == effort]
        if same:
            rows = same
    if rows:
        tin = sum(r["input_tokens"] or 0 for r, _ in rows) / len(rows)
        tout = sum(r["output_tokens"] or 0 for r, _ in rows) / len(rows)
        basis = len(rows)
    else:
        tin, tout, basis = GUESS_IN, GUESS_OUT, 0
    return {"model": model, "in": tin, "out": tout, "basis": basis, "cost": price_of(pack, model, tin, tout)}


def estimate_run(store, pack, model: str | None = None, ids: list[str] | None = None,
                 effort: str | None = None) -> dict:
    todo = pending_for_ai(store) if ids is None else [r for r in store.submissions() if r["sub_id"] in set(ids)]
    default = model or (pack.model or {}).get("name", "gpt-6-luna")
    each = per_student(store, pack, default, effort)
    total, unknown = 0.0, 0
    for r in todo:
        m = r["rerun_model"] or default
        c = price_of(pack, m, each["in"], each["out"])
        if c is None:
            unknown += 1
        else:
            total += c
    return {"n": len(todo), "cost": total if len(todo) > unknown else None, "basis": each["basis"],
            "model": default, "unknown": unknown}


def money(x: float | None) -> str:
    """'about $0.42', or 'less than $0.01'."""
    if x is None:
        return "unknown"
    if x < 0.01:
        return "less than $0.01"
    if x < 10:
        return f"about ${x:.2f}"
    return f"about ${x:,.0f}"
