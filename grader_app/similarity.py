"""Similar work: find pairs of submissions that share long stretches of identical text.

Everything runs on this computer and nothing is sent to the AI. Each PDF is read word by word, with hidden text
removed. Two submissions match where they share a run of SHINGLE consecutive words (letters and numbers only,
case and punctuation ignored). Matches are not counted when the words also appear in the handout, or when
they are shared by many students (common phrasing, standard code, the usual way of asking an AI assistant).

Only pairs with a lot of shared text are reported, so the list stays short. For each pair the shared passages
are listed with their pages and the exact word positions in both PDFs, for side-by-side inspection."""
from __future__ import annotations

import itertools
import json
import math
import re
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

SHINGLE = 10                 # words in a row that must match
MIN_SHARED_WORDS = 250       # a pair is reported with at least this many shared words...
MIN_LONGEST = 100            # ...or one passage at least this long
# Words are counted without numbers: identical result tables are expected when students get the right answer.
# On 14 independent real submissions the largest overlap was 137 words in total and 47 in one passage, mostly
# standard proof phrasing, so these limits leave ordinary agreement out.
MAX_PAIRS = 15
MAX_RECTS = 600              # highlight areas kept per passage side
_TOKEN = re.compile(r"[0-9a-z]+")


def _norm(word: str) -> list[str]:
    w = unicodedata.normalize("NFKC", word).casefold()
    return _TOKEN.findall(w)


def read_tokens(pdf_path: str | Path) -> dict:
    """{'tokens': [...], 'where': [(page, (x0, y0, x1, y1)), ...]} with one entry per word piece."""
    import pymupdf
    from .hidden import strip_hidden
    tokens, where, wid, words = [], [], [], []
    with pymupdf.open(stream=Path(pdf_path).read_bytes(), filetype="pdf") as doc:
        try:
            strip_hidden(doc)
        except Exception:  # noqa: BLE001
            pass
        for pno, page in enumerate(doc, 1):
            for w in page.get_text("words", sort=True):
                pieces = _norm(w[4])
                if pieces:
                    words.append(w[4])          # the word as printed, for previews
                for t in pieces:
                    tokens.append(t)
                    wid.append(len(words) - 1)
                    where.append((pno, (round(w[0], 1), round(w[1], 1), round(w[2], 1), round(w[3], 1))))
    return {"tokens": tokens, "where": where, "wid": wid, "words": words}


def _shingles(tokens: list[str]) -> dict[int, list[int]]:
    out = defaultdict(list)
    for i in range(len(tokens) - SHINGLE + 1):
        out[hash(tuple(tokens[i:i + SHINGLE]))].append(i)
    return out


def handout_shingles(paths: list[Path]) -> set[int]:
    excl = set()
    for p in paths:
        try:
            if p.suffix.lower() == ".pdf":
                toks = read_tokens(p)["tokens"]
            else:
                toks = [t for w in p.read_text(errors="ignore").split() for t in _norm(w)]
            excl |= set(_shingles(toks))
        except Exception:  # noqa: BLE001
            continue
    return excl


def _sections(row) -> dict[int, str]:
    try:
        ext = json.loads(row["extraction"] or "{}")
        return {p["number"]: p["section"] for p in ext.get("pages", [])}
    except Exception:  # noqa: BLE001
        return {}


SECTION_NAMES = {"report": "Report", "chat": "AI record", "code": "Code"}


def section_name(s: str) -> str:
    parts = [SECTION_NAMES.get(x, x) for x in (s or "report").split("+")]
    return " and ".join(dict.fromkeys(parts))


def compare(students: list[dict], handout: set[int], progress=None) -> dict:
    """students: [{'sid', 'name', 'tokens', 'where', 'sections'}]. Returns the report."""
    n = len(students)
    common_limit = max(3, math.ceil(0.10 * n))       # shared by more students than this: common material
    sh = [_shingles(s["tokens"]) for s in students]
    index: dict[int, list[int]] = defaultdict(list)
    for k, d in enumerate(sh):
        for h in d:
            if h not in handout:
                index[h].append(k)
    pair_count: dict[tuple[int, int], int] = defaultdict(int)
    for h, who in index.items():
        if 2 <= len(who) <= common_limit:
            for a, b in itertools.combinations(who, 2):
                pair_count[(a, b)] += 1
    common = {h for h, who in index.items() if len(who) > common_limit} | handout

    pairs = []
    candidates = [p for p, c in pair_count.items() if c >= 20]
    for j, (a, b) in enumerate(candidates):
        if progress:
            progress(j + 1, len(candidates))
        rep = _pair(students[a], students[b], sh[a], sh[b], common)
        if rep and (rep["shared_words"] >= MIN_SHARED_WORDS or rep["longest"] >= MIN_LONGEST):
            pairs.append(rep)
    pairs.sort(key=lambda r: -r["shared_words"])
    total_pairs = n * (n - 1) // 2
    return {"at": time.time(), "students": n, "pairs_compared": total_pairs, "found": len(pairs),
            "pairs": pairs[:MAX_PAIRS], "shingle": SHINGLE, "common_limit": common_limit}


def _cluster(starts: list[int]) -> tuple[int, int] | None:
    if not starts:
        return None
    starts = sorted(starts)
    groups, cur = [], [starts[0]]
    for x in starts[1:]:
        if x - cur[-1] > 40:
            groups.append(cur)
            cur = [x]
        else:
            cur.append(x)
    groups.append(cur)
    best = max(groups, key=len)
    return best[0], best[-1] + SHINGLE - 1


def _pair(A, B, sa, sb, common) -> dict | None:
    shared = (set(sa) & set(sb)) - common
    if not shared:
        return None
    covered = [False] * len(A["tokens"])
    for h in shared:
        for p in sa[h]:
            for q in range(p, min(p + SHINGLE, len(covered))):
                covered[q] = True
    runs, i = [], 0
    while i < len(covered):
        if covered[i]:
            j = i
            while j + 1 < len(covered) and (covered[j + 1] or any(covered[j + 1:j + 5])):
                j += 1
            while not covered[j]:
                j -= 1
            runs.append((i, j))
            i = j + 1
        else:
            i += 1
    # one passage per page of A, so long copies can be walked through page by page
    chunks = []
    for s, e in runs:
        start = s
        for k in range(s + 1, e + 1):
            if A["where"][k][0] != A["where"][start][0]:
                chunks.append((start, k - 1))
                start = k
        chunks.append((start, e))
    passages = []
    for s, e in chunks:
        hs = {hash(tuple(A["tokens"][p:p + SHINGLE])) for p in range(max(0, s - SHINGLE + 1), e + 1)}
        bstarts = [q for h in hs & shared for q in sb.get(h, [])]
        span = _cluster(bstarts)
        if span is None:
            continue
        bs, be = span
        words = sum(1 for k in range(s, e + 1) if covered[k] and not A["tokens"][k].isdigit())
        if words < 15:
            continue
        passages.append(_passage(A, B, s, e, bs, be, words))
    if not passages:
        return None
    shared_words = sum(p["words"] for p in passages)
    by_section = defaultdict(int)
    for p in passages:
        by_section[p["section"]] += p["words"]
    shorter = max(1, min(len(A["tokens"]), len(B["tokens"])))
    passages.sort(key=lambda p: (p["a_page"], p["a_start"]))
    return {"a": A["sid"], "b": B["sid"], "a_name": A["name"], "b_name": B["name"],
            "shared_words": shared_words, "share": round(shared_words / shorter, 3),
            "longest": max(p["words"] for p in passages), "by_section": dict(by_section),
            "passages": passages}


def _rects(S, s, e):
    out = defaultdict(list)
    for k in range(s, min(e + 1, len(S["where"]))):
        page, r = S["where"][k]
        if not out[page] or out[page][-1] != list(r):
            out[page].append(list(r))
    total = 0
    trimmed = {}
    for p, rs in out.items():
        keep = rs[:max(0, MAX_RECTS - total)]
        total += len(keep)
        if keep:
            trimmed[str(p)] = keep
    return trimmed


def _passage(A, B, s, e, bs, be, words) -> dict:
    from collections import Counter
    a_page = Counter(A["where"][k][0] for k in range(s, e + 1)).most_common(1)[0][0]
    b_page = Counter(B["where"][k][0] for k in range(bs, min(be + 1, len(B["where"])))).most_common(1)[0][0]
    sec_a = A["sections"].get(a_page, "report")
    sec_b = B["sections"].get(b_page, "report")
    if A.get("wid"):
        ids = list(dict.fromkeys(A["wid"][s:e + 1]))
        text = " ".join(A["words"][i] for i in ids)
        # some PDFs store code letter by letter ("n u m p y"): show it as one word again
        text = re.sub(r"(?<!\S)(?:\S ){3,}\S(?!\S)", lambda m: m.group(0).replace(" ", ""), text)
    else:
        text = " ".join(A["tokens"][s:e + 1])
    return {"a_start": s, "a_end": e, "b_start": bs, "b_end": be, "a_page": a_page, "b_page": b_page,
            "a_last": A["where"][e][0], "b_last": B["where"][min(be, len(B["where"]) - 1)][0],
            "section": section_name(sec_a), "b_section": section_name(sec_b), "words": words,
            "preview": text[:260] + ("…" if len(text) > 260 else ""),
            "a_rects": _rects(A, s, e), "b_rects": _rects(B, bs, be)}


_TOKEN_CACHE: dict = {}       # (file, size, modified) -> words, kept while the app runs


def signature(store) -> str:
    """Which submissions, in which version: the check only needs to run again when this changes."""
    import hashlib
    parts = sorted(f"{r['sub_id']}:{r['pdf_hash'] or ''}" for r in store.submissions())
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


def _tokens_cached(path: str) -> dict:
    p = Path(path)
    st = p.stat()
    key = (str(p), st.st_size, st.st_mtime)
    if key not in _TOKEN_CACHE:
        _TOKEN_CACHE[key] = read_tokens(p)
    return _TOKEN_CACHE[key]


def run(store, pack, workspace: Path, progress=None) -> dict:
    """Read every submission and compare. progress(stage, i, n)."""
    sig = signature(store)
    rows = [r for r in store.submissions() if r["pdf_path"] and Path(r["pdf_path"]).exists()]
    students = []
    for k, r in enumerate(rows, 1):
        if progress:
            progress("read", k, len(rows))
        try:
            t = _tokens_cached(r["pdf_path"])
        except Exception:  # noqa: BLE001
            continue
        students.append({"sid": r["sub_id"], "name": r["name"] or r["sub_id"], "sections": _sections(r), **t})
    handout_files = []
    files = (pack.data.get("files") or {}) if pack else {}
    if files.get("assignment"):
        handout_files.append(Path(pack.folder) / files["assignment"])
    for extra in (files.get("starter_code") or []) if isinstance(files.get("starter_code"), list) else []:
        handout_files.append(Path(pack.folder) / extra)
    handout = handout_shingles([p for p in handout_files if p.exists()])
    rep = compare(students, handout, progress=(lambda i, n: progress("compare", i, n)) if progress else None)
    rep["signature"] = sig
    return rep


# report kept in the workspace, and the findings made from it ---------------------------------------------------
REPORT_KEY = "similarity_report"


def pair_key(p: dict) -> str:
    return "|".join(sorted((p["a"], p["b"])))


def swap(p: dict) -> dict:
    """The same pair seen from the other student."""
    q = dict(p)
    q["a"], q["b"], q["a_name"], q["b_name"] = p["b"], p["a"], p["b_name"], p["a_name"]
    q["passages"] = []
    for x in p["passages"]:
        y = dict(x)
        for f in ("start", "end", "page", "last", "rects"):
            y[f"a_{f}"], y[f"b_{f}"] = x[f"b_{f}"], x[f"a_{f}"]
        y["section"], y["b_section"] = x["b_section"], x["section"]
        q["passages"].append(y)
    q["passages"].sort(key=lambda r: (r["a_page"], r["a_start"]))
    q["by_section"] = {}
    for y in q["passages"]:
        q["by_section"][y["section"]] = q["by_section"].get(y["section"], 0) + y["words"]
    return q


def find_pair(report: dict, key: str) -> dict | None:
    return next((p for p in (report or {}).get("pairs", []) if pair_key(p) == key), None)


def add_findings(store, pack, report: dict, reviewer: str = "") -> int:
    """Give both students of every flagged pair an integrity finding to decide, unless they already have one for
    that pair. Returns how many findings were added."""
    import uuid
    from .scoring import new_review_from_screen
    cat = next((c for c in pack.categories if c.id == "other"), pack.categories[-1] if pack.categories else None)
    added = 0
    for p in (report or {}).get("pairs", []):
        key = pair_key(p)
        for me in (p["a"], p["b"]):
            view = p if me == p["a"] else swap(p)
            rev = store.review(me)
            if rev is None:
                row = store.submission(me)
                screen = json.loads(row["screen"]) if row and row["screen"] else None
                rev = new_review_from_screen(pack, screen, reviewer)
            if any(f.get("similar_pair") == key for f in rev.get("findings", [])):
                continue
            pages = sorted({q["a_page"] for q in view["passages"]})
            top = sorted(view["by_section"].items(), key=lambda x: -x[1])
            rev.setdefault("findings", []).append({
                "uid": uuid.uuid4().hex[:10], "origin": "auto", "category": cat.id if cat else "other",
                "suggested_category": cat.id if cat else "other", "similar_pair": key,
                "summary": (f"Similar work: shares {view['shared_words']:,} words in {len(view['passages'])} "
                            f"passages with {view['b_name']} ({view['b']}), mostly {top[0][0] if top else 'text'}, "
                            f"on pages {', '.join(map(str, pages[:12]))} of this paper."),
                "ta_check": ("Press Compare side by side and go through the shared passages. Reject the finding "
                             "if the overlap is ordinary, such as standard definitions or short standard code. "
                             "Decide the same way for the other student."),
                "affected_rows": [], "evidence": [{"page": q["a_page"], "excerpt": ""} for q in
                                                  sorted(view["passages"], key=lambda q: -q["words"])[:3]],
                "decision": "pending", "comment": ""})
            rev["reviewed"] = False
            store.save_review(me, rev)
            added += 1
    return added
