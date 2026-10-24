"""Processing pipeline, independent of the user interface.

register_submissions() records what is in the submissions folder.
process_submission() runs extraction, automatic checks and the AI pre-screen
for one student and stores each stage immediately.
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from .applog import log as glog
from .checks import CheckResult, run_checks
from .extract import Extraction, extract_submission
from .llm import Screener, offline_screen
from .extract import ID_RE
from .moodle import file_hash, match_student, read_class_list, scan_submissions
from .pack import Pack
from .store import Store


def _page1_ids(pdf: Path) -> list[str]:
    import pymupdf
    try:
        with pymupdf.open(pdf) as d:
            return sorted(set(ID_RE.findall(d[0].get_text()))) if len(d) else []
    except Exception:
        return []


def register_submissions(store: Store, root: Path, worksheet: Path | None = None) -> dict:
    """Register the submissions in a Moodle ZIP or folder. Each PDF is copied into the workspace as
    submissions/<Moodle number>.pdf, so the workspace never depends on the download staying where it was."""
    import shutil
    from .moodle import unpack_zip
    from .workspace import import_pdf
    root = Path(root)
    sub_dir = store.root / "submissions"
    incoming = None
    if root.is_file() and root.suffix.lower() == ".zip":
        # a short temporary folder, so long Moodle names stay under Windows' path length limit
        import tempfile
        incoming = Path(tempfile.mkdtemp(prefix="m241_"))
        unpack_zip(root, incoming)
        root = incoming
    found, notes = scan_submissions(root)
    # an older workspace may have the Moodle download unpacked in submissions/; skip our own copies there
    found = [s for s in found if s.pdf_path.parent.resolve() != sub_dir.resolve()]
    stats = {"new": 0, "changed": 0, "same": 0, "notes": notes, "total": len(found), "unmatched": 0}
    cls = None
    if worksheet and Path(worksheet).exists():
        try:
            cls = read_class_list(Path(worksheet))
        except Exception as e:  # noqa: BLE001
            notes.append(f"Could not read the class list: {e}")
    try:
        for s in found:
            info = {"original_file": s.pdf_path.name, "moodle_folder": s.moodle_prefix}
            display = " ".join(s.name.replace("_", " ").split()) if s.name else ""
            if cls:
                entry, note = match_student(s.name, s.sub_id, _page1_ids(s.pdf_path), cls)
                if entry:
                    display = entry["full_name"]
                    info.update({k: entry[k] for k in ("full_name", "id_number", "email")})
                else:
                    stats["unmatched"] += 1
                if note:
                    info["match_note"] = note
            local = import_pdf(store, s.sub_id, s.pdf_path)
            state = store.upsert_found(s.sub_id, display, s.layout, s.moodle_prefix,
                                       str(local), file_hash(local), s.note or info.get("match_note", ""))
            stats[state] += 1
            store.set_info(s.sub_id, info)
    finally:
        if incoming is not None:
            shutil.rmtree(incoming, ignore_errors=True)
    if cls and stats["unmatched"]:
        notes.append(f"{stats['unmatched']} submissions could not be matched to the class list.")
    glog.info("Submissions added from %s: %s found, %s new, %s changed, %s unchanged, %s not in the class list",
              Path(root).name, stats["total"], stats["new"], stats["changed"], stats["same"], stats["unmatched"])
    return stats


def rematch_classlist(store: Store, worksheet: Path) -> dict:
    """Match students already in the workspace to a class list chosen after their PDFs were added."""
    cls = read_class_list(Path(worksheet))
    out = {"matched": 0, "unmatched": 0}
    for r in store.submissions():
        try:
            info = json.loads(r["info"] or "{}")
        except (ValueError, TypeError):
            info = {}
        moodle_name = (info.get("moodle_folder") or r["moodle_prefix"] or "").split("_")[0] or (r["name"] or "")
        try:
            ids = _page1_ids(Path(r["pdf_path"])) if r["pdf_path"] else []
        except Exception:  # noqa: BLE001
            ids = []
        entry, note = match_student(moodle_name, r["sub_id"], ids, cls)
        if entry:
            info.update({k: entry[k] for k in ("full_name", "id_number", "email")})
            info.pop("match_note", None)
            with store._lock, store.conn() as c:
                c.execute("UPDATE submissions SET name=? WHERE sub_id=?", (entry["full_name"], r["sub_id"]))
            out["matched"] += 1
        else:
            out["unmatched"] += 1
            if note:
                info["match_note"] = note
        store.set_info(r["sub_id"], info)
    return out


def current_prompt_version(store: Store) -> str:
    from .llm import prompt_version
    return prompt_version(store.get_meta("ai_instructions", "") or "", store.get_meta("global_note", "") or "")


def prompt_version_of(row) -> str | None:
    """The class-wide prompt version an AI result was made with ('default' for results from before versions were
    recorded), or None when there is no AI result."""
    try:
        meta = json.loads(row["screen"] or "{}").get("_meta", {})
    except (ValueError, TypeError):
        return None
    if row["status"] != "screened" or meta.get("model") in (None, "offline"):
        return None
    return meta.get("prompt_version") or "default"


def outdated_students(store: Store) -> list[str]:
    """Students whose AI result was made with an earlier class-wide prompt than the current one."""
    cur = current_prompt_version(store)
    out = []
    for r in store.submissions():
        v = prompt_version_of(r)
        if v is not None and v != cur and not r["rerun_requested"]:
            out.append(r["sub_id"])
    return out


def queue_rescreen(store: Store, sub_ids: list[str]) -> None:
    """Mark students to be pre-screened again on the next Start. Their current result stays until the new one
    arrives, and each keeps its own student note."""
    for sid in sub_ids:
        row = store.submission(sid)
        if row is not None:
            store.request_rerun(sid, None, row["ta_note"] or "")


def restore_lost_findings(store: Store, pack: Pack, sub_id: str) -> int:
    """Put back AI and automatic-check findings that are in the pre-screen result but missing from the grading.
    Version 0.7.1 and earlier could lose them when the student was on screen while the pre-screen ran. A finding
    whose type the grader changed, or one already decided under the same type, is not added again. Returns how
    many were put back; those students need a look again."""
    row = store.submission(sub_id)
    rev = store.review(sub_id)
    if row is None or rev is None or not row["screen"]:
        return 0
    try:
        screen = json.loads(row["screen"])
    except (ValueError, TypeError):
        return 0
    if screen.get("_meta", {}).get("model") in (None, "offline"):
        return 0
    from .scoring import new_review_from_screen
    fs = rev.get("findings", [])
    have_cat = {f.get("category") for f in fs} | {f.get("suggested_category") for f in fs}
    have_text = {f.get("summary") for f in fs}
    fresh = new_review_from_screen(pack, screen)["findings"]
    lost = [f for f in fresh if f.get("category") not in have_cat and f.get("summary") not in have_text]
    if not lost:
        return 0
    for f in lost:
        f["suggested_category"] = f.get("category")
    rev["findings"] = fs + lost
    rev["reviewed"] = False
    store.save_review(sub_id, rev)
    glog.info("Restored %s pre-screen finding(s) missing from the grading of %s", len(lost), sub_id)
    return len(lost)


def restore_all_lost_findings(store: Store, pack: Pack) -> list[str]:
    out = []
    for r in store.submissions():
        try:
            if restore_lost_findings(store, pack, r["sub_id"]):
                out.append(r["sub_id"])
        except Exception as e:  # noqa: BLE001
            glog.exception("Could not check %s for missing findings: %s", r["sub_id"], e)
    return out


def load_stage(row) -> tuple[Extraction | None, list[CheckResult] | None]:
    ext = Extraction.from_json(json.loads(row["extraction"])) if row["extraction"] else None
    checks = [CheckResult(**c) for c in json.loads(row["checks"])] if row["checks"] else None
    return ext, checks


STAGES = {
    "text": "Reading the PDF",
    "checks": "Automatic checks",
    "prepare": "Removing names, preparing pages",
    "ai": "Waiting for the AI",
    "save": "Saving",
}


def process_submission(store: Store, pack: Pack, sub_id: str, screener: Screener | None,
                       dry_run: bool = False, model_override: str | None = None, on_stage=None,
                       effort: str | None = None) -> str:
    """Extraction and checks are cached; the AI step uses the class-wide note
    (meta 'global_note') and this student's TA note, if any. on_stage(name) is told each step as it starts
    (see STAGES); it is only for showing progress and can never affect the result."""
    def stage(name):
        if on_stage:
            try:
                on_stage(name)
            except Exception:  # noqa: BLE001
                pass
    row = store.submission(sub_id)
    if row is None:
        return "missing"
    ext, checks = load_stage(row)
    if ext is not None and not getattr(ext, "hidden_checked", False):
        ext, checks = None, None        # read by an older version: read again so hidden text is checked too
    stage("text" if ext is None else "checks")
    if ext is None:
        info = json.loads(row["info"] or "{}") if row["info"] else {}
        ext = extract_submission(row["pdf_path"], known_name=info.get("full_name") or row["name"] or "",
                                 report_pattern_cfg=pack.report,
                                 max_images=int(pack.model.get("max_report_images", 8)),
                                 known_ids=[info.get("id_number", "")])
        stage("checks")
        checks = run_checks(pack, ext)
        store.save_extraction(sub_id, ext.to_json(), [c.to_json() for c in checks],
                              name_if_empty=ext.identity.get("name", ""))
    if checks is None:
        checks = run_checks(pack, ext)
    global_note = store.get_meta("global_note", "") or ""
    ta_note = row["ta_note"] or ""
    custom = store.get_meta("ai_instructions", "") or ""      # the instructor's edited AI instructions, if any
    if dry_run or screener is None:
        screen = offline_screen(pack, checks)
        from .llm import build_input, prompt_as_text
        inp, _ = build_input(pack, ext, checks, row["pdf_path"], global_note, ta_note, with_images=False)
        store.save_prompt(sub_id, prompt_as_text(inp, custom), None)
    else:
        screen = screener.screen(ext, checks, row["pdf_path"], global_note, ta_note, model_override,
                                 on_stage=stage, custom_instructions=custom, effort=effort)
        store.save_prompt(sub_id, screen.pop("_prompt_text", ""), screen.pop("_raw", None))
    stage("save")
    from .llm import auto_findings
    screen["auto_integrity"] = auto_findings(pack, checks)
    store.save_screen(sub_id, screen)
    try:
        merge_new_screen(store, pack, sub_id)
    except Exception as e:  # noqa: BLE001
        print(f"merge after re-screen failed for {sub_id}: {e}")
    return "screened"


def merge_new_screen(store: Store, pack: Pack, sub_id: str) -> dict | None:
    """Bring a newer AI pre-screen into a student's grading without overriding the grader.

    The grader's levels, comments and decided findings stay. New AI findings are added only for kinds of
    problem not already in the grading, so nothing is listed twice. If the grader had already started or
    finished this student, the student is flagged for a re-check (meta 'recheck:<id>'), with a note of what
    the AI now sees differently, and is no longer counted as reviewed until the grader confirms again.
    Safe to call repeatedly: it acts once per new pre-screen."""
    from .scoring import new_review_from_screen
    row = store.submission(sub_id)
    if row is None or not row["screen"]:
        return None
    screen = json.loads(row["screen"])
    if screen.get("_meta", {}).get("model") == "offline":
        return None                     # automatic checks only: nothing from the AI to compare
    statuses = {x["row_id"]: x.get("status", "gray") for x in screen.get("rows", [])}
    seen = store.get_meta(f"screen_seen:{sub_id}")
    if seen == row["screened_at"]:
        return None
    previous = store.get_meta(f"ai_status:{sub_id}") or {}
    store.set_meta(f"screen_seen:{sub_id}", row["screened_at"])
    store.set_meta(f"ai_status:{sub_id}", statuses)
    rev = store.review(sub_id)
    if rev is None:
        return None                     # not opened yet: the grading starts from this pre-screen
    if seen is None and (rev.get("updated_at") or 0) >= (row["screened_at"] or 0):
        return None                     # a workspace from an older version: this is not a new pre-screen
    started = rev.get("reviewed") or any(v is not None for v in (rev.get("levels") or {}).values()) or any(
        f.get("decision", "pending") != "pending" for f in rev.get("findings") or [])
    fresh = new_review_from_screen(pack, screen)["findings"]
    kept = [f for f in rev.get("findings") or [] if f.get("origin") == "ta" or f.get("decision") != "pending"
            or f.get("similar_pair")]          # similar-work findings come from the comparison, not the AI
    have = {f.get("category") for f in kept if not f.get("similar_pair")}
    have_text = {f.get("summary") for f in kept}
    added = [f for f in fresh if f.get("category") not in have
             or (f.get("summary", "").startswith("Automatic check: Hidden text") and f.get("summary") not in have_text)]
    rev["findings"] = kept + added
    note = None
    if started:
        names = {r.id: r.label for r in pack.rubric}
        label = {"green": "nothing flagged", "yellow": "check this", "red": "likely problem", "gray": "not assessed"}
        changed = [f"{names.get(k, k)}: {label.get(previous[k], previous[k])} → {label.get(v, v)}"
                   for k, v in statuses.items() if k in previous and previous[k] != v]
        cats = {c.id: c.label for c in pack.categories}
        note = {"at": row["screened_at"], "model": screen.get("_meta", {}).get("model", ""),
                "changed": changed, "compared": bool(previous),
                "new_findings": [cats.get(f.get("category"), f.get("category")) for f in added],
                "was_reviewed": bool(rev.get("reviewed"))}
        store.set_meta(f"recheck:{sub_id}", note)
        rev["reviewed"] = False
    store.save_review(sub_id, rev)
    return note


class BatchRunner:
    """Runs pending submissions with a few parallel workers. Can be paused;
    anything finished is already saved, so a restart continues from there."""

    def __init__(self, store: Store, pack: Pack, api_key: str | None, dry_run: bool, workers: int = 4,
                 redo_errors: bool = True, model: str | None = None, effort: str | None = None):
        self.store, self.pack, self.dry_run = store, pack, dry_run
        self.effort = effort                    # reasoning effort for this run; None means the assignment's default
        self.model = model                      # the model chosen for this run; None means the assignment's default
        self.workers = max(1, workers)
        self.redo_errors = redo_errors
        self.stop_event = threading.Event()
        self.screener = None if dry_run else Screener(pack, api_key or "")

    def pending(self) -> list[str]:
        out = []
        for r in self.store.submissions():
            if r["rerun_requested"] and not self.dry_run:
                out.append(r["sub_id"])       # a TA asked for this one again
                continue
            if r["status"] == "screened":
                meta = json.loads(r["screen"] or "{}").get("_meta", {})
                # a dry-run result is replaced when a real AI run is requested
                if self.dry_run or meta.get("model") != "offline":
                    continue
            if r["status"] == "error" and not self.redo_errors:
                continue
            out.append(r["sub_id"])
        return out

    def stop(self):
        self.stop_event.set()

    def run(self, on_progress: Callable[[str, str, str], None], on_stage=None) -> None:
        todo = self.pending()

        def job(sid):
            if self.stop_event.is_set():
                return sid, "skipped", ""
            import time as _t
            t0 = _t.monotonic()
            try:
                row = self.store.submission(sid)
                model = ((row["rerun_model"] or None) if row and row["rerun_requested"] else None) or self.model
                asked = self.store.get_meta(f"rerun_effort:{sid}") if row and row["rerun_requested"] else None
                state = process_submission(self.store, self.pack, sid, self.screener, self.dry_run, model,
                                           effort=asked or self.effort,
                                           on_stage=(lambda name, s=sid: on_stage(s, name)) if on_stage else None)
                if row and row["rerun_requested"] and not self.dry_run:
                    self.store.clear_rerun_request(sid)
                    self.store.set_meta(f"rerun_effort:{sid}", None)
                done = self.store.submission(sid)
                meta = (json.loads(done["screen"] or "{}").get("_meta", {}) if done else {})
                glog.info("Pre-screen %s: %s in %.0f s (model %s, effort %s, tokens in %s / out %s)", sid, state,
                          _t.monotonic() - t0, meta.get("model", "-"), meta.get("effort", "-"),
                          meta.get("input_tokens", "-"), meta.get("output_tokens", "-"))
                return sid, state, ""
            except Exception as e:  # noqa: BLE001
                glog.exception("Pre-screen %s failed after %.0f s: %s", sid, _t.monotonic() - t0, e)
                self.store.save_error(sid, f"{type(e).__name__}: {e}")
                return sid, "error", str(e)

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = [pool.submit(job, s) for s in todo]
            for fut in as_completed(futures):
                if fut.cancelled():
                    continue
                sid, state, msg = fut.result()
                if state != "skipped":
                    on_progress(sid, state, msg)
                if self.stop_event.is_set():
                    for f in futures:
                        f.cancel()
