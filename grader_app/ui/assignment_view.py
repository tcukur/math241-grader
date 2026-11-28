"""The assignment at hand: rubric, handout and solution in a window of their own.

Opened from the Assignment button in the top bar, so it can be reached from any tab and kept open beside the
grading screen or on a second monitor while moving from student to student. It shows the files already copied
into the workspace and changes nothing."""
from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings, Qt
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QTabWidget, QTextBrowser, QVBoxLayout, QWidget

from ..scoring import fmt
from .pdf_view import PdfView
from .state import AppState

CSS = """
body { font-size: 13px; color: #0f172a; }
h1 { font-size: 18px; margin: 0 0 2px 0; }
h2 { font-size: 15px; margin: 18px 0 6px 0; }
.muted { color: #64748b; }
table { border-collapse: collapse; width: 100%; }
th { text-align: left; background: #eef2fd; padding: 6px 8px; font-weight: 600; }
td { padding: 6px 8px; border-bottom: 1px solid #e3e7ee; vertical-align: top; }
td.pts { text-align: right; white-space: nowrap; font-weight: 600; }
tr.group td { background: #f7f8fa; font-weight: 600; color: #334155; }
.focus { color: #64748b; font-size: 12px; margin-top: 3px; }
"""


def _e(s) -> str:
    return html.escape(str(s or ""))


def rubric_html(pack) -> str:
    d = pack.data
    out = [f"<h1>{_e(pack.title)}</h1>",
           f"<div class='muted'>{len(pack.rubric)} rubric items, {fmt(pack.total_max)} points in total</div>",
           "<h2>Rubric</h2><table><tr><th>Item</th><th style='text-align:right'>Points</th></tr>"]
    group = None
    for r in pack.rubric:
        if r.group and r.group != group:
            group = r.group
            out.append(f"<tr class='group'><td colspan='2'>{_e(group)}</td></tr>")
        orig = pack.handout_points(r.id)
        pts = fmt(r.max) + (f" <span class='muted'>(handout {fmt(orig)})</span>" if orig is not None else "")
        focus = f"<div class='focus'>What to look at: {_e(r.screening_focus)}</div>" if r.screening_focus else ""
        out.append(f"<tr><td><b>{_e(r.label)}</b><br/>{_e(r.description)}{focus}</td><td class='pts'>{pts}</td></tr>")
    out.append("</table>")
    levels = d.get("level_descriptions") or {}
    if levels:
        out.append("<h2>Levels</h2><table>")
        for lv in pack.levels:
            out.append(f"<tr><td class='pts' style='width:60px'>{lv}%</td><td>{_e(levels.get(str(lv), ''))}</td></tr>")
        out.append("</table>")
    for title, key in (("Grading rules", "grading_rules"), ("Accepted alternatives", "accepted_alternatives")):
        items = d.get(key) or []
        if items:
            out.append(f"<h2>{title}</h2><ul>" + "".join(f"<li>{_e(x)}</li>" for x in items) + "</ul>")
    cats = [c for c in pack.categories if c.points or c.row_cap_pct is not None]
    if cats:
        out.append("<h2>Integrity findings</h2><div class='muted'>What a confirmed finding costs. Half means "
                   "the finding was confirmed at half weight.</div><table><tr><th>Finding</th>"
                   "<th style='text-align:right'>Deduction</th></tr>")
        names = {r.id: r.label for r in pack.rubric}
        for c in cats:
            cap = ""
            if c.row_cap_pct is not None:
                rows = ", ".join(names.get(x, x) for x in c.default_rows) or "the affected items"
                cap = (f"<div class='focus'>Also caps {_e(rows)} at {fmt(c.row_cap_pct)}% "
                       + (f"(half: {fmt(c.half_row_cap_pct)}%)" if c.half_row_cap_pct is not None else "") + "</div>")
            out.append(f"<tr><td><b>{_e(c.label)}</b><br/>{_e(c.description)}{cap}</td>"
                       f"<td class='pts'>{fmt(c.points)} pts</td></tr>")
        out.append("</table>")
        if pack.integrity_cap:
            out.append(f"<p class='muted'>Integrity deductions are capped at {fmt(pack.integrity_cap)} points in "
                       "total.</p>")
    return "".join(out)


class AssignmentWindow(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent, Qt.Window)
        self.state = state
        self.setWindowTitle("Assignment")
        self.resize(900, 900)
        g = QSettings().value("assignment_window_geometry")
        if isinstance(g, QByteArray):
            self.restoreGeometry(g)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)
        self.rubric = QTextBrowser()
        self.rubric.setOpenExternalLinks(False)
        self.rubric.document().setDefaultStyleSheet(CSS)
        self.handout = PdfView()
        self.guide = PdfView()
        self.guide_text = QPlainTextEdit()
        self.guide_text.setReadOnly(True)
        self.code = QPlainTextEdit()
        self.code.setReadOnly(True)
        self.code.setStyleSheet("font-family: monospace;")
        self.empty = QLabel("Choose the assignment on the Setup tab first.")
        self.empty.setAlignment(Qt.AlignCenter)
        state.pack_changed.connect(self.refresh)
        state.workspace_changed.connect(self.refresh)
        self.refresh()

    def _file(self, key: str) -> Path | None:
        name = (self.state.pack.data.get("files") or {}).get(key) if self.state.pack else None
        p = self.state.pack.folder / name if name else None
        return p if p and p.exists() else None

    def refresh(self):
        keep = self.tabs.tabText(self.tabs.currentIndex()) if self.tabs.count() else ""
        while self.tabs.count():
            self.tabs.removeTab(0)
        pack = self.state.pack
        if not pack:
            self.tabs.addTab(self.empty, "Assignment")
            return
        self.setWindowTitle(f"Assignment: {pack.title}")
        self.rubric.setHtml(rubric_html(pack))
        self.tabs.addTab(self.rubric, "Rubric")
        hand = self._file("assignment")
        if hand:
            self.handout.load(str(hand))
            self.tabs.addTab(self.handout, "Handout")
        guide = self._file("instructor_guide")
        if guide and guide.suffix.lower() == ".pdf":
            self.guide.load(str(guide))
            self.tabs.addTab(self.guide, "Solution")
        elif guide:
            self.guide_text.setPlainText(guide.read_text(encoding="utf-8", errors="replace"))
            self.tabs.addTab(self.guide_text, "Solution")
        code = self._file("reference_code")
        if code:
            self.code.setPlainText(code.read_text(encoding="utf-8", errors="replace"))
            self.tabs.addTab(self.code, "Reference code")
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == keep:
                self.tabs.setCurrentIndex(i)

    def show_again(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e):
        QSettings().setValue("assignment_window_geometry", self.saveGeometry())
        super().closeEvent(e)
