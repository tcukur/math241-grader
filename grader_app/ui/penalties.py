"""Edit the points of each rubric item and the integrity penalties, and see the effect on every student before
saving.

Reviews store only the level chosen for each item (100%, 75%, ...) and, for findings, the category and the
decision, never points. New numbers therefore apply to all students automatically. Nobody has to re-grade.
The original points are remembered and shown to graders. Feedback pages show only the current points."""
from __future__ import annotations

import copy
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDoubleSpinBox, QHBoxLayout, QHeaderView, QLabel,
                               QMessageBox, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..applog import log as glog
from ..pack import IntegrityCategory, Pack, RubricRow
from ..scoring import compute, fmt
from .state import AppState
from .theme import WrapLabel

COLS = ["Finding", "Points", "Item score cap,\nfull penalty (%)", "Item score cap,\nhalf penalty (%)", "Shown to the student"]


def _spin(value, maximum, allow_none=False):
    s = QDoubleSpinBox()
    s.setDecimals(1)
    s.setRange(-1 if allow_none else 0, maximum)
    s.setSingleStep(1)
    if allow_none:
        s.setSpecialValueText("no cap")
    s.setValue(-1 if value is None and allow_none else (value or 0))
    s.setMinimumWidth(90)
    s.setMaximumHeight(32)
    return s


class PenaltyDialog(QDialog):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.pack: Pack = state.pack
        self.setWindowTitle(f"Points and penalties for {self.pack.title}")
        self.resize(1100, 860)
        lay = QVBoxLayout(self)

        # rubric points --------------------------------------------------------------------------
        h = QLabel("Rubric points")
        h.setObjectName("h2")
        lay.addWidget(h)
        lay.addWidget(WrapLabel(
            "The points each rubric item is worth. The levels graders chose (100%, 75%, ...) stay as they are, and "
            "each score is recalculated from the new points. The AI does not use points, so nothing needs to be "
            "pre-screened again. Feedback pages show only the current points.",
            "muted"))
        self.handout = dict(self.pack.data.get("handout_points") or {})
        self.rtable = QTableWidget(len(self.pack.rubric), 3)
        self.rtable.setHorizontalHeaderLabels(["Rubric item", "Points", "Original"])
        self.rtable.verticalHeader().setVisible(False)
        self.rtable.setSelectionMode(QAbstractItemView.NoSelection)
        self.rtable.setFocusPolicy(Qt.NoFocus)
        rh = self.rtable.horizontalHeader()
        rh.setSectionResizeMode(0, QHeaderView.Stretch)
        rh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        rh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.rwidgets = []
        for i, r in enumerate(self.pack.rubric):
            it = QTableWidgetItem(f"{r.group} · {r.label}" if r.group else r.label)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            self.rtable.setItem(i, 0, it)
            sp = _spin(r.max, 1000)
            sp.valueChanged.connect(self._update_total)
            self.rtable.setCellWidget(i, 1, sp)
            orig = self.handout.get(r.id, r.max)
            o = QTableWidgetItem(fmt(orig))
            o.setFlags(o.flags() & ~Qt.ItemIsEditable)
            self.rtable.setItem(i, 2, o)
            self.rtable.setRowHeight(i, 40)
            self.rwidgets.append((r.id, sp, orig))
        self.rtable.setFixedHeight(self.rtable.horizontalHeader().sizeHint().height() + 40 * max(1, len(self.pack.rubric)) + 4)
        lay.addWidget(self.rtable)
        self.total_label = WrapLabel("")
        self.total_label.setTextFormat(Qt.RichText)
        lay.addWidget(self.total_label)
        self._update_total()

        h = QLabel("Integrity penalties")
        h.setObjectName("h2")
        lay.addWidget(h)
        lay.addWidget(WrapLabel(
            "Points are deducted from the assignment total when a grader confirms a finding (half penalty halves "
            "them). Most findings only take points off. A cap also limits the score of the rubric items the grader "
            "ticks on that finding, whatever level was chosen for them, for example Checks at most 25% when the "
            "reported results are not produced by the submitted code. \"no cap\" means the finding only takes "
            "points off. Changes apply to every student "
            "already graded in this workspace, because grades store the finding and the decision, not the points. "
            "Press Preview to see who is affected by any change on this page before saving.", "muted"))
        if state.is_ta:
            lay.addWidget(WrapLabel("<b>Note:</b> these numbers should be the same for every grader. Agree changes "
                                    "with the instructor and share the updated assignment folder."))

        self.table = QTableWidget(len(self.pack.categories), len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for c in (1, 2, 3):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        self.widgets = []
        total = max(self.pack.total_max, 1000)
        for i, c in enumerate(self.pack.categories):
            it = QTableWidgetItem(c.label)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            it.setToolTip(c.description)
            self.table.setItem(i, 0, it)
            pts = _spin(c.points, total)
            full = _spin(c.row_cap_pct, 100, allow_none=True)
            half = _spin(c.half_row_cap_pct, 100, allow_none=True)
            self.table.setCellWidget(i, 1, pts)
            self.table.setCellWidget(i, 2, full)
            self.table.setCellWidget(i, 3, half)
            txt = QTableWidgetItem(c.student_text)
            self.table.setItem(i, 4, txt)
            self.widgets.append((c.id, pts, full, half))
        self.table.setWordWrap(True)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(46)
        for i in range(self.table.rowCount()):
            self.table.setRowHeight(i, 46)
        self.table.setFocusPolicy(Qt.NoFocus)
        lay.addWidget(self.table, 3)

        cap_row = QHBoxLayout()
        cap_row.addWidget(QLabel("Maximum total deduction per student"))
        self.cap = _spin(self.pack.integrity_cap or total, total)
        cap_row.addWidget(self.cap)
        cap_row.addStretch(1)
        lay.addLayout(cap_row)

        self.preview_box = QPlainTextEdit()
        self.preview_box.setReadOnly(True)
        self.preview_box.setPlaceholderText("Press Preview to list the students whose totals would change.")
        lay.addWidget(self.preview_box, 1)

        b = QHBoxLayout()
        pv = QPushButton("Preview")
        pv.clicked.connect(self.preview)
        b.addWidget(pv)
        b.addStretch(1)
        c = QPushButton("Cancel")
        c.clicked.connect(self.reject)
        b.addWidget(c)
        ok = QPushButton("Save and apply to all students")
        ok.setObjectName("primary")
        ok.clicked.connect(self.save)
        b.addWidget(ok)
        lay.addLayout(b)

    # -------------------------------------------------------------------------
    def _update_total(self, *_):
        new = sum(sp.value() for _, sp, _ in self.rwidgets)
        orig = sum(o for _, _, o in self.rwidgets)
        txt = f"Total: <b>{fmt(new)}</b> points"
        if abs(new - orig) > 1e-9:
            txt += (f" <span style='color:#c0392b'>The original total was {fmt(orig)}. If the Moodle grade is out of "
                    f"{fmt(orig)}, move points between items so the total stays the same, or change the maximum "
                    "grade in Moodle too.</span>")
        self.total_label.setText(txt)

    def _new_data(self) -> dict:
        data = copy.deepcopy(self.pack.data)
        handout = dict(data.get("handout_points") or {})
        for row in data["rubric"]:
            rid = row["id"]
            new = next(round(sp.value(), 1) for i, sp, _ in self.rwidgets if i == rid)
            if new != row["max"] and rid not in handout:
                handout[rid] = row["max"]           # first change: remember the original points
            row["max"] = new
        handout = {k: v for k, v in handout.items()
                   if any(r["id"] == k and r["max"] != v for r in data["rubric"])}   # back to the original: forget
        if handout:
            data["handout_points"] = handout
        else:
            data.pop("handout_points", None)
        cats = {c["id"]: c for c in data["integrity"]["categories"]}
        for i, (cid, pts, full, half) in enumerate(self.widgets):
            c = cats[cid]
            c["points"] = round(pts.value(), 1)
            c["row_cap_pct"] = None if full.value() < 0 else round(full.value(), 1)
            c["half_row_cap_pct"] = None if half.value() < 0 else round(half.value(), 1)
            c["student_text"] = self.table.item(i, 4).text().strip() or c["label"]
        data["integrity"]["total_cap"] = round(self.cap.value(), 1)
        return data

    def _pack_with(self, data: dict) -> Pack:
        p = copy.copy(self.pack)
        p.data = data
        p.rubric = [RubricRow(**r) for r in data["rubric"]]
        p.categories = []
        for c in data["integrity"]["categories"]:
            p.categories.append(IntegrityCategory(
                id=c["id"], label=c["label"], description=c.get("description", ""), points=float(c.get("points", 0)),
                row_cap_pct=c.get("row_cap_pct"), half_row_cap_pct=c.get("half_row_cap_pct"),
                default_rows=list(c.get("default_rows", [])), student_text=c.get("student_text", c["label"])))
        return p

    def changes(self, data: dict) -> list[tuple[str, float, float]]:
        new_pack = self._pack_with(data)
        out = []
        for r in self.state.store.submissions():
            rev = self.state.store.review(r["sub_id"])
            if not rev:
                continue
            before, after = compute(self.pack, rev), compute(new_pack, rev)
            if abs(before["total"] - after["total"]) > 1e-9 or before["complete"] != after["complete"]:
                out.append((r["name"] or r["sub_id"], before["total"], after["total"],
                            bool(rev.get("reviewed"))))
        return out

    def preview(self):
        ch = self.changes(self._new_data())
        if not ch:
            self.preview_box.setPlainText("No graded student's total would change.")
            return
        lines = [f"{len(ch)} students' totals would change:"]
        for name, b, a, reviewed in sorted(ch):
            lines.append(f"  {name}: {fmt(b)} -> {fmt(a)}" + ("" if reviewed else "  (not yet marked reviewed)"))
        self.preview_box.setPlainText("\n".join(lines))

    def save(self):
        data = self._new_data()
        ch = self.changes(data)
        if ch and QMessageBox.question(
                self, "Apply to all students?",
                f"{len(ch)} students' totals will change. Feedback PDFs and grade files already exported are not "
                "changed until you export again. Continue?") != QMessageBox.Yes:
            return
        new_total = sum(r["max"] for r in data["rubric"])
        if abs(new_total - self.pack.total_max) > 1e-9 and QMessageBox.question(
                self, "Different total",
                f"The total changes from {fmt(self.pack.total_max)} to {fmt(new_total)} points. Grades sent to "
                f"Moodle will be out of {fmt(new_total)}. Keep this total?") != QMessageBox.Yes:
            return
        self.state.backup("before-penalties")
        glog.info("Points and penalties changed: %s totals changed; points %s; penalties %s", len(ch),
                  {r["id"]: r["max"] for r in data["rubric"]},
                  {c["id"]: c["points"] for c in data["integrity"]["categories"]})
        path = self.pack.folder / "pack.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        log = self.state.meta("penalty_changes", []) or []
        log.append({"by": self.state.meta("reviewer", "") or "", "students_changed": len(ch),
                    "points": {c["id"]: c["points"] for c in data["integrity"]["categories"]},
                    "rubric": {r["id"]: r["max"] for r in data["rubric"]}})
        self.state.set_meta("penalty_changes", log[-50:])
        self.state.reload_pack()
        self.state.reviews_changed.emit()
        self.state.submissions_changed.emit()
        self.accept()
