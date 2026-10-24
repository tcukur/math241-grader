"""A workspace is one self-contained folder:

    <workspace>/grading.db         grading, AI results, settings
    <workspace>/assignment/        copy of the assignment pack (pack.json, PDFs, reference code)
    <workspace>/submissions/       copy of every student PDF, named <moodle number>.pdf
    <workspace>/classlist.<ext>    copy of the class list
    <workspace>/ai_access.m241access   sealed AI access for TAs (optional)
    <workspace>/export/            feedback PDFs, Moodle files, grade tables
    <workspace>/packages/          TA packages and return files

Everything is stored relative to the folder, so it can be moved, renamed, copied to another computer or
opened on Mac or Windows without breaking. Original file names and Moodle prefixes live in the database.
"""
from __future__ import annotations

import os
import shutil
import unicodedata
from pathlib import Path

from .store import Store

DB_NAME = "grading.db"
CLOUD_MARKERS = ("googledrive", "google drive", "cloudstorage", "my drive", "dropbox", "onedrive",
                 "icloud", "mobile documents", "box sync")


# ---------------------------------------------------------------- finding and creating ----------
def find_workspaces(folder: Path, depth: int = 3) -> list[Path]:
    """Workspaces (folders holding grading.db) at or below `folder`, nearest first."""
    folder = Path(folder)
    found = []
    if (folder / DB_NAME).exists():
        return [folder]
    frontier = [folder]
    for _ in range(depth):
        nxt = []
        for d in frontier:
            try:
                for child in sorted(d.iterdir()):
                    if child.is_dir() and not child.name.startswith("."):
                        if (child / DB_NAME).exists():
                            found.append(child)
                        else:
                            nxt.append(child)
            except OSError:
                continue
        if found:
            return found
        frontier = nxt
    return found


def is_cloud_folder(path: Path) -> bool:
    s = str(Path(path).resolve()).lower()
    return any(m in s for m in CLOUD_MARKERS)


def copy_workspace(src: Path, dest_parent: Path) -> Path:
    dest_parent.mkdir(parents=True, exist_ok=True)
    dest = dest_parent / src.name
    k = 2
    while dest.exists():
        dest = dest_parent / f"{src.name} ({k})"
        k += 1
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("*-wal", "*-shm", ".DS_Store"))
    return dest


def local_workspaces_dir() -> Path:
    # the home folder, not Documents: Documents is often synced by OneDrive (Windows) or iCloud (Mac)
    return Path.home() / "MATH241 Grader workspaces"


# ---------------------------------------------------------------- bringing files in --------------
def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def import_pack(store: Store, src: Path) -> Path:
    """Copy an assignment pack into <workspace>/assignment (replacing an older copy)."""
    dest = store.root / "assignment"
    src = Path(src)
    if not _same_file(src, dest):
        tmp = store.root / "assignment.new"
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(src, tmp, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
        if dest.exists():
            shutil.rmtree(dest)
        tmp.rename(dest)
    store.set_meta("pack_path", str(dest))
    return dest


def import_classlist(store: Store, src: Path) -> Path:
    src = Path(src)
    dest = store.root / ("classlist" + src.suffix.lower())
    if not _same_file(src, dest):
        for old in store.root.glob("classlist.*"):
            old.unlink(missing_ok=True)
        shutil.copy2(src, dest)
    store.set_meta("worksheet_path", str(dest))
    return dest


def import_pdf(store: Store, sub_id: str, src: Path) -> Path:
    dest_dir = store.root / "submissions"
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / f"{sub_id}.pdf"
    if not _same_file(src, dest):
        shutil.copy2(src, dest)
    return dest


# ---------------------------------------------------------------- older workspaces ----------------
def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _find_by_name(name: str, roots: list[Path], depth: int = 2) -> Path | None:
    """Find a file or folder by name, ignoring Mac/Windows differences in how accented letters are stored."""
    want = _nfc(name)
    frontier = [r for r in roots if r and r.exists()]
    seen = set()
    for _ in range(depth + 1):
        nxt = []
        for d in frontier:
            if d in seen:
                continue
            seen.add(d)
            try:
                for child in d.iterdir():
                    if _nfc(child.name) == want:
                        return child
                    if child.is_dir() and not child.name.startswith("."):
                        nxt.append(child)
            except OSError:
                continue
        frontier = nxt
    return None


def _locate(old: str, store: Store, extra_roots: list[Path]) -> Path | None:
    p = Path(old)
    if p.exists():
        return p
    old_root = store.get_meta_raw("workspace_root")
    if old_root:
        try:
            cand = (store.root / os.path.relpath(old, old_root)).resolve()
            if cand.exists():
                return cand
        except (ValueError, OSError):
            pass
    name = p.name if "/" not in old or "\\" in old else old.rsplit("/", 1)[-1]
    name = name.rsplit("\\", 1)[-1]
    return _find_by_name(name, [store.root, store.root.parent] + extra_roots)


def bring_in(store: Store) -> dict:
    """Make a workspace self-contained: copy in anything it still refers to outside its folder.
    Safe to run on every open; does nothing for an up-to-date workspace."""
    rep = {"copied": [], "missing": []}
    raw = store.get_meta_raw("pack_path")
    if raw and not store.inside(raw):
        src = _locate(raw, store, [])
        if src is not None and (src / "pack.json").exists():
            import_pack(store, src)
            rep["copied"].append("the assignment")
        else:
            rep["missing"].append("the assignment folder")
    raw = store.get_meta_raw("worksheet_path")
    if raw and not store.inside(raw):
        src = _locate(raw, store, [])
        if src is not None and src.is_file():
            import_classlist(store, src)
            rep["copied"].append("the class list")
        else:
            rep["missing"].append("the class list")

    raw_sub = store.get_meta_raw("submissions_path")
    sub_roots = []
    if raw_sub and not store.inside(raw_sub):
        loc = _locate(raw_sub, store, [])
        if loc is not None:
            sub_roots.append(loc)
    n_ok, n_missing = 0, 0
    for r in store.submissions():
        stored = r.get("pdf_path_stored")
        if not stored or store.inside(stored):
            if stored and not Path(r["pdf_path"]).exists():
                n_missing += 1
            continue
        src = _locate(stored, store, sub_roots)
        if src is not None and src.is_file():
            store.set_pdf_path(r["sub_id"], import_pdf(store, r["sub_id"], src))
            n_ok += 1
        else:
            n_missing += 1
    if n_ok:
        rep["copied"].append(f"{n_ok} student PDF" + ("s" if n_ok != 1 else ""))
    if n_missing:
        rep["missing"].append(f"{n_missing} student PDF" + ("s" if n_missing != 1 else ""))
    # once every PDF is inside, the workspace's submissions folder is the one to show and use
    raw_sub = store.get_meta_raw("submissions_path")
    subs = store.submissions()
    if subs and raw_sub and not store.inside(raw_sub) and all(store.inside(r.get("pdf_path_stored")) for r in subs):
        store.set_meta("submissions_source", raw_sub)
        store.set_meta("submissions_path", str(store.root / "submissions"))
    store.set_meta("workspace_root", str(store.root))
    return rep
