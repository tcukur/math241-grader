"""Application entry point."""
import os
import sys
import traceback
from pathlib import Path


def _log_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
        return base / "MATH241Grader"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MATH241 Grader"
    return Path.home() / ".math241grader"


def _setup_logging() -> Path | None:
    """On Windows the app runs without a console window, so there is nowhere to print to and some libraries
    fail when they try. Send all output to a log file instead, which also keeps a record of any error."""
    log = None
    try:
        d = _log_dir()
        d.mkdir(parents=True, exist_ok=True)
        log = d / "app.log"
        if log.exists() and log.stat().st_size > 2_000_000:
            log.replace(d / "app.old.log")
        if sys.stdout is None or sys.stderr is None or sys.platform.startswith("win"):
            fh = open(log, "a", encoding="utf-8", buffering=1)
            sys.stdout = fh
            sys.stderr = fh
    except Exception:  # noqa: BLE001
        pass
    return log


def main() -> int:
    log = _setup_logging()

    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication, QMessageBox

    from . import APP_NAME, APP_VERSION
    from .ui.main_window import MainWindow
    from .ui.theme import apply_theme

    print(f"--- {APP_NAME} {APP_VERSION} starting, Python {sys.version.split()[0]} on {sys.platform}")
    from .applog import log as glog, start_app_log, workspace_log
    start_app_log((log.parent / "events.log") if log else None)

    QCoreApplication.setOrganizationName("Bilkent")
    QCoreApplication.setApplicationName(APP_NAME)
    app = QApplication(sys.argv)
    # The app is in English: numbers (5.0, not 5,0) and dates follow that, whatever the computer's language.
    from PySide6.QtCore import QLocale
    loc = QLocale(QLocale.English, QLocale.UnitedStates)
    loc.setNumberOptions(QLocale.OmitGroupSeparator)
    QLocale.setDefault(loc)

    def on_error(etype, value, tb):
        # an unexpected error is shown and logged instead of silently closing the app
        text = "".join(traceback.format_exception(etype, value, tb))
        try:
            print(text, file=sys.stderr)
        except Exception:  # noqa: BLE001
            pass
        glog.error("Unexpected error: %s: %s", etype.__name__, value, exc_info=(etype, value, tb))
        where = None
        try:
            where = workspace_log(w.state.workspace) if w is not None else None
        except Exception:  # noqa: BLE001
            pass
        try:
            QMessageBox.warning(None, "Something went wrong",
                                f"{etype.__name__}: {value}\n\nYour grading is saved. If this keeps happening, "
                                f"send this log file to the instructor:\n{where or log or 'not available'}")
        except Exception:  # noqa: BLE001
            pass

    w = None
    sys.excepthook = on_error
    apply_theme(app)
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
