"""Export: feedback PDFs, Moodle ZIP, grades for Moodle, instructor summary."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
                               QPushButton, QVBoxLayout, QWidget)

from ..applog import log as glog
from ..feedback import export_all
from .state import AppState
from .theme import ACCENT, MUTED, STATUS, WrapLabel
from .overview import OverviewCard
from .widgets import flow


class ExportThread(QThread):
    progress = Signal(int, int)
    done = Signal(dict, str)

    def __init__(self, kwargs):
        super().__init__()
        self.kwargs = kwargs

    def run(self):
        try:
            res = export_all(**self.kwargs, progress=lambda i, n: self.progress.emit(i, n))
            self.done.emit(res, "")
        except Exception as e:  # noqa: BLE001
            self.done.emit({}, f"{type(e).__name__}: {e}")


# small building blocks ----------------------------------------------------------------------------
def card(title: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("card")
    v = QVBoxLayout(f)
    v.setContentsMargins(18, 14, 18, 16)
    v.setSpacing(8)
    t = QLabel(title)
    t.setObjectName("sectiontitle")
    v.addWidget(t)
    if subtitle:
        v.addWidget(WrapLabel(subtitle, "muted"))
    return f, v


def tile(value: str, label: str, colour: str = "") -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    f.setMinimumWidth(170)
    v = QVBoxLayout(f)
    v.setContentsMargins(16, 10, 16, 10)
    v.setSpacing(0)
    n = QLabel(value)
    n.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {colour or '#0f172a'};")
    v.addWidget(n)
    lb = QLabel(label)
    lb.setObjectName("muted")
    v.addWidget(lb)
    return f


def step(number: int, html: str) -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 2, 0, 2)
    h.setSpacing(10)
    b = QLabel(str(number))
    b.setObjectName("stepbadge")
    b.setAlignment(Qt.AlignCenter)
    b.setFixedSize(24, 24)
    h.addWidget(b, 0, Qt.AlignTop)
    t = WrapLabel(html)
    t.setTextFormat(Qt.RichText)
    h.addWidget(t, 1)
    return w


def clear(layout):
    while layout.count():
        it = layout.takeAt(0)
        if it.widget():
            w = it.widget()
            w.hide()              # gone at once, not only when Qt gets round to deleting it
            w.setParent(None)
            w.deleteLater()
        elif it.layout():
            clear(it.layout())


class ExportTab(QWidget):
    open_student = Signal(str)

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(14)
        t = QLabel("Export feedback and grades")
        t.setObjectName("h1")
        lay.addWidget(t)

        # status tiles
        self.tiles = QWidget()
        self.tiles_lay = QHBoxLayout(self.tiles)
        self.tiles_lay.setContentsMargins(0, 0, 0, 0)
        self.tiles_lay.setSpacing(10)
        lay.addWidget(self.tiles)

        # how the grades are spread, with a way to open any student from the plot
        self.overview = OverviewCard()
        self.overview.open_student.connect(self.open_student)
        lay.addWidget(self.overview)

        # export
        ec, ev = card("Export", "Files go to the export folder inside the workspace. Exporting again replaces "
                                "the earlier files, so export whenever grading changes.")
        self.only_reviewed = QCheckBox("Only students marked as reviewed")
        self.only_reviewed.setChecked(True)
        ev.addWidget(self.only_reviewed)
        self.only_regrades = QCheckBox("")
        self.only_regrades.setVisible(False)
        ev.addWidget(self.only_regrades)
        self.go = QPushButton("Export")
        self.go.setObjectName("primary")
        self.go.clicked.connect(self.export)
        self.open_btn = QPushButton("Open export folder")
        self.open_btn.clicked.connect(
            lambda: self.state.workspace and QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.out_dir()))))
        ev.addWidget(flow(self.go, self.open_btn))
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        ev.addWidget(self.bar)
        self.status = WrapLabel("")
        self.status.setTextFormat(Qt.RichText)
        ev.addWidget(self.status)
        lay.addWidget(ec)

        # files written (filled after an export)
        self.files_card, fv = card("Files written")
        self.files_grid = QGridLayout()
        self.files_grid.setHorizontalSpacing(18)
        self.files_grid.setVerticalSpacing(8)
        self.files_grid.setColumnStretch(1, 1)
        fv.addLayout(self.files_grid)
        self.files_card.setVisible(False)
        lay.addWidget(self.files_card)

        # AI compared with the grading (filled after an export)
        self.ai_card, av = card(
            "How the AI compared with the grading",
            "For students marked as reviewed. <b>Missed</b>: the AI saw no problem but the grader gave 50% or "
            "less. <b>False alarm</b>: the AI said <i>likely problem</i> but the grader gave 100%. Low numbers in "
            "both columns mean the pre-screen was pointing the right way.")
        self.ai_grid = QGridLayout()
        self.ai_grid.setHorizontalSpacing(22)
        self.ai_grid.setVerticalSpacing(6)
        self.ai_grid.setColumnStretch(0, 1)
        av.addLayout(self.ai_grid)
        self.ai_integ = WrapLabel("")
        self.ai_integ.setTextFormat(Qt.RichText)
        av.addWidget(self.ai_integ)
        self.ai_card.setVisible(False)
        lay.addWidget(self.ai_card)

        # Moodle steps
        mc, self.moodle_lay = card("Upload to Moodle")
        lay.addWidget(mc)
        lay.addStretch(1)

        state.workspace_changed.connect(self.refresh)
        state.reviews_changed.connect(self.refresh)
        state.submissions_changed.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------------------------------------
    def _grades_target(self) -> tuple[str, str]:
        """(tile text, Moodle step text) for where the grades go."""
        ws = self.state.meta("worksheet_path")
        kind = ""
        if ws and Path(ws).exists():
            try:
                from ..moodle import read_class_list
                kind = read_class_list(Path(ws))["kind"]
            except Exception:  # noqa: BLE001
                kind = ""
        if kind == "roster":
            return ("Gradebook CSV", "<b>Grades.</b> In the course, open <i>Grades › Import › CSV file</i> and "
                    "upload <b>moodle_gradebook_import_….csv</b>. Identify users by <i>ID number</i> and map the "
                    "grade column to this assignment.")
        if kind == "worksheet":
            return ("Grading worksheet", "<b>Grades.</b> In the assignment, choose <i>Upload grading worksheet</i> "
                    "and upload <b>…_graded.csv</b>.")
        return ("Grades table only", "<b>Grades.</b> No class list is chosen, so no Moodle grade file is made. "
                "The grades are in <b>grades_detailed.csv</b>. Choose the gradebook export on the Setup tab to get "
                "a file Moodle can import.")

    def refresh(self):
        st = self.state
        clear(self.tiles_lay)
        clear(self._moodle_body())
        if not st.ready:
            self.tiles_lay.addWidget(QLabel("Open a workspace on the Setup tab first."))
            self.tiles_lay.addStretch(1)
            self.go.setEnabled(False)
            self.open_btn.setEnabled(False)
            self.overview.hide()
            return
        self.go.setEnabled(True)
        self.open_btn.setEnabled(True)
        self.overview.show()
        from .. import regrade
        pending = [s["sub_id"] for s in st.store.submissions() if regrade.not_exported(st.store, s["sub_id"])]
        self.only_regrades.setVisible(bool(pending))
        if not pending:
            self.only_regrades.setChecked(False)
        self.only_regrades.setText(
            f"Only the {len(pending)} {'student' if len(pending) == 1 else 'students'} with a finished regrade "
            "request not exported yet (written to a separate regrades folder)")
        try:
            self.overview.refresh(st)
        except Exception:  # noqa: BLE001
            glog.exception("Grade overview could not be drawn")
        c = st.store.counts()
        total, reviewed = c.get("total", 0), c.get("reviewed", 0)
        left = total - reviewed
        target, grade_step = self._grades_target()
        self.tiles_lay.addWidget(tile(f"{reviewed} of {total}", "students reviewed",
                                      STATUS["green"][0] if total and not left else ""))
        self.tiles_lay.addWidget(tile(str(left), "not reviewed yet", STATUS["yellow"][0] if left else ""))
        self.tiles_lay.addWidget(tile(target, "where the grades go", ACCENT))
        self.tiles_lay.addStretch(1)
        body = self._moodle_body()
        for k, html in enumerate([
                "<b>Feedback.</b> In the assignment, open <i>View all submissions</i>, choose <i>Upload multiple "
                "feedback files in a zip</i> and upload <b>moodle_feedback_files.zip</b>. Each student receives "
                "only their own PDF.", grade_step,
                "<b>First time?</b> Try it with one test student. Keep Moodle's own advanced grading (rubric or "
                "marking guide) switched off for this assignment, since it blocks uploads."], 1):
            body.addWidget(step(k, html))

    def _moodle_body(self) -> QVBoxLayout:
        if not hasattr(self, "_mbody"):
            self._mbody = QVBoxLayout()
            self._mbody.setSpacing(6)
            self.moodle_lay.addLayout(self._mbody)
        return self._mbody

    def out_dir(self) -> Path:
        d = self.state.workspace / "export"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def export(self):
        st = self.state
        subs = [dict(r) for r in st.store.submissions()]
        reviews = {s["sub_id"]: st.store.review(s["sub_id"]) for s in subs}
        reviews = {k: v for k, v in reviews.items() if v}
        if self.only_reviewed.isChecked() and not any(v.get("reviewed") for v in reviews.values()):
            QMessageBox.information(self, "Nothing to export", "No student is marked as reviewed yet.")
            return
        from .. import regrade
        for sid, rv in reviews.items():
            reqs = regrade.requests(st.store, sid)
            rv["regrade_all"] = reqs
            rv["regrade"] = [r for r in reqs if r.get("closed_at")]
        ws = st.meta("worksheet_path")
        out, only_ids = self.out_dir(), None
        if self.only_regrades.isVisible() and self.only_regrades.isChecked():
            import datetime as _dt
            only_ids = {s["sub_id"] for s in subs if regrade.not_exported(st.store, s["sub_id"])}
            out = out / ("regrades_" + _dt.datetime.now().strftime("%Y-%m-%d_%H%M"))
        kwargs = dict(pack=st.pack, subs=subs, reviews=reviews, out_dir=out,
                      grader=st.meta("reviewer", "") or "", worksheet_path=Path(ws) if ws else None,
                      only_reviewed=self.only_reviewed.isChecked(), only_ids=only_ids)
        self._export_dir = out
        self.go.setEnabled(False)
        self.bar.setVisible(True)
        self.bar.setRange(0, len(subs))
        self.bar.setValue(0)
        self.status.setText("Exporting…")
        glog.info("Export started to %s (%s)", out, "regraded students only" if only_ids is not None else
                  ("reviewed students" if self.only_reviewed.isChecked() else "all students"))
        self.th = ExportThread(kwargs)
        self.th.progress.connect(lambda i, n: self.bar.setValue(i))
        self.th.done.connect(self.done)
        self.th.start()

    def done(self, res: dict, err: str):
        self.go.setEnabled(True)
        self.bar.setVisible(False)
        if err:
            glog.error("Export failed: %s", err)
            self.status.setText(f"<span style='color:{STATUS['red'][0]}'><b>Export failed.</b> {err}</span>")
            QMessageBox.warning(self, "Export failed", err)
            return
        n_pdf, n_skip = len(res["written"]), len(res["skipped"])
        glog.info("Export finished: %s feedback PDFs, %s left out, grades file: %s", n_pdf, n_skip,
                  res.get("grades_kind") or "table only")
        from .. import regrade
        for sid in res["written"]:
            regrade.mark_exported(self.state.store, sid)
        sub_dir = getattr(self, "_export_dir", None)
        if sub_dir is not None and sub_dir != self.out_dir():
            self.status.setText(f"<span style='color:{STATUS['green'][0]}'><b>✓ Exported</b></span> "
                                f"{n_pdf} regraded {'student' if n_pdf == 1 else 'students'} to the folder "
                                f"<b>export/{sub_dir.name}</b>. Upload its ZIP and grade file to Moodle the same "
                                "way. Only these students are changed there.")
        else:
            self.status.setText(f"<span style='color:{STATUS['green'][0]}'><b>✓ Exported</b></span> "
                                f"{n_pdf} feedback {'PDF' if n_pdf == 1 else 'PDFs'}"
                                + (f". {n_skip} not-reviewed {'student was' if n_skip == 1 else 'students were'} "
                                   "left out." if n_skip else "."))
        self.refresh()
        self._show_files(res)
        self._show_agreement(res.get("agreement") or {})

    def _show_files(self, res: dict):
        clear(self.files_grid)
        rows = [(Path(res["zip"]).name, "Feedback PDFs packed for Moodle's <i>Upload multiple feedback files</i>.",
                 "Moodle")]
        if res.get("worksheet"):
            rows.append((Path(res["worksheet"]).name, res.get("worksheet_note", ""), "Moodle"))
        rows += [
            (Path(res["pdf_dir"]).name + "/", f"{len(res['written'])} feedback PDFs, one per student: a cover page "
             "with scores, comments and findings, then the original submission.", "Students"),
            (Path(res["grades_csv"]).name, "Every score, deduction and total, one row per student.", "Your records"),
            (Path(res["findings_csv"]).name, "All integrity findings with the graders' decisions and comments.",
             "Instructor"),
        ]
        if res.get("regrade_csv"):
            rows.append((Path(res["regrade_csv"]).name, "Every regrade request with the reply, the grade before "
                         "and after, and what changed.", "Instructor"))
        ag = res.get("agreement") or {}
        if ag.get("csv"):
            rows.append((Path(ag["csv"]).name, "Row-by-row comparison of the AI pre-screen with the final grades.",
                         "Instructor"))
        for i, (name, what, who) in enumerate(rows):
            n = QLabel(f"<b>{name}</b>")
            n.setTextInteractionFlags(Qt.TextSelectableByMouse)
            w = WrapLabel(what)
            w.setTextFormat(Qt.RichText)
            tag = QLabel(who)
            colour = ACCENT if who == "Moodle" else MUTED
            tag.setStyleSheet(f"color: {colour}; background: #f1f4f9; border-radius: 9px; padding: 2px 9px; "
                              "font-size: 12px; font-weight: 600;")
            self.files_grid.addWidget(n, i, 0, Qt.AlignTop)
            self.files_grid.addWidget(w, i, 1)
            self.files_grid.addWidget(tag, i, 2, Qt.AlignTop | Qt.AlignRight)
        self.files_card.setVisible(True)

    def _show_agreement(self, ag: dict):
        clear(self.ai_grid)
        if not ag.get("students"):
            self.ai_card.setVisible(False)
            return
        heads = ["Rubric item", "Flagged by the AI", "Missed", "False alarms", "AI unsure"]
        for j, h in enumerate(heads):
            lb = QLabel(h)
            lb.setStyleSheet(f"color: {MUTED}; font-weight: 600;")
            self.ai_grid.addWidget(lb, 0, j, Qt.AlignLeft if j == 0 else Qt.AlignRight)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: #e3e7ee;")
        self.ai_grid.addWidget(line, 1, 0, 1, len(heads))
        for i, r in enumerate(ag.get("rows", []), 2):
            n = r["n"]
            cells = [r["label"], f"{r['flagged']} of {n}", str(r["missed"]), str(r["false_alarm"]),
                     str(r["low_conf"])]
            for j, v in enumerate(cells):
                lb = QLabel(v)
                if j == 2 and r["missed"]:
                    lb.setStyleSheet(f"color: {STATUS['red'][0]}; font-weight: 600;")
                elif j == 3 and r["false_alarm"]:
                    lb.setStyleSheet(f"color: {STATUS['yellow'][0]}; font-weight: 600;")
                self.ai_grid.addWidget(lb, i, j, Qt.AlignLeft if j == 0 else Qt.AlignRight)
        integ = ag.get("integrity") or {}
        if integ.get("ai_findings") or integ.get("ta_added"):
            self.ai_integ.setText(
                f"<b>Integrity findings.</b> The AI raised {integ.get('ai_findings', 0)}: "
                f"{integ.get('confirmed', 0)} confirmed by the graders and {integ.get('rejected', 0)} rejected. "
                f"The graders added {integ.get('ta_added', 0)} of their own.")
        else:
            self.ai_integ.setText("")
        self.ai_card.setVisible(True)
