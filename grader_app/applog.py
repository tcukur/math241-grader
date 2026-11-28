"""Diagnostic log.

Two files get the same messages:
  - <workspace>/logs/grader.log, kept with the workspace, so a TA can send it along with a problem report;
  - app.log in the app's own folder, which also covers what happens before a workspace is open.

Each start of the app writes a short header (version, system, workspace). Then one line per step that matters:
imports, each student pre-screened (with time and tokens), exports, backups, changes to points, penalties or AI
instructions, and every error with its full traceback. The API key and the prompt text are never written."""
from __future__ import annotations

import logging
import logging.handlers
import platform
import sys
import threading
from pathlib import Path

log = logging.getLogger("grader")
log.setLevel(logging.INFO)
log.propagate = False
class _SafeFormatter(logging.Formatter):
    """Never lets an API key reach the file, even inside an error message from the AI service."""
    _KEY = None

    def format(self, record):
        import re
        if _SafeFormatter._KEY is None:
            _SafeFormatter._KEY = re.compile(r"sk-[A-Za-z0-9_\-*]{6,}")
        return _SafeFormatter._KEY.sub("sk-[hidden]", super().format(record))


_FMT = _SafeFormatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
_ws_handler: logging.Handler | None = None
_app_handler: logging.Handler | None = None


def _header() -> str:
    from . import APP_NAME, APP_VERSION
    parts = [f"{APP_NAME} {APP_VERSION}", f"Python {sys.version.split()[0]}", platform.platform()]
    try:
        import PySide6
        parts.append(f"Qt {PySide6.__version__}")
    except Exception:  # noqa: BLE001
        pass
    try:
        import pymupdf
        parts.append(f"PyMuPDF {pymupdf.VersionBind}")
    except Exception:  # noqa: BLE001
        pass
    return " · ".join(parts)


def start_app_log(path: Path | None) -> None:
    """The app-wide log. Called once at start."""
    global _app_handler
    if path is None or _app_handler is not None:
        return
    try:
        h = logging.handlers.RotatingFileHandler(path, maxBytes=2_000_000, backupCount=2, encoding="utf-8")
        h.setFormatter(_FMT)
        log.addHandler(h)
        _app_handler = h
    except Exception:  # noqa: BLE001
        pass
    log.info("=" * 20 + " start: " + _header())
    _install_hooks()


def attach_workspace(folder: Path) -> Path | None:
    """Also write to the log inside this workspace (and stop writing to the previous one)."""
    global _ws_handler
    if _ws_handler is not None:
        log.removeHandler(_ws_handler)
        try:
            _ws_handler.close()
        except Exception:  # noqa: BLE001
            pass
        _ws_handler = None
    try:
        d = Path(folder) / "logs"
        d.mkdir(exist_ok=True)
        path = d / "grader.log"
        h = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        h.setFormatter(_FMT)
        log.addHandler(h)
        _ws_handler = h
        h.emit(logging.LogRecord("grader", logging.INFO, "", 0, "=" * 20 + " session: " + _header(), None, None))
        return path
    except Exception:  # noqa: BLE001
        return None


def workspace_log(folder: Path | None) -> Path | None:
    return Path(folder) / "logs" / "grader.log" if folder else None


def _install_hooks() -> None:
    # errors in background threads end up in the log too
    def thread_hook(args):
        log.error("Error in background work (%s): %s", getattr(args.thread, "name", "?"), args.exc_value,
                  exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    threading.excepthook = thread_hook
    # Qt's own warnings, without the routine noise
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler

        def qt_handler(mode, _ctx, message):
            if mode in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
                log.error("Qt: %s", message)
            elif mode == QtMsgType.QtWarningMsg and "propagateSizeHints" not in message:
                log.warning("Qt: %s", message)
        qInstallMessageHandler(qt_handler)
    except Exception:  # noqa: BLE001
        pass
