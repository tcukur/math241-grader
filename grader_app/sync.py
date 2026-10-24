"""Packages for passing work between the instructor and TAs without sharing the API key.

Instructor -> TA ("to_ta"): the assignment pack, the selected students' PDFs, their AI
pre-screen results, the grading worksheet and any grading already done.
TA -> instructor ("to_ta" back the other way is never needed): "to_instructor" carries the TA's
grading and re-run requests only. No PDFs, so it stays small.

Importing always merges: for each student the newer review wins, and a newer AI pre-screen
replaces an older one. Nothing is deleted.
"""
from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

from .store import Store

FORMAT = "math241grader-package"


def _now() -> float:
    return time.time()


def create_package(store: Store, workspace: Path, pack_folder: Path | None, sub_ids: list[str], out_path: Path,
                   kind: str, sender: str = "", worksheet: Path | None = None,
                   ai_access: dict | None = None) -> dict:
    assert kind in ("to_ta", "to_instructor")
    subs, reviews = [], {}
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for sid in sub_ids:
            row = store.submission(sid)
            if row is None:
                continue
            d = dict(row)
            if kind == "to_ta":
                pdf = Path(d["pdf_path"])
                arc = f"pdfs/{sid}.pdf"
                if pdf.exists():
                    z.write(pdf, arc)
                d["pdf_file"] = arc
                d.pop("pdf_path", None)
            else:
                d = {"sub_id": sid, "ta_note": d["ta_note"], "rerun_model": d["rerun_model"],
                     "rerun_requested": d["rerun_requested"]}
            subs.append(d)
            rv = store.review_raw(sid)
            if rv:
                reviews[sid] = rv
        pack_files = []
        if kind == "to_ta" and pack_folder:
            for f in Path(pack_folder).iterdir():
                if f.is_file():
                    z.write(f, f"pack/{f.name}")
                    pack_files.append(f.name)
        ws_file = None
        if kind == "to_ta" and worksheet and Path(worksheet).exists():
            z.write(worksheet, "worksheet.csv")
            ws_file = "worksheet.csv"
        manifest = {
            "format": FORMAT, "version": 1, "kind": kind, "created_at": _now(), "sender": sender,
            "pack_id": store.get_meta("pack_id", ""), "pack_files": pack_files, "worksheet_file": ws_file,
            "global_note": store.get_meta("global_note", "") or "",
            "submissions": subs, "reviews": reviews,
            "ai_access": ai_access if kind == "to_ta" else None,
        }
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
    return {"students": len(subs), "reviews": len(reviews), "path": str(out_path)}


def read_manifest(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        m = json.loads(z.read("manifest.json").decode("utf-8"))
    if m.get("format") != FORMAT:
        raise ValueError("This file is not a MATH241 Grader package.")
    return m


def _merge_review(store: Store, sid: str, incoming: dict) -> bool:
    mine = store.review_raw(sid)
    if mine is None or (incoming.get("updated_at") or 0) > (mine.get("updated_at") or 0):
        store.put_review_raw(sid, incoming)
        return True
    return False


def import_package(store: Store, workspace: Path, path: Path, my_mode: str) -> dict:
    m = read_manifest(path)
    kind = m["kind"]
    if kind == "to_ta" and my_mode == "instructor":
        raise ValueError("This is a package for a TA. Open it as a new workspace in TA mode instead.")
    if kind == "to_instructor" and my_mode == "ta":
        raise ValueError("This is a return file for the instructor, not an update for a TA.")
    stats = {"kind": kind, "students": 0, "screens_updated": 0, "reviews_updated": 0, "requests": 0,
             "sender": m.get("sender", "")}
    workspace = Path(workspace)
    with zipfile.ZipFile(path) as z:
        if kind == "to_ta":
            pack_dir = workspace / "pack"
            if m.get("pack_files"):
                pack_dir.mkdir(parents=True, exist_ok=True)
                for name in m["pack_files"]:
                    (pack_dir / name).write_bytes(z.read(f"pack/{name}"))
                store.set_meta("pack_path", str(pack_dir))
            if m.get("worksheet_file"):
                (workspace / "worksheet.csv").write_bytes(z.read(m["worksheet_file"]))
                store.set_meta("worksheet_path", str(workspace / "worksheet.csv"))
            store.set_meta("global_note", m.get("global_note", ""))
            store.set_meta("mode", "ta")
            # AI access travels with each package; an update without it withdraws access
            store.set_meta("ai_access", m.get("ai_access"))
            store.set_meta("ai_used", 0)
            sub_dir = workspace / "submissions"
            sub_dir.mkdir(parents=True, exist_ok=True)
            for d in m["submissions"]:
                sid = d["sub_id"]
                target = sub_dir / f"{sid}.pdf"
                if d.get("pdf_file"):
                    target.write_bytes(z.read(d["pdf_file"]))
                mine = store.submission(sid)
                vals = {k: d.get(k) for k in Store.COPY_COLS if k in d}
                if mine is None:
                    store.put_row(sid, str(target), vals)
                    stats["screens_updated"] += 1
                elif (d.get("screened_at") or 0) > (mine["screened_at"] or 0):
                    # a newer AI result from the instructor; this also settles any re-run request
                    store.put_row(sid, str(target), vals)
                    stats["screens_updated"] += 1
                else:
                    # same AI result as before: keep the TA's own note and any pending request
                    for k in ("ta_note", "rerun_model", "rerun_requested"):
                        vals.pop(k, None)
                    for k in ("screen", "screened_at", "status", "error", "prompt_text", "raw_response"):
                        vals.pop(k, None)
                    store.put_row(sid, str(target), vals)
                stats["students"] += 1
        else:
            for d in m["submissions"]:
                sid = d["sub_id"]
                if store.submission(sid) is None:
                    continue
                stats["students"] += 1
                if d.get("rerun_requested"):
                    store.request_rerun(sid, d.get("rerun_model"), d.get("ta_note") or "")
                    stats["requests"] += 1
                elif d.get("ta_note") is not None:
                    store.set_ta_note(sid, d.get("ta_note") or "")
                if m.get("sender"):
                    info = json.loads(store.submission(sid)["info"] or "{}")
                    info["assigned_ta"] = m["sender"]
                    store.set_info(sid, info)
        for sid, rv in (m.get("reviews") or {}).items():
            if store.submission(sid) is not None and _merge_review(store, sid, rv):
                stats["reviews_updated"] += 1
    return stats


def new_workspace_from_package(path: Path, workspace: Path) -> None:
    """Prepare an empty folder to receive a TA package."""
    workspace = Path(workspace)
    if workspace.exists() and any(workspace.iterdir()) and not (workspace / "grading.db").exists():
        raise ValueError("Choose an empty folder for the new workspace.")
    workspace.mkdir(parents=True, exist_ok=True)

