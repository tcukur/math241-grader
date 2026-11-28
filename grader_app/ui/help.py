"""Help: the user guide, the version history and an About page."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QTextBrowser, QVBoxLayout

from .resources import resource_dir

CSS = """
body { font-family: Inter, sans-serif; font-size: 13px; color: #0f172a; }
h1 { font-size: 20px; } h2 { font-size: 16px; margin-top: 18px; color: #3355d1; }
li { margin-bottom: 4px; }
"""


def _doc(name: str, title: str) -> str:
    p = resource_dir() / "docs" / name
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return f"# {title}\n\nThis page was not found next to the app."


def guide_text() -> str:
    return _doc("USER_GUIDE.md", "User guide")


def changelog_text() -> str:
    return _doc("CHANGELOG.md", "What's new")


def about_text() -> str:
    from .. import APP_NAME, APP_VERSION
    try:
        from ..main import _log_dir
        log = str(_log_dir() / "app.log")
    except Exception:  # noqa: BLE001
        log = "not available"
    import platform
    import sys
    try:
        import pymupdf
        mupdf = getattr(pymupdf, "__version__", "") or getattr(pymupdf, "VersionBind", "")
    except Exception:  # noqa: BLE001
        mupdf = ""
    try:
        import PySide6
        qt = PySide6.__version__
    except Exception:  # noqa: BLE001
        qt = ""
    return (f"# {APP_NAME}\n\n"
            f"**Version {APP_VERSION}**, October 2026\n\n"
            "Pre-screens AI-assisted assignments for MATH 241. The AI points to what needs a closer look. The "
            "grader decides every grade and every finding.\n\n"
            "## Developer\n\n"
            "Prof. Tolga Çukur, Department of Electrical and Electronics Engineering, Bilkent University, "
            "Ankara. Contact: cukur@ee.bilkent.edu.tr\n\n"
            "© 2026 Tolga Çukur. For use in Bilkent University courses.\n\n"
            "## This installation\n\n"
            f"- Running from: `{resource_dir()}`\n"
            f"- App log: `{log}`\n"
            "- Workspace log: *logs/grader.log* inside the workspace folder (*Help › Open log folder*)\n"
            f"- Python {sys.version.split()[0]} on {platform.system()} {platform.release()}"
            + (f", Qt for Python {qt}" if qt else "") + (f", PyMuPDF {mupdf}" if mupdf else "") + "\n\n"
            "If something goes wrong, send the workspace log to the instructor. It records each step and every "
            "error, never the API key.\n\n"
            "## Open-source components\n\n"
            "The app is built on these components, each used under its own licence:\n\n"
            "| Component | Used for | Licence |\n"
            "| --- | --- | --- |\n"
            "| Python | the language the app runs on | PSF License |\n"
            "| Qt for Python (PySide6) | windows, buttons, PDF display | LGPL v3 |\n"
            "| PyMuPDF and MuPDF (Artifex) | reading, rendering and writing PDFs | AGPL v3 |\n"
            "| OpenAI Python library | sending the pre-screen to the AI | Apache 2.0 |\n"
            "| httpx | network connections | BSD 3-Clause |\n"
            "| keyring | keeping your own API key in the system keychain | MIT |\n"
            "| openpyxl | reading and writing Moodle Excel files | MIT |\n"
            "| Inter font (Rasmus Andersson) | the app's typeface | SIL Open Font License 1.1 |\n"
            "| uv (Astral) | installing the app on first start | MIT or Apache 2.0 |\n\n"
            "The AI pre-screen uses OpenAI's API under the account holder's terms. Names, student IDs and "
            "email addresses are removed before anything is sent.\n")


def _space_out(doc) -> None:
    """Give Markdown pages room to breathe: spacing around headings and paragraphs, coloured section heads.
    Purely cosmetic, so any problem here leaves the page as it was."""
    try:
        from PySide6.QtGui import QColor, QTextCursor
        block = doc.begin()
        while block.isValid():
            cur = QTextCursor(block)
            fmt = block.blockFormat()
            level = fmt.headingLevel()
            if level == 1:
                fmt.setTopMargin(0)
                fmt.setBottomMargin(10)
            elif level == 2:
                fmt.setTopMargin(22)
                fmt.setBottomMargin(6)
                # select only this heading's own text, not the line break before it
                cur.movePosition(QTextCursor.StartOfBlock)
                cur.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                cf = cur.charFormat()
                cf.setForeground(QColor("#3355d1"))
                cur.mergeCharFormat(cf)
            elif level >= 3:
                fmt.setTopMargin(14)
                fmt.setBottomMargin(4)
            elif block.textList() is not None:
                fmt.setBottomMargin(5)
            else:
                fmt.setBottomMargin(8)
            cur.setBlockFormat(fmt)
            block = block.next()
    except Exception:  # noqa: BLE001
        pass


class HelpDialog(QDialog):
    """Shows one Markdown page. kind is 'guide', 'changes' or 'about'."""

    def __init__(self, parent=None, kind: str = "guide"):
        super().__init__(parent)
        title, text, size = {
            "guide": ("User guide", guide_text(), (860, 820)),
            "changes": ("What's new", changelog_text(), (760, 760)),
            "about": ("About", about_text(), (640, 640)),
        }.get(kind, ("User guide", guide_text(), (860, 820)))
        self.setWindowTitle(title)
        self.resize(*size)
        lay = QVBoxLayout(self)
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        view.document().setDefaultStyleSheet(CSS)
        view.setMarkdown(text)
        _space_out(view.document())
        view.document().setDocumentMargin(22)
        lay.addWidget(view)
