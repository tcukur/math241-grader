"""Backups of the grading database.

All grading lives in <workspace>/grading.db. Copies are kept in <workspace>/backups/ as
grading_YYYY-MM-DD_HHMMSS[_reason].db, made with SQLite's own backup function, so a copy is always complete and
consistent even while the app is writing. The student PDFs, the assignment and the class list are copies that
never change, so the database is the only thing that needs backing up.
"""
from __future__ import annotations

import datetime as _dt
import re
import sqlite3
from pathlib import Path

KEEP = 30                  # newest backups kept
NAME_RX = re.compile(r"^grading_(\d{4}-\d{2}-\d{2})_(\d{6})(?:-\d+)?(?:_([a-z-]+))?\.db$")
REASONS = {
    "": "automatic",
    "open": "when the workspace was opened",
    "close": "when the app was closed",
    "manual": "made by hand",
    "before-restore": "just before a restore",
    "before-import": "before importing a package",
    "before-assignment": "before the assignment was changed",
    "before-penalties": "before points or penalties were changed",
}


def backup_dir(workspace: Path) -> Path:
    return Path(workspace) / "backups"


def make_backup(db_path: Path, reason: str = "") -> Path | None:
    """Copy the database into backups/. Returns the new file, or None if there was nothing to copy."""
    db_path = Path(db_path)
    if not db_path.exists():
        return None
    d = backup_dir(db_path.parent)
    d.mkdir(exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dest = d / (f"grading_{stamp}" + (f"_{reason}" if reason else "") + ".db")
    k = 1
    while dest.exists():
        k += 1
        dest = d / (f"grading_{stamp}-{k}" + (f"_{reason}" if reason else "") + ".db")
    src = sqlite3.connect(str(db_path), timeout=10)
    out = sqlite3.connect(str(dest))
    try:
        src.backup(out)
    finally:
        out.close()
        src.close()
    prune(d)
    return dest


def prune(d: Path, keep: int = KEEP) -> None:
    files = sorted(list_backups_in(d), key=lambda b: b["path"].name, reverse=True)
    for b in files[keep:]:
        try:
            b["path"].unlink()
        except OSError:
            pass


def list_backups_in(d: Path) -> list[dict]:
    out = []
    if not d.exists():
        return out
    for p in d.glob("grading_*.db"):
        m = NAME_RX.match(p.name)
        when = None
        if m:
            try:
                when = _dt.datetime.strptime(m.group(1) + m.group(2), "%Y-%m-%d%H%M%S")
            except ValueError:
                when = None
        reason = (m.group(3) if m else "") or ""
        out.append({"path": p, "when": when or _dt.datetime.fromtimestamp(p.stat().st_mtime),
                    "reason": reason, "label": REASONS.get(reason, reason)})
    return sorted(out, key=lambda b: b["when"], reverse=True)


def list_backups(workspace: Path) -> list[dict]:
    """Backups, newest first, each with a summary of what it holds."""
    items = list_backups_in(backup_dir(workspace))
    for b in items:
        b.update(summarize(b["path"]))
    return items


def summarize(db: Path) -> dict:
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            total = con.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
            reviewed = con.execute("SELECT COUNT(*) FROM reviews WHERE reviewed=1").fetchone()[0]
            started = con.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
            last = con.execute("SELECT MAX(updated_at) FROM reviews").fetchone()[0]
        finally:
            con.close()
        return {"students": total, "reviewed": reviewed, "opened": started, "last_change": last}
    except Exception:  # noqa: BLE001
        return {"students": None, "reviewed": None, "opened": None, "last_change": None}


def latest_backup_date(workspace: Path) -> _dt.date | None:
    items = list_backups_in(backup_dir(workspace))
    return items[0]["when"].date() if items else None


def restore_backup(db_path: Path, backup: Path) -> Path | None:
    """Put a backup back in place of the current grading. The current state is backed up first, so a restore
    can itself be undone. SQLite's backup function writes into the open database, so this also works on Windows
    where an open file cannot be replaced."""
    before = make_backup(db_path, "before-restore")
    src = sqlite3.connect(str(backup), timeout=10)
    dst = sqlite3.connect(str(db_path), timeout=10)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return before


def changed_since_last_backup(db_path: Path) -> bool:
    """True when grading was saved after the newest backup was made."""
    items = list_backups_in(backup_dir(Path(db_path).parent))
    if not items:
        return True
    newest = items[0]["path"].stat().st_mtime
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            last = con.execute("SELECT MAX(updated_at) FROM reviews").fetchone()[0]
            meta_changed = Path(db_path).stat().st_mtime
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        return True
    return bool((last and last > newest) or meta_changed > newest + 2)
