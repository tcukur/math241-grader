"""Comment bank: comments already written for other students, offered again for the same rubric item or the
same kind of finding.

Nothing is stored separately. The bank is read from the grading itself each time a student is opened, so it
always matches what is in the workspace, survives a restore and needs no upkeep. Only the comments the grader
chose to remove from the list are remembered, in the workspace's settings."""
from __future__ import annotations

import json
import re
from collections import Counter

HIDDEN_KEY = "comment_bank_hidden"


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


def build_bank(store, exclude_sid: str | None = None) -> dict[str, list[tuple[str, int]]]:
    """{key: [(comment, times used), ...]} most used first. Keys are rubric item ids, 'finding:<category>' and
    'overall'."""
    counts: dict[str, Counter] = {}
    spelling: dict[tuple[str, str], Counter] = {}

    def add(key, text):
        t = re.sub(r"\s+", " ", (text or "").strip())
        if len(t) < 3:
            return
        n = norm(t)
        counts.setdefault(key, Counter())[n] += 1
        spelling.setdefault((key, n), Counter())[t] += 1

    rows = store.conn().execute("SELECT sub_id, comments, findings, overall_comment FROM reviews").fetchall()
    for r in rows:
        if r["sub_id"] == exclude_sid:
            continue
        try:
            for rid, c in (json.loads(r["comments"] or "{}") or {}).items():
                add(rid, c)
            for f in json.loads(r["findings"] or "[]") or []:
                if f.get("decision") in ("half", "none", "full", "rejected"):
                    add(f"finding:{f.get('category')}", f.get("comment", ""))
        except (ValueError, TypeError):
            continue
        add("overall", r["overall_comment"])
    hidden = hidden_map(store)
    out = {}
    for key, c in counts.items():
        gone = set(hidden.get(key, []))
        out[key] = [(spelling[(key, n)].most_common(1)[0][0], k) for n, k in c.most_common() if n not in gone]
    return out


def hidden_map(store) -> dict[str, list[str]]:
    try:
        v = store.get_meta_raw(HIDDEN_KEY)
        return v if isinstance(v, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def hide(store, key: str, text: str) -> None:
    h = hidden_map(store)
    h.setdefault(key, [])
    if norm(text) not in h[key]:
        h[key].append(norm(text))
    store.set_meta(HIDDEN_KEY, h)


def insert_text(current: str, text: str) -> str:
    """Add a saved comment to what is already typed, without doubling it."""
    cur = (current or "").rstrip()
    if not cur:
        return text
    if norm(text) in norm(cur):
        return current
    return cur + ("" if cur.endswith((".", "!", "?")) else ".") + " " + text
