"""Dialog: create an assignment pack from new documents, with an AI-drafted rubric."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..pack_builder import DEFAULT_RULES, ai_draft, build_pack
from .state import AppState
from .theme import WrapLabel

COLS = ["Group", "Rubric row", "Max", "Description", "What the AI should check"]


class DraftThread(QThread):
    done = Signal(dict, str)

    def __init__(self, key, model, a, g):
        super().__init__()
        self.args = (key, model, a, g)

    def run(self):
        try:
            self.done.emit(ai_draft(self.args[0], self.args[1], Path(self.args[2]), Path(self.args[3])), "")
        except Exception as e:  # noqa: BLE001
            self.done.emit({}, f"{type(e).__name__}: {e}")


def _file_row(placeholder, filt):
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    lay.addWidget(e, 1)
    b = QPushButton("Choose…")
    b.clicked.connect(lambda: (lambda f: e.setText(f) if f else None)(
        QFileDialog.getOpenFileName(w, placeholder, "", filt)[0]))
    lay.addWidget(b)
    return w, e


class NewPackDialog(QDialog):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("New assignment from documents")
        self.resize(1080, 860)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll, 1)
        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)

        lay.addWidget(WrapLabel(
            "Point to the new assignment's documents. The AI can draft the rubric rows from your instructor guide. "
            "Check every row before saving: the points must match your rubric, and 'What the AI should check' "
            "steers the pre-screen. The guide is used as reference material, never as the only correct answer.",
            "muted"))
        form = QFormLayout()
        self.title = QLineEdit()
        self.title.setPlaceholderText("For example: MATH 241 Assignment 2 (Fall 2026-2027)")
        form.addRow("Title", self.title)
        self.short = QLineEdit()
        self.short.setPlaceholderText("For example: MATH241-A2 (used in feedback file names)")
        form.addRow("Short name", self.short)
        w, self.assignment = _file_row("Assignment handout (PDF)", "PDF (*.pdf)")
        form.addRow("Assignment", w)
        w, self.guide = _file_row("Instructor guide with rubric (PDF, .tex or .txt)", "Documents (*.pdf *.tex *.txt)")
        form.addRow("Instructor guide", w)
        w, self.code = _file_row("Optional reference code", "Code (*.py *.m *.ipynb *.txt);;All files (*)")
        form.addRow("Reference code", w)
        self.page_limit = QSpinBox()
        self.page_limit.setRange(0, 100)
        self.page_limit.setSpecialValueText("No limit")
        form.addRow("Main report page limit", self.page_limit)
        lay.addLayout(form)

        dr = QHBoxLayout()
        self.draft_btn = QPushButton("Draft rubric from the guide with AI")
        self.draft_btn.setObjectName("primary")
        self.draft_btn.clicked.connect(self.draft)
        dr.addWidget(self.draft_btn)
        self.draft_status = WrapLabel("", "muted")
        dr.addWidget(self.draft_status, 1)
        lay.addLayout(dr)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setWordWrap(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setMinimumHeight(260)
        self.table.itemChanged.connect(self._total)
        lay.addWidget(self.table)
        tb = QHBoxLayout()
        add = QPushButton("Add row")
        add.clicked.connect(lambda: self._add_row({}))
        tb.addWidget(add)
        rm = QPushButton("Remove selected row")
        rm.clicked.connect(self._remove_row)
        tb.addWidget(rm)
        self.total = QLabel("")
        tb.addStretch(1)
        tb.addWidget(self.total)
        lay.addLayout(tb)

        lay.addWidget(QLabel("Grading rules, one per line"))
        self.rules = QPlainTextEdit("\n".join(DEFAULT_RULES))
        self.rules.setMaximumHeight(120)
        lay.addWidget(self.rules)
        lay.addWidget(QLabel("Examples of accepted alternative approaches, one per line (optional)"))
        self.alts = QPlainTextEdit()
        self.alts.setMaximumHeight(100)
        lay.addWidget(self.alts)
        lay.addWidget(QLabel("Required report headings, one per line as \"Heading | Rubric row\" (optional)"))
        self.heads = QPlainTextEdit()
        self.heads.setMaximumHeight(100)
        lay.addWidget(self.heads)

        # the assignment is always written into the open workspace, next to everything else
        self.folder = QLineEdit()
        base = state.workspace if state.workspace else Path.home() / "MATH241 Grader assignments"
        self.folder.setText(str(Path(base) / "assignment"))
        if not state.workspace:
            sr = QHBoxLayout()
            sr.addWidget(QLabel("Save the assignment in"))
            sr.addWidget(self.folder, 1)
            fb = QPushButton("Choose…")
            fb.clicked.connect(lambda: (lambda d: self.folder.setText(d) if d else None)(
                QFileDialog.getExistingDirectory(self, "Folder for the new assignment")))
            sr.addWidget(fb)
            outer.addLayout(sr)
        btns = QHBoxLayout()
        btns.addStretch(1)
        c = QPushButton("Cancel")
        c.clicked.connect(self.reject)
        btns.addWidget(c)
        ok = QPushButton("Save and use this assignment")
        ok.setObjectName("primary")
        ok.clicked.connect(self.save)
        btns.addWidget(ok)
        outer.addLayout(btns)
        self._total()

    # table ------------------------------------------------------------------
    def _add_row(self, r: dict):
        i = self.table.rowCount()
        self.table.insertRow(i)
        vals = [r.get("group", ""), r.get("label", ""), f"{r.get('max', '')}".rstrip("0").rstrip(".")
                if isinstance(r.get("max"), float) else str(r.get("max", "")),
                r.get("description", ""), r.get("screening_focus", "")]
        for j, v in enumerate(vals):
            self.table.setItem(i, j, QTableWidgetItem(v))
        self.table.resizeRowsToContents()

    def _remove_row(self):
        for idx in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(idx)
        self._total()

    def _rows(self) -> list[dict]:
        out = []
        for i in range(self.table.rowCount()):
            cell = [(self.table.item(i, j).text().strip() if self.table.item(i, j) else "") for j in range(len(COLS))]
            if not cell[1]:
                continue
            try:
                mx = float(cell[2].replace(",", "."))
            except ValueError:
                mx = 0.0
            out.append({"group": cell[0], "label": cell[1], "max": mx, "description": cell[3],
                        "screening_focus": cell[4]})
        return out

    def _total(self, *_):
        rows = self._rows()
        self.total.setText(f"{len(rows)} rows, total {sum(r['max'] for r in rows):g} points")

    # actions ----------------------------------------------------------------
    def draft(self):
        a, g = self.assignment.text().strip(), self.guide.text().strip()
        if not (a and g and Path(a).exists() and Path(g).exists()):
            QMessageBox.information(self, "Documents missing", "Choose the assignment and the instructor guide first.")
            return
        key = self.state.api_key()
        if not key:
            QMessageBox.information(self, "No AI access", "Save a key or load an access file on the Setup tab. "
                                                          "You can also fill in the rubric by hand.")
            return
        model = (self.state.pack.model.get("name") if self.state.pack else None) or self._template()["model"]["name"]
        self.draft_btn.setEnabled(False)
        self.draft_status.setText("Reading the documents and drafting the rubric…")
        self._t = DraftThread(key, model, a, g)
        self._t.done.connect(self._drafted)
        self._t.start()

    def _drafted(self, d: dict, err: str):
        self.draft_btn.setEnabled(True)
        if err:
            self.draft_status.setText("Drafting failed: " + err[:300])
            return
        self.table.setRowCount(0)
        for r in d.get("rubric", []):
            self._add_row(r)
        if d.get("title") and not self.title.text():
            self.title.setText(d["title"])
        if d.get("grading_rules"):
            self.rules.setPlainText("\n".join(DEFAULT_RULES + [x for x in d["grading_rules"] if x not in DEFAULT_RULES]))
        self.alts.setPlainText("\n".join(d.get("accepted_alternatives", [])))
        self.heads.setPlainText("\n".join(f"{h['text']} | {h['row_label']}" for h in d.get("required_headings", [])))
        if d.get("page_limit"):
            self.page_limit.setValue(int(d["page_limit"]))
        self._total()
        note = d.get("notes", "").strip()
        self.draft_status.setText("Draft ready. Check every row, especially the points." + (f" Note: {note}" if note else ""))

    def _template(self) -> dict:
        # penalties, model and checks are taken from the current assignment, else from the app's defaults
        p = Path(__file__).resolve().parents[1] / "defaults.json"
        if self.state.pack:
            p = self.state.pack.folder / "pack.json"
        return json.loads(p.read_text(encoding="utf-8"))

    def save(self):
        rows = self._rows()
        a, g, c = self.assignment.text().strip(), self.guide.text().strip(), self.code.text().strip()
        problems = []
        if not self.title.text().strip():
            problems.append("Enter a title.")
        if not (a and Path(a).exists()):
            problems.append("Choose the assignment PDF.")
        if not (g and Path(g).exists()):
            problems.append("Choose the instructor guide.")
        if not rows:
            problems.append("Add at least one rubric row.")
        if any(r["max"] <= 0 for r in rows):
            problems.append("Every rubric row needs a maximum above zero.")
        if problems:
            QMessageBox.information(self, "Not ready", "\n".join(problems))
            return
        heads = []
        for line in self.heads.toPlainText().splitlines():
            if "|" in line:
                t, rl = line.split("|", 1)
                heads.append({"text": t.strip(), "row_label": rl.strip()})
        folder = Path(self.folder.text().strip())
        if (folder / "pack.json").exists() and QMessageBox.question(
                self, "Replace?", "This folder already has an assignment. Replace it?") != QMessageBox.Yes:
            return
        build_pack(folder, self._template(), self.title.text().strip(), self.short.text().strip(), Path(a), Path(g),
                   Path(c) if c else None, rows,
                   [x.strip() for x in self.rules.toPlainText().splitlines() if x.strip()],
                   [x.strip() for x in self.alts.toPlainText().splitlines() if x.strip()],
                   heads, self.page_limit.value())
        if self.state.store:
            self.state.set_pack(folder)
        self.saved_folder = folder
        self.accept()
