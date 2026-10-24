"""Pre-screen: run the automatic checks and the AI pre-screen with progress."""
from __future__ import annotations

import html

import json

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QAbstractItemView, QCheckBox, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QSpinBox, QSplitter, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..applog import log as glog
from ..dates import stamp
from ..pipeline import BatchRunner
from .state import AppState
from .live import LivePanel
from .theme import STATUS, WrapLabel
from .widgets import flow


class RunThread(QThread):
    progress = Signal(str, str, str)
    stage = Signal(str, str, float)     # student, step, when it started (time.monotonic in the worker)
    finished_at = Signal(str, float)

    def __init__(self, runner: BatchRunner):
        super().__init__()
        self.runner = runner

    def run(self):
        import time

        def progress(sid, state, msg):
            self.finished_at.emit(sid, time.monotonic())
            self.progress.emit(sid, state, msg)
        self.runner.run(progress, on_stage=lambda sid, name: self.stage.emit(sid, name, time.monotonic()))


class _StatusLine:
    """Stands in for the old log box: shows a message on the progress box's status line."""

    def __init__(self, live):
        self.live = live

    def appendPlainText(self, text: str):
        try:
            self.live.summary.setText(text)
            print(text)
        except Exception:  # noqa: BLE001
            pass


class RunTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.thread: RunThread | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(12)

        t = QLabel("Pre-screen submissions")
        t.setObjectName("h1")
        lay.addWidget(t)
        self.summary = WrapLabel("", "muted")
        lay.addWidget(self.summary)

        opts_items = []
        self.dry = QCheckBox("Automatic checks only (no AI, free)")
        self.dry.setToolTip("Runs extraction and pattern checks without calling the AI. "
                            "A later full run replaces these results.")
        opts_items.append(self.dry)
        opts_items.append(QLabel("Parallel workers:"))
        self.workers = QSpinBox()
        self.workers.setRange(1, 8)
        self.workers.setValue(4)
        opts_items.append(self.workers)
        opts_items.append(QLabel("Model:"))
        self.model_box = QComboBox()
        self.model_box.setToolTip("The AI model for this run. Re-runs requested from Review keep their own choice.")
        self.model_box.currentIndexChanged.connect(lambda _i: self.refresh())
        opts_items.append(self.model_box)
        opts_items.append(QLabel("Effort:"))
        from .effort import effort_box
        self.effort_box = effort_box("medium")
        self.effort_box.currentIndexChanged.connect(lambda _i: self.refresh())
        opts_items.append(self.effort_box)
        self.start_btn = QPushButton("Start")
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self.start)
        opts_items.append(self.start_btn)
        self.stop_btn = QPushButton("Pause")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop)
        opts_items.append(self.stop_btn)
        self.redo_btn = QPushButton("Re-screen selected")
        self.redo_btn.clicked.connect(self.redo_selected)
        opts_items.append(self.redo_btn)
        lay.addWidget(flow(*opts_items))

        note_row = QHBoxLayout()
        nl = QVBoxLayout()
        lbl = QLabel("Note to the AI for every submission (optional)")
        lbl.setObjectName("h2")
        nl.addWidget(lbl)
        self.instr_btn = QPushButton("AI instructions…")
        self.instr_btn.setToolTip("See, and as the instructor change, the instructions the AI follows for every "
                                  "student, and the full prompt for one student")
        self.instr_btn.clicked.connect(self.open_instructions)
        nl.addWidget(flow(self.instr_btn))
        hint = QLabel("Use this for issues that apply to the whole class, for example \"Many students give the "
                      "voltage map as a table; that is acceptable.\" It is added to every prompt from the next "
                      "run on, and saving it offers to re-screen the students already done.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        nl.addWidget(hint)
        note_row.addLayout(nl, 2)
        self.global_note = QPlainTextEdit()
        self.global_note.setMaximumHeight(70)
        self.global_note.setPlaceholderText("No class-wide note")
        note_row.addWidget(self.global_note, 3)
        save_note = QPushButton("Save note")
        save_note.clicked.connect(self.save_global_note)
        note_row.addWidget(save_note, 0, Qt.AlignTop)
        lay.addLayout(note_row)

        self.bar = QProgressBar()
        self.bar.setFormat("%v of %m")
        lay.addWidget(self.bar)

        # which class-wide prompt the results were made with
        pr_row = QHBoxLayout()
        self.prompt_label = WrapLabel("", "muted")
        self.prompt_label.setTextFormat(Qt.RichText)
        pr_row.addWidget(self.prompt_label, 1)
        self.rescreen_btn = QPushButton("Re-screen them")
        self.rescreen_btn.setToolTip("Pre-screen these students again with the current instructions and note. "
                                     "Grading already done is kept.")
        self.rescreen_btn.clicked.connect(self.rescreen_outdated)
        pr_row.addWidget(self.rescreen_btn, 0, Qt.AlignTop)
        lay.addLayout(pr_row)

        # similar work: checked on this computer when a run finishes, results become findings in Review
        sim_row = QHBoxLayout()
        self.sim_label = WrapLabel("", "muted")
        self.sim_label.setTextFormat(Qt.RichText)
        sim_row.addWidget(self.sim_label, 1)
        self.sim_btn = QPushButton("Check for similar work now")
        self.sim_btn.setToolTip("Compare every pair of submissions for long identical passages, on this computer "
                                "and without the AI. This also runs by itself when a pre-screen run finishes.")
        self.sim_btn.clicked.connect(self.check_similar)
        sim_row.addWidget(self.sim_btn, 0, Qt.AlignTop)
        lay.addLayout(sim_row)
        self.sim_thread = None

        split = QSplitter(Qt.Vertical)
        self.live = LivePanel()
        self.live.setMinimumHeight(150)
        split.addWidget(self.live)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Student", "Status", "Rows to check", "Integrity findings", "Note"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        split.addWidget(self.table)
        # one-off messages ("Nothing to do", "Pausing…") go to the status line of the progress box,
        # and to the log file
        self.log = _StatusLine(self.live)
        self.table.setMinimumHeight(220)
        split.setSizes([180, 520])
        split.setChildrenCollapsible(False)
        lay.addWidget(split, 1)

        state.submissions_changed.connect(self.refresh)
        state.workspace_changed.connect(self.refresh)
        self.refresh()

    def _fit_summary(self):
        # the summary wraps to one or more lines; reserve exactly the height it needs at the current width
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QFontMetrics
        w = max(300, self.width() - 60)
        text = self.summary.text()
        h = QFontMetrics(self.summary.font()).boundingRect(QRect(0, 0, w, 100000), Qt.TextWordWrap, text).height()
        self.summary.setMinimumHeight(h + 10 if text else 0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit_summary()

    def refresh(self):
        try:
            if self.sim_thread is None:
                self._show_similar()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._fill_models()
            self._fill_effort_default()
            self._show_prompt_state()
        except Exception:  # noqa: BLE001
            pass
        self._refresh()

    # model and class-wide prompt -------------------------------------------------------------------
    def _fill_models(self):
        st = self.state
        if not st.pack:
            return
        mc = st.pack.model
        labels = {mc.get("name"): mc.get("label", mc.get("name")),
                  mc.get("escalation_name"): mc.get("escalation_label", mc.get("escalation_name"))}
        models = st.allowed_models() or [mc.get("name", "")]
        have = [self.model_box.itemData(i) for i in range(self.model_box.count())]
        if have != models:
            cur = self.model_box.currentData()
            self.model_box.blockSignals(True)
            self.model_box.clear()
            for m in models:
                self.model_box.addItem(labels.get(m) or m, m)
            self.model_box.setCurrentIndex(max(0, self.model_box.findData(cur)))
            self.model_box.blockSignals(False)

    def chosen_model(self) -> str | None:
        return self.model_box.currentData() or None

    def chosen_effort(self) -> str | None:
        return self.effort_box.currentData() or None

    def _fill_effort_default(self):
        """Mark the assignment's own default level, once per assignment."""
        st = self.state
        default = (st.pack.model or {}).get("reasoning_effort") or "medium" if st.pack else "medium"
        if getattr(self, "_effort_default", None) == default:
            return
        self._effort_default = default
        from .effort import LEVELS
        self.effort_box.blockSignals(True)
        for i, (key, label) in enumerate(LEVELS):
            self.effort_box.setItemText(i, label + (" (default)" if key == default else ""))
        self.effort_box.setCurrentIndex(max(0, self.effort_box.findData(default)))
        self.effort_box.blockSignals(False)

    def _show_prompt_state(self):
        st = self.state
        from ..pipeline import current_prompt_version, outdated_students
        from .instructions import version_label
        if not st.ready:
            self.prompt_label.setText("")
            self.rescreen_btn.setVisible(False)
            return
        cur = current_prompt_version(st.store)
        old = outdated_students(st.store)
        notes = sum(1 for r in st.store.submissions() if (r["ta_note"] or "").strip())
        parts = []
        if (st.meta("ai_instructions", "") or "").strip():
            parts.append("edited AI instructions")
        if (st.meta("global_note", "") or "").strip():
            parts.append("the class-wide note")
        txt = (f"<b>Prompt:</b> {version_label(st, cur)}" + (f" ({' and '.join(parts)})" if parts else "") + ".")
        if notes:
            txt += (f" {notes} {'student has' if notes == 1 else 'students have'} their own note from Review, "
                    "added for that student only.")
        if old:
            from ..cost import estimate_run, money
            est = estimate_run(st.store, st.pack, self.chosen_model(), ids=old, effort=self.chosen_effort())
            who = "student was" if len(old) == 1 else "students were"
            txt += (f" <b style='color:{STATUS['yellow'][0]}'>{len(old)} {who} pre-screened with earlier "
                    f"instructions or note.</b> Re-screening them costs {money(est['cost'])}.")
        self.prompt_label.setText(txt)
        self.rescreen_btn.setVisible(bool(old) and not st.is_ta)

    def open_instructions(self):
        if not self.state.ready:
            QMessageBox.information(self, "No assignment", "Open a workspace with an assignment first.")
            return
        from .instructions import InstructionsDialog
        dlg = InstructionsDialog(self.state, self)
        dlg.exec()
        if dlg.saved:
            self._prompt_changed()

    def _prompt_changed(self):
        """The instructions or the class-wide note changed: offer to bring every student up to date."""
        from ..pipeline import outdated_students
        self.refresh()
        old = outdated_students(self.state.store)
        if not old:
            return
        from ..cost import estimate_run, money
        est = estimate_run(self.state.store, self.state.pack, self.chosen_model(), ids=old,
                           effort=self.chosen_effort())
        if QMessageBox.question(
                self, "Re-screen with the new prompt?",
                f"{len(old)} students were pre-screened with the earlier prompt. Re-screen all of them now, so "
                f"every result comes from the same prompt? This costs {money(est['cost'])}.\n\nGrading already "
                "done is kept. Students you already graded are marked to check again.\n\nIf you choose No, they "
                "stay listed here with a Re-screen them button.") == QMessageBox.Yes:
            self.rescreen_outdated()

    def rescreen_outdated(self):
        from ..pipeline import outdated_students, queue_rescreen
        old = outdated_students(self.state.store)
        if not old:
            return
        queue_rescreen(self.state.store, old)
        glog.info("Re-screen queued for %s students with an earlier prompt", len(old))
        self.refresh()
        self.dry.setChecked(False)
        self.start()

    def _refresh(self):
        self._refresh()
        self._fit_summary()

    def _refresh(self):
        st = self.state
        if not st.ready:
            self.summary.setText("Open a workspace and choose an assignment on the Setup tab first.")
            self.table.setRowCount(0)
            self.start_btn.setEnabled(False)
            return
        ta = st.is_ta
        self.start_btn.setEnabled(self.thread is None and not ta)
        for w in (self.dry, self.workers, self.redo_btn):
            w.setEnabled(not ta)
        self.global_note.setReadOnly(ta)
        if not self.global_note.hasFocus():
            self.global_note.setPlainText(st.meta("global_note", "") or "")
        rows = st.store.submissions()
        c = st.store.counts()
        tok = ""
        if c.get("input_tokens"):
            cached = 0
            for r in rows:
                try:
                    cached += int((json.loads(r["screen"]) if r["screen"] else {}).get("_meta", {})
                                  .get("cached_tokens") or 0)
                except Exception:  # noqa: BLE001
                    pass
            tok = (f" Tokens used so far: {c['input_tokens']:,} in"
                   + (f" ({cached:,} of them repeated material billed at the lower cached rate)" if cached else "")
                   + f", {c['output_tokens']:,} out.")
        req = c.get("rerun_requests", 0)
        try:
            from ..cost import estimate_run, money, spent
            est, so_far = (estimate_run(st.store, st.pack, self.chosen_model(), effort=self.chosen_effort()),
                           spent(st.store, st.pack))
            if so_far is not None:
                tok += f" Spent on the AI so far: {money(so_far)}."
            if est["n"] and est["cost"] is not None:
                basis = (f"the {est['basis']} {'student' if est['basis'] == 1 else 'students'} done so far"
                         if est["basis"] else "a first guess until a few students are done")
                tok += (f" Start would send {est['n']} {'student' if est['n'] == 1 else 'students'} to the AI, "
                        f"{money(est['cost'])} (estimate based on {basis}).")
        except Exception:  # noqa: BLE001
            pass
        if ta:
            self.summary.setText(
                f"{st.pack.title}. {c.get('total', 0)} submissions in this package. The instructor runs the AI "
                f"pre-screen. {req} re-run request(s) of yours are waiting to be sent with your return file.")
        else:
            self.summary.setText(
            (f"{req} re-run request(s) from TAs are waiting, and Start processes them. " if req else "") +
            f"{st.pack.title}. {c.get('total', 0)} submissions: {c.get('screened', 0)} pre-screened, "
            f"{c.get('error', 0)} with errors, {c.get('new', 0) + c.get('extracted', 0)} waiting.{tok} "
            "Finished students are saved immediately, so you can pause or close the app and continue later.")
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            name = r["name"] or r["sub_id"]
            screen = json.loads(r["screen"]) if r["screen"] else None
            flagged = integ = integ_tip = ""
            if screen:
                n = sum(1 for x in screen["rows"] if x["status"] in ("yellow", "red"))
                red = sum(1 for x in screen["rows"] if x["status"] == "red")
                flagged = f"{n}" + (f" ({red} red)" if red else "")
                integ, integ_tip = self._integrity_count(r, screen)
            status = r["status"]
            if status == "screened" and screen and screen.get("_meta", {}).get("model") == "offline":
                status = "checks only"
            if r["rerun_requested"]:
                status += " · re-run requested" + (f" ({r['rerun_model']})" if r["rerun_model"] else "")
            items = [QTableWidgetItem(f"{name}  ({r['sub_id']})"), QTableWidgetItem(status),
                     QTableWidgetItem(flagged), QTableWidgetItem(integ),
                     QTableWidgetItem(r["error"] or r["note"] or "")]
            if screen:
                items[3].setToolTip(integ_tip)
            if r["status"] == "error":
                items[1].setForeground(QColor(STATUS["red"][0]))
            if integ and integ != "0":
                items[3].setForeground(QColor(STATUS["red"][0]))
            items[0].setData(Qt.UserRole, r["sub_id"])
            for j, it in enumerate(items):
                self.table.setItem(i, j, it)

    def start(self):
        st = self.state
        key = st.api_key()
        if not self.dry.isChecked() and not key:
            QMessageBox.information(self, "API key needed",
                                    "Save an OpenAI API key on the Setup tab, or tick 'Automatic checks only'.")
            return
        try:
            default = (st.pack.model or {}).get("name")
            chosen = self.chosen_model()
            runner = BatchRunner(st.store, st.pack, key, dry_run=self.dry.isChecked(),
                                 workers=self.workers.value(), model=chosen if chosen != default else None,
                                 effort=self.chosen_effort())
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Could not start", str(e))
            return
        todo = runner.pending()
        if not todo:
            self.log.appendPlainText("Nothing to do: every submission is already pre-screened.")
            return
        self.done_count = 0
        self.bar.setRange(0, len(todo))
        self.bar.setValue(0)
        self.log.appendPlainText(f"Starting {'automatic checks' if self.dry.isChecked() else 'AI pre-screen'} "
                                 f"for {len(todo)} submissions…")
        self.live.begin(self.workers.value(), self.dry.isChecked(), len(todo))
        from ..pipeline import current_prompt_version
        glog.info("Pre-screen run started: %s students, %s, model %s, effort %s, %s workers, prompt %s", len(todo),
                  "automatic checks only" if self.dry.isChecked() else "AI", runner.model or "default",
                  runner.effort or "default", self.workers.value(), current_prompt_version(st.store))
        self.thread = RunThread(runner)
        self.thread.progress.connect(self.on_progress)
        self.thread.stage.connect(self.on_stage)
        self.thread.finished_at.connect(lambda sid, t: self.live.note_finish_time(sid, t))
        self.thread.finished.connect(self.on_finished)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.thread.start()

    def on_stage(self, sid, stage, when=None):
        try:
            from ..pipeline import STAGES
            row = self.state.store.submission(sid)
            name = (row["name"] if row else "") or sid
            self.live.stage(sid, name, f"{name} ({sid})", stage, when)
            label = STAGES.get("ai" if stage.startswith("retry") else stage, stage) + "…"
            for i in range(self.table.rowCount()):
                it = self.table.item(i, 0)
                if it is not None and it.data(Qt.UserRole) == sid:
                    self.table.item(i, 1).setText(label)
                    break
        except Exception:  # noqa: BLE001
            pass   # progress display only

    def on_progress(self, sid, state, msg):
        try:
            self.live.finish(sid, state, msg)
        except Exception:  # noqa: BLE001
            pass
        self.done_count += 1
        self.bar.setValue(self.done_count)
        self.state.student_updated.emit(sid)       # the grading panel shows it if that student is on screen
        row = self.state.store.submission(sid)
        name = (row["name"] if row else "") or sid
        line = f"{name} ({sid}): {state}"
        if msg:
            line += f"  {msg[:300]}"
        print(line)   # to the log file; the progress box and the table show it on screen
        if self.done_count % 3 == 0:
            self.refresh()

    def on_finished(self):
        glog.info("Pre-screen run %s: %s of %s done", "paused" if self.bar.value() < self.bar.maximum() else "finished",
                  self.bar.value(), self.bar.maximum())
        try:
            self.live.end(self.bar.value() < self.bar.maximum())
        except Exception:  # noqa: BLE001
            pass
        self.thread = None
        self.stop_btn.setEnabled(False)
        self.refresh()
        print("Stopped." if self.bar.value() < self.bar.maximum() else "Finished.")
        self.state.submissions_changed.emit()
        if self.bar.value() >= self.bar.maximum():
            self.check_similar(only_if_changed=True)    # every paper is in: look for similar work before grading

    # similar work ------------------------------------------------------------------------------------
    def check_similar(self, only_if_changed: bool = False):
        st = self.state
        if not st.ready or self.sim_thread is not None or len(st.store.submissions()) < 2:
            return
        if only_if_changed:
            from .. import similarity
            last = st.meta(similarity.REPORT_KEY)
            if isinstance(last, dict) and last.get("signature") == similarity.signature(st.store):
                return                    # same submissions as the last check: nothing new to compare
        from .compare import CompareThread
        self.sim_btn.setEnabled(False)
        self.sim_label.setText("<b>Similar work:</b> reading the submissions…")
        glog.info("Similar work check started (%s students)", len(st.store.submissions()))
        self.sim_thread = CompareThread(st)
        self._sim_workspace = st.workspace
        self.sim_thread.progress.connect(lambda stage, i, n: self.sim_label.setText(
            f"<b>Similar work:</b> {'reading submission' if stage == 'read' else 'comparing pair'} {i} of {n}…"))
        self.sim_thread.done.connect(self._similar_done)
        self.sim_thread.start()

    def _similar_done(self, rep: dict, _n: int, err: str):
        self.sim_thread = None
        self.sim_btn.setEnabled(True)
        if err:
            glog.error("Similar work check failed: %s", err)
            self.sim_label.setText(f"<b>Similar work:</b> the check failed ({html.escape(err)}).")
            return
        glog.info("Similar work check done: %s pairs flagged (%s pairs compared)", len(rep.get("pairs", [])),
                  rep.get("pairs_compared"))
        from .compare import save_and_apply
        added = save_and_apply(self.state, rep, workspace=getattr(self, "_sim_workspace", None))
        self._show_similar(added)

    def _show_similar(self, added: int | None = None):
        from .. import similarity
        rep = self.state.meta(similarity.REPORT_KEY) if self.state.ready else None
        if not isinstance(rep, dict) or not rep:
            self.sim_label.setText("<b>Similar work:</b> not checked yet. It runs by itself when a pre-screen run "
                                   "finishes.")
            return
        import datetime as _dt
        when = stamp(rep.get("at", 0), year=False)
        pairs = rep.get("pairs", [])
        if not pairs:
            self.sim_label.setText(f"<b>Similar work:</b> checked {when}, {rep.get('students')} students. No two "
                                   "submissions share long passages.")
            return
        names = ", ".join(f"{html.escape(p['a_name'])} and {html.escape(p['b_name'])}" for p in pairs[:4])
        more = len(pairs) - 4
        self.sim_label.setText(
            f"<b>Similar work:</b> checked {when}. <b style='color:{STATUS['red'][0]}'>{len(pairs)} "
            f"{'pair shares' if len(pairs) == 1 else 'pairs share'} long passages</b>: {names}"
            + (f" and {more} more" if more > 0 else "") + ". Each of these students has a finding to decide in "
            "Review and grade, with Compare side by side."
            + (f" {added} new {'finding' if added == 1 else 'findings'} added." if added else ""))

    def _integrity_count(self, row, screen) -> tuple[str, str]:
        """Integrity findings to decide for this student, counted the way Review and grade lists them: from the AI,
        from the automatic checks, from the similar-work check and added by a grader."""
        rev = self.state.store.review(row["sub_id"])
        if rev is not None:
            fs = rev.get("findings", [])
        else:
            from ..scoring import new_review_from_screen      # what Review will list when the student is opened
            fs = new_review_from_screen(self.state.pack, screen)["findings"]
        parts = {"from the AI": sum(1 for f in fs if f.get("origin") == "ai"),
                 "automatic check": sum(1 for f in fs if f.get("origin") == "auto" and not f.get("similar_pair")),
                 "similar work": sum(1 for f in fs if f.get("similar_pair")),
                 "added by a grader": sum(1 for f in fs if f.get("origin") == "ta")}
        total = sum(parts.values())
        tip = ", ".join(f"{n} {k}" for k, n in parts.items() if n) or "No integrity findings"
        return str(total), tip

    def stop(self):
        if self.thread:
            self.thread.runner.stop()
            self.stop_btn.setEnabled(False)
            self.log.appendPlainText("Pausing after the submissions currently in progress…")

    def save_global_note(self):
        new = self.global_note.toPlainText().strip()
        if new == (self.state.meta("global_note", "") or "").strip():
            return
        self.state.set_meta("global_note", new)
        from .instructions import record_prompt_change
        record_prompt_change(self.state)
        glog.info("Class-wide note changed (%s characters)", len(new))
        self.log.appendPlainText("Class-wide note saved. It applies to submissions pre-screened from now on.")
        self._prompt_changed()

    def redo_selected(self):
        ids = {self.table.item(i.row(), 0).data(Qt.UserRole) for i in self.table.selectionModel().selectedRows()}
        if not ids:
            return
        for sid in ids:
            self.state.store.reset_screen(sid)
        self.log.appendPlainText(f"{len(ids)} submission(s) will be pre-screened again on the next Start.")
        self.refresh()
