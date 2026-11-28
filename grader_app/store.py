"""SQLite store kept in the grading workspace. Every result is written as soon
as it exists, so an interrupted run resumes where it stopped."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS submissions (
    sub_id TEXT PRIMARY KEY,
    name TEXT,
    layout TEXT,
    moodle_prefix TEXT,
    pdf_path TEXT,
    pdf_hash TEXT,
    status TEXT DEFAULT 'new',          -- new, extracted, screened, error
    error TEXT,
    extraction TEXT,
    checks TEXT,
    screen TEXT,
    screened_at REAL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    note TEXT
);
CREATE TABLE IF NOT EXISTS reviews (
    sub_id TEXT PRIMARY KEY,
    levels TEXT,             -- {row_id: level or null}
    comments TEXT,           -- {row_id: str}
    findings TEXT,           -- list of finding dicts with TA decisions
    overall_comment TEXT,
    reviewed INTEGER DEFAULT 0,
    reviewer TEXT,
    updated_at REAL
);
"""


PATH_META = ("pack_path", "worksheet_path", "submissions_path")


class Store:
    """The workspace database. Paths to files inside the workspace folder are stored relative to it,
    so the folder can be moved, renamed or opened on another computer (Mac or Windows)."""

    def __init__(self, db_path: str | Path):
        self.path = str(db_path)
        self.root = Path(db_path).resolve().parent
        self._lock = threading.Lock()
        self._local = threading.local()
        with self.conn() as c:
            c.executescript(SCHEMA)
            cols = {r["name"] for r in c.execute("PRAGMA table_info(submissions)")}
            for col, typ in (("ta_note", "TEXT"), ("prompt_text", "TEXT"), ("raw_response", "TEXT"),
                             ("info", "TEXT"), ("rerun_model", "TEXT"), ("rerun_requested", "REAL")):
                if col not in cols:
                    c.execute(f"ALTER TABLE submissions ADD COLUMN {col} {typ}")

    def conn(self) -> sqlite3.Connection:
        con = getattr(self._local, "con", None)
        if con is None:
            con = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
            con.row_factory = sqlite3.Row
            # rollback journal instead of WAL: no -wal/-shm side files, so the folder can be moved,
            # copied or synced (Google Drive, Dropbox) safely whenever the app is closed
            con.execute("PRAGMA journal_mode=DELETE")
            self._local.con = con
        return con

    # paths ------------------------------------------------------------------
    def abs(self, p) -> str:
        """Stored path -> real path on this computer."""
        if not p:
            return p
        s = str(p)
        if s.startswith("ws:"):
            return str(self.root.joinpath(*s[3:].split("/")))
        return s

    def rel(self, p) -> str:
        """Real path -> stored form ('ws:submissions/123.pdf' for files inside the workspace)."""
        if not p:
            return p
        try:
            r = Path(p).resolve().relative_to(self.root)
            return "ws:" + "/".join(r.parts)
        except (ValueError, OSError):
            return str(p)

    def inside(self, p) -> bool:
        return bool(p) and str(p).startswith("ws:")

    # meta -------------------------------------------------------------------
    def get_meta(self, key: str, default=None):
        r = self.conn().execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        val = json.loads(r["value"]) if r else default
        return self.abs(val) if key in PATH_META and isinstance(val, str) else val

    def get_meta_raw(self, key: str, default=None):
        r = self.conn().execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(r["value"]) if r else default

    def set_meta(self, key: str, value) -> None:
        if key in PATH_META and isinstance(value, str):
            value = self.rel(value)
        with self._lock, self.conn() as c:
            c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)", (key, json.dumps(value)))

    # submissions -------------------------------------------------------------
    def upsert_found(self, sub_id, name, layout, prefix, pdf_path, pdf_hash, note="") -> str:
        """Register a submission. Returns 'new', 'changed' or 'same'."""
        with self._lock, self.conn() as c:
            r = c.execute("SELECT pdf_hash FROM submissions WHERE sub_id=?", (sub_id,)).fetchone()
            if r is None:
                c.execute("INSERT INTO submissions(sub_id, name, layout, moodle_prefix, pdf_path, pdf_hash, note)"
                          " VALUES(?,?,?,?,?,?,?)", (sub_id, name, layout, prefix, self.rel(pdf_path), pdf_hash, note))
                return "new"
            if r["pdf_hash"] != pdf_hash:
                c.execute("UPDATE submissions SET name=?, layout=?, moodle_prefix=?, pdf_path=?, pdf_hash=?,"
                          " status='new', error=NULL, extraction=NULL, checks=NULL, screen=NULL, note=?"
                          " WHERE sub_id=?", (name, layout, prefix, self.rel(pdf_path), pdf_hash, note, sub_id))
                return "changed"
            c.execute("UPDATE submissions SET name=?, layout=?, moodle_prefix=?, pdf_path=?, note=? WHERE sub_id=?",
                      (name, layout, prefix, self.rel(pdf_path), note, sub_id))
            return "same"

    def _row(self, r):
        if r is None:
            return None
        d = dict(r)
        d["pdf_path_stored"] = d.get("pdf_path")
        d["pdf_path"] = self.abs(d.get("pdf_path"))
        return d

    def submissions(self) -> list[dict]:
        rows = self.conn().execute("SELECT * FROM submissions").fetchall()
        from .names import sort_key
        return sorted((self._row(r) for r in rows), key=lambda r: (sort_key(r["name"] or r["sub_id"]), r["sub_id"]))

    def submission(self, sub_id: str) -> dict | None:
        return self._row(self.conn().execute("SELECT * FROM submissions WHERE sub_id=?", (sub_id,)).fetchone())

    def set_pdf_path(self, sub_id: str, path) -> None:
        with self._lock, self.conn() as c:
            c.execute("UPDATE submissions SET pdf_path=? WHERE sub_id=?", (self.rel(path), sub_id))

    def save_extraction(self, sub_id, extraction: dict, checks: list[dict], name_if_empty: str = ""):
        with self._lock, self.conn() as c:
            c.execute("UPDATE submissions SET extraction=?, checks=?, status='extracted', error=NULL,"
                      " name=CASE WHEN name IS NULL OR name='' THEN ? ELSE name END WHERE sub_id=?",
                      (json.dumps(extraction), json.dumps(checks), name_if_empty, sub_id))

    def save_screen(self, sub_id, screen: dict):
        meta = screen.get("_meta", {})
        with self._lock, self.conn() as c:
            c.execute("UPDATE submissions SET screen=?, status='screened', error=NULL, screened_at=?,"
                      " input_tokens=?, output_tokens=? WHERE sub_id=?",
                      (json.dumps(screen), time.time(), meta.get("input_tokens"), meta.get("output_tokens"), sub_id))

    def save_prompt(self, sub_id, prompt_text: str, raw_response: str | None):
        with self._lock, self.conn() as c:
            c.execute("UPDATE submissions SET prompt_text=?, raw_response=? WHERE sub_id=?",
                      (prompt_text, raw_response, sub_id))

    def set_info(self, sub_id, info: dict):
        with self._lock, self.conn() as c:
            c.execute("UPDATE submissions SET info=? WHERE sub_id=?", (json.dumps(info), sub_id))

    def request_rerun(self, sub_id, model: str | None, note: str):
        with self._lock, self.conn() as c:
            c.execute("UPDATE submissions SET rerun_model=?, rerun_requested=?, ta_note=? WHERE sub_id=?",
                      (model or None, time.time(), note, sub_id))

    def clear_rerun_request(self, sub_id):
        with self._lock, self.conn() as c:
            c.execute("UPDATE submissions SET rerun_model=NULL, rerun_requested=NULL WHERE sub_id=?", (sub_id,))

    def set_ta_note(self, sub_id, note: str):
        with self._lock, self.conn() as c:
            c.execute("UPDATE submissions SET ta_note=? WHERE sub_id=?", (note, sub_id))

    def save_error(self, sub_id, msg: str):
        with self._lock, self.conn() as c:
            c.execute("UPDATE submissions SET status='error', error=? WHERE sub_id=?", (msg[:2000], sub_id))

    def reset_screen(self, sub_id):
        with self._lock, self.conn() as c:
            c.execute("UPDATE submissions SET screen=NULL, status=CASE WHEN extraction IS NULL THEN 'new'"
                      " ELSE 'extracted' END WHERE sub_id=?", (sub_id,))

    # reviews -----------------------------------------------------------------
    def review(self, sub_id: str) -> dict | None:
        r = self.conn().execute("SELECT * FROM reviews WHERE sub_id=?", (sub_id,)).fetchone()
        if not r:
            return None
        return {"levels": json.loads(r["levels"] or "{}"), "comments": json.loads(r["comments"] or "{}"),
                "findings": json.loads(r["findings"] or "[]"), "overall_comment": r["overall_comment"] or "",
                "reviewed": bool(r["reviewed"]), "reviewer": r["reviewer"] or "", "updated_at": r["updated_at"]}

    def save_review(self, sub_id: str, review: dict):
        with self._lock, self.conn() as c:
            c.execute("INSERT OR REPLACE INTO reviews(sub_id, levels, comments, findings, overall_comment,"
                      " reviewed, reviewer, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                      (sub_id, json.dumps(review.get("levels", {})), json.dumps(review.get("comments", {})),
                       json.dumps(review.get("findings", [])), review.get("overall_comment", ""),
                       int(bool(review.get("reviewed"))), review.get("reviewer", ""), time.time()))

    COPY_COLS = ("name", "layout", "moodle_prefix", "pdf_hash", "status", "error", "extraction", "checks",
                 "screen", "screened_at", "input_tokens", "output_tokens", "note", "ta_note", "prompt_text",
                 "raw_response", "info", "rerun_model", "rerun_requested")

    def put_row(self, sub_id: str, pdf_path: str, values: dict):
        """Insert or overwrite a submission row from a package."""
        cols = [c for c in self.COPY_COLS if c in values]
        with self._lock, self.conn() as c:
            if c.execute("SELECT 1 FROM submissions WHERE sub_id=?", (sub_id,)).fetchone() is None:
                c.execute("INSERT INTO submissions(sub_id, pdf_path) VALUES(?, ?)", (sub_id, self.rel(pdf_path)))
            elif pdf_path:
                c.execute("UPDATE submissions SET pdf_path=? WHERE sub_id=?", (self.rel(pdf_path), sub_id))
            if cols:
                c.execute(f"UPDATE submissions SET {', '.join(f'{k}=?' for k in cols)} WHERE sub_id=?",
                          [values[k] for k in cols] + [sub_id])

    def put_review_raw(self, sub_id: str, row: dict):
        with self._lock, self.conn() as c:
            c.execute("INSERT OR REPLACE INTO reviews(sub_id, levels, comments, findings, overall_comment,"
                      " reviewed, reviewer, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                      (sub_id, row["levels"], row["comments"], row["findings"], row["overall_comment"],
                       row["reviewed"], row["reviewer"], row["updated_at"]))

    def review_raw(self, sub_id: str) -> dict | None:
        r = self.conn().execute("SELECT * FROM reviews WHERE sub_id=?", (sub_id,)).fetchone()
        return dict(r) if r else None

    def counts(self) -> dict:
        c = self.conn()
        out = {r["status"]: r["n"] for r in c.execute("SELECT status, COUNT(*) n FROM submissions GROUP BY status")}
        out["total"] = sum(v for k, v in out.items())
        out["reviewed"] = c.execute("SELECT COUNT(*) FROM reviews WHERE reviewed=1").fetchone()[0]
        out["rerun_requests"] = c.execute("SELECT COUNT(*) FROM submissions WHERE rerun_requested IS NOT NULL"
                                          ).fetchone()[0]
        tok = c.execute("SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0) FROM submissions").fetchone()
        out["input_tokens"], out["output_tokens"] = tok[0], tok[1]
        return out
