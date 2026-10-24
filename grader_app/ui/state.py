"""Shared application state: the open workspace, its store and pack."""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal

from ..applog import log as glog
from ..keyshare import unseal
from ..pack import Pack, load_pack
from ..workspace import DB_NAME, bring_in, import_pack
from ..store import Store

KEYRING_SERVICE = "MATH241Grader"


ACCESS_FORMAT = "math241grader-access"
ACCESS_NAME = "ai_access.m241access"   # inside the workspace folder, so AI access travels with it

_workspace: Path | None = None


def workspace_access_path() -> Path | None:
    return _workspace / ACCESS_NAME if _workspace else None


def _read_access(path: Path) -> dict | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if data.get("format") == ACCESS_FORMAT else None
    except Exception:
        return None


def own_api_key() -> str:
    """A key typed in on this computer (instructor)."""
    try:
        import keyring
        key = keyring.get_password(KEYRING_SERVICE, "openai")
        if key:
            return key
    except Exception:
        pass
    s = QSettings()
    return s.value("api_key_fallback", "") or ""


def access_info() -> dict | None:
    """The instructor's access file: the one inside the open workspace first, else one loaded on this
    computer by an older version (the key stays sealed)."""
    wp = workspace_access_path()
    if wp and wp.exists():
        data = _read_access(wp)
        if data:
            return data
    raw = QSettings().value("access_file", "")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def access_valid() -> tuple[bool, str]:
    acc = access_info()
    if not acc:
        return False, ""
    exp = acc.get("expires") or ""
    if exp and date.today().isoformat() > exp:
        return False, f"The instructor's access file expired on {exp}."
    label = acc.get("label") or "the instructor"
    return True, f"AI access from {label}'s access file" + (f", valid until {exp}." if exp else ".")


def load_access_file(path: str | Path) -> dict:
    """Validate an access file and copy it into the open workspace (or keep it on this computer when no
    workspace is open)."""
    data = _read_access(Path(path))
    if not data:
        raise ValueError("This is not an access file for this app.")
    unseal(data["key"])            # validates the file without keeping the plain key
    wp = workspace_access_path()
    if wp:
        if Path(path).resolve() != wp.resolve():
            wp.write_text(json.dumps(data), encoding="utf-8")
    else:
        QSettings().setValue("access_file", json.dumps(data))
    return data


def save_access_file(data: dict) -> Path:
    wp = workspace_access_path()
    if not wp:
        raise ValueError("Open a workspace first.")
    wp.write_text(json.dumps(data), encoding="utf-8")
    return wp


def remove_access_file() -> None:
    QSettings().remove("access_file")
    wp = workspace_access_path()
    if wp and wp.exists():
        wp.unlink()


def get_api_key() -> str:
    """Own key first, then a valid access file."""
    key = own_api_key()
    if key:
        return key
    ok, _ = access_valid()
    if ok:
        try:
            return unseal(access_info()["key"])
        except Exception:
            return ""
    return ""


def key_source() -> str:
    if own_api_key():
        return "own"
    if access_valid()[0]:
        return "access"
    return ""


def set_api_key(key: str) -> str:
    """Store the key. Returns where it was stored."""
    try:
        import keyring
        keyring.set_password(KEYRING_SERVICE, "openai", key)
        return "system keychain"
    except Exception:
        QSettings().setValue("api_key_fallback", key)
        return "application settings (no system keychain available)"


def remove_api_key() -> None:
    try:
        import keyring
        keyring.delete_password(KEYRING_SERVICE, "openai")
    except Exception:
        pass
    QSettings().remove("api_key_fallback")


def _check_writable(db_path) -> None:
    """Fail with a clear message instead of hanging when the database is locked or read-only
    (for example open in another copy of the app, or inside a syncing cloud folder)."""
    import sqlite3
    try:
        con = sqlite3.connect(str(db_path), timeout=5)
        con.execute("BEGIN IMMEDIATE")
        con.execute("ROLLBACK")
        con.close()
    except sqlite3.Error as e:
        raise PermissionError(
            "This workspace cannot be written to right now. It may be open in another copy of the app, or "
            "the folder may be read-only or still syncing. Close other copies, or copy the workspace folder "
            f"to this computer and open the copy. ({e})") from e


def output_dir(kind: str) -> Path:
    """Folder inside the workspace for files the app writes ('export', 'packages')."""
    if _workspace is None:
        raise ValueError("Open a workspace first.")
    d = _workspace / kind
    d.mkdir(parents=True, exist_ok=True)
    return d


def show_in_folder(path: Path) -> None:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    p = Path(path)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(p if p.is_dir() else p.parent)))


class AppState(QObject):
    workspace_changed = Signal()
    pack_changed = Signal()
    submissions_changed = Signal()
    reviews_changed = Signal()
    reload_student = Signal()
    student_updated = Signal(str)        # a new pre-screen result for this student was saved           # grading changed underneath the panel: show it again from the file

    def __init__(self):
        super().__init__()
        self.workspace: Path | None = None
        self.store: Store | None = None
        self.last_repair: dict = {}
        self.pack: Pack | None = None
        self.flush_hooks: list = []      # save anything still pending in the interface (the Review tab)
        self.discard_hooks: list = []    # forget what the interface shows, without saving (used by a restore)

    def discard(self):
        for f in self.discard_hooks:
            try:
                f()
            except Exception:  # noqa: BLE001
                pass

    def flush(self):
        for f in self.flush_hooks:
            try:
                f()
            except Exception:  # noqa: BLE001
                pass

    def backup(self, reason: str = ""):
        """Back up the grading now. Never stops the work if it fails."""
        if not self.workspace:
            return None
        try:
            from ..backup import make_backup
            p = make_backup(self.workspace / DB_NAME, reason)
            glog.info("Backup made (%s): %s", reason or "automatic", p.name if p else "nothing to copy")
            return p
        except Exception as e:  # noqa: BLE001
            glog.exception("Backup failed (%s): %s", reason or "automatic", e)
            return None

    # workspace ---------------------------------------------------------------
    def open_workspace(self, folder: str | Path, create: bool = False) -> None:
        """Open the workspace in `folder`. A new, empty workspace is only made when `create` is set, so
        choosing the wrong folder never silently shows an empty class."""
        folder = Path(folder)
        self.flush()      # anything pending belongs to the workspace that is open now
        if not (folder / DB_NAME).exists():
            if not create:
                raise FileNotFoundError(f"There is no workspace in {folder}.")
            folder.mkdir(parents=True, exist_ok=True)
        _check_writable(folder / DB_NAME)
        try:
            store = Store(folder / DB_NAME)
        except sqlite3.OperationalError as e:
            raise PermissionError(
                "This workspace is in use, probably still open in another copy of the app (or an older version). "
                "Close it there and try again, or copy the workspace folder and open the copy. "
                f"({e})") from e
        global _workspace
        _workspace = folder
        self.workspace = folder
        self.store = store
        QSettings().setValue("last_workspace", str(folder))
        recent = [str(folder)] + [p for p in (QSettings().value("recent_workspaces", []) or []) if p != str(folder)]
        QSettings().setValue("recent_workspaces", recent[:8])
        self.pack = None
        try:
            self.last_repair = bring_in(self.store)
        except Exception as e:  # noqa: BLE001
            self.last_repair = {"copied": [], "missing": [f"could not check the files ({e})"]}
        pack_path = self.store.get_meta("pack_path")
        if pack_path and Path(pack_path).exists():
            try:
                self.pack = load_pack(pack_path)
            except Exception:
                self.pack = None
        # a backup at least once a day, made when the workspace is opened
        try:
            import datetime
            from ..backup import latest_backup_date
            if self.store.counts().get("total") and latest_backup_date(folder) != datetime.date.today():
                self.backup("open")
        except Exception:  # noqa: BLE001
            pass
        from ..applog import attach_workspace
        attach_workspace(folder)
        if self.pack is not None:
            try:
                from ..pipeline import restore_all_lost_findings
                self.restored_findings = restore_all_lost_findings(self.store, self.pack)
            except Exception:  # noqa: BLE001
                self.restored_findings = []
        c = self.store.counts()
        glog.info("Workspace opened: %s (%s submissions, %s reviewed, assignment: %s)", folder, c.get("total", 0),
                  c.get("reviewed", 0), self.pack.title if self.pack else "none")
        if self.last_repair and (self.last_repair.get("copied") or self.last_repair.get("missing")):
            glog.info("Files brought into the workspace: %s copied, missing: %s",
                      len(self.last_repair.get("copied") or []), self.last_repair.get("missing") or "none")
        self.workspace_changed.emit()
        self.pack_changed.emit()
        self.submissions_changed.emit()

    def set_pack(self, folder: str | Path) -> None:
        load_pack(folder)  # fails early if this is not an assignment folder
        if self.store:
            if self.store.get_meta_raw("pack_path"):
                self.backup("before-assignment")
            folder = import_pack(self.store, Path(folder))
        self.pack = load_pack(folder)
        glog.info("Assignment set: %s (%s rubric items, %s points)", self.pack.title, len(self.pack.rubric),
                  self.pack.total_max)
        self.pack_changed.emit()

    def meta(self, key, default=None):
        return self.store.get_meta(key, default) if self.store else default

    def set_meta(self, key, value):
        if self.store:
            self.store.set_meta(key, value)

    @property
    def is_ta(self) -> bool:
        return bool(self.store) and self.store.get_meta("mode", "instructor") == "ta"

    def reload_pack(self):
        pp = self.meta("pack_path")
        if pp and Path(pp).exists():
            self.pack = load_pack(pp)
        self.pack_changed.emit()

    # API key -------------------------------------------------------------
    def ai_access(self) -> dict | None:
        return self.meta("ai_access") if self.is_ta else None

    def ai_status(self) -> tuple[bool, str]:
        """Whether AI calls are possible here, and a line describing it for the interface."""
        if not self.is_ta or not self.ai_access():
            if get_api_key():
                return (True, access_valid()[1] if key_source() == "access" else "")
            msg = access_valid()[1] or "No AI access on this computer."
            return (False, msg + (" Re-runs go to the instructor as requests." if self.is_ta else ""))
        acc = self.ai_access()
        used, limit = int(self.meta("ai_used", 0) or 0), int(acc.get("max_reruns") or 0)
        exp = acc.get("expires") or ""
        if exp and date.today().isoformat() > exp:
            return (False, f"AI access from the instructor expired on {exp}. Re-runs go to the instructor as requests.")
        if limit and used >= limit:
            return (False, f"All {limit} AI re-runs in this package are used. Further re-runs go to the instructor "
                           "as requests.")
        left = f"{limit - used} of {limit} re-runs left" if limit else "no re-run limit"
        return (True, f"AI access provided by the instructor: {left}" + (f", valid until {exp}." if exp else "."))

    def api_key(self) -> str:
        if not self.is_ta or not self.ai_access():
            return get_api_key()
        ok, _ = self.ai_status()
        if not ok:
            return ""
        try:
            return unseal(self.ai_access()["key"])
        except Exception:
            return ""

    def allowed_models(self) -> list[str]:
        mc = self.pack.model if self.pack else {}
        models = [m for m in (mc.get("name"), mc.get("escalation_name")) if m]
        restrict = None
        if self.is_ta and self.ai_access():
            restrict = self.ai_access().get("models")
        elif key_source() == "access":
            restrict = (access_info() or {}).get("models")
        if restrict is not None:
            strong_ok = bool((self.ai_access() if self.is_ta else access_info() or {}).get("allow_strong"))
            # models are matched by role, so a new pack with new model names still works
            models = models[:1] + (models[1:] if strong_ok or any(m in restrict for m in models[1:]) else [])
        return models

    def count_ai_use(self):
        if self.is_ta:
            self.set_meta("ai_used", int(self.meta("ai_used", 0) or 0) + 1)

    @property
    def ready(self) -> bool:
        return self.store is not None and self.pack is not None
