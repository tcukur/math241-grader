"""Review: student list, PDF viewer, and the grading panel with AI flags,
rubric levels, integrity findings and a per-student AI re-run."""
from __future__ import annotations

import html
import json
import re
import uuid

from PySide6.QtCore import QPoint, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QTextCursor
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
                               QScrollArea, QSplitter, QTabWidget, QVBoxLayout, QWidget, QApplication, QCompleter,
                               QMenu, QToolButton, QInputDialog, QToolTip)

from ..applog import log as glog
from ..dates import stamp
from ..checks import CheckResult
from ..llm import Screener, build_input, prompt_as_text
from ..pipeline import load_stage, merge_new_screen, process_submission
from .. import regrade
from ..comment_bank import build_bank, hide as bank_hide, insert_text
from ..scoring import DECISIONS, compute, fmt, new_review_from_screen, readiness_problems
from .pdf_view import PdfView
from .state import AppState
from .theme import ACCENT, STATUS, WrapLabel
from .widgets import ClickCard, evidence_block, flow, labelled


RECHECK = "#7c3aed"      # violet: graded before, then the AI pre-screen was run again
REGRADE = "#0f766e"      # teal: an open regrade request
NOFLAG = "noflag"        # white dot: pre-screened, nothing flagged


def list_dot(color: str) -> QIcon:
    return dot_icon("#ffffff", "#94a3b8") if color == NOFLAG else dot_icon(color)


def _bank_icon() -> QIcon:
    """Small list symbol shown inside a comment box that has earlier comments."""
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(ACCENT))
    for y in (8, 15, 22):
        p.drawEllipse(5, y - 1, 4, 4)
        p.drawRoundedRect(12, y, 15, 2.6, 1.3, 1.3)
    p.end()
    return QIcon(pm)


def _day(ts) -> str:
    import datetime as _dt
    return stamp(ts)


def dot_icon(color: str, ring: str | None = None) -> QIcon:
    pm = QPixmap(14, 14)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor(ring) if ring else Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(2, 2, 10, 10)
    p.end()
    return QIcon(pm)


def recheck_banner(note: dict) -> QFrame:
    """Shown on a student whose AI pre-screen was run again after grading had started."""
    import datetime
    box = QFrame()
    box.setObjectName("recheck")
    box.setStyleSheet(f"QFrame#recheck {{ background: #f5f3ff; border: 1px solid #ddd6fe; "
                      f"border-left: 4px solid {RECHECK}; border-radius: 10px; }}")
    v = QVBoxLayout(box)
    v.setContentsMargins(12, 9, 12, 10)
    v.setSpacing(4)
    when = ""
    try:
        when = stamp(float(note.get("at")), year=False)
    except Exception:  # noqa: BLE001
        pass
    head = (f"<b style='color:{RECHECK}'>AI pre-screen run again</b>"
            + (f" <span style='color:#6b7280'>· {when}" + (f" · {note.get('model')}" if note.get("model") else "")
               + "</span>" if when else ""))
    v.addWidget(wrap_label(head))
    parts = ["Your grades, comments and decisions are kept. The AI notes on the cards below are from the new run."]
    changed, new = note.get("changed") or [], note.get("new_findings") or []
    if changed:
        parts.append("<b>The AI now sees these differently:</b><br/>" + "<br/>".join(html.escape(c) for c in changed))
    elif note.get("compared"):
        parts.append("<b>The AI's view of the rubric items did not change.</b>")
    if new:
        parts.append(f"<b>New {'finding' if len(new) == 1 else 'findings'} to decide:</b> "
                     + html.escape(", ".join(new)) + ".")
    elif note.get("compared"):
        parts.append("No new integrity findings.")
    parts.append("Look again where needed, then press <b>Mark reviewed and next</b> to confirm."
                 + (" Until then this student does not count as reviewed." if note.get("was_reviewed") else ""))
    for p in parts:
        lb = wrap_label(p)
        lb.setTextFormat(Qt.RichText)
        v.addWidget(lb)
    return box


def section_header(number: str, title: str, subtitle: str = "", right: QWidget | None = None):
    """A numbered step heading for the grading panel. Returns the widget and its progress chip."""
    box = QWidget()
    v = QVBoxLayout(box)
    v.setContentsMargins(0, 12, 0, 2)
    v.setSpacing(2)
    top = QHBoxLayout()
    top.setSpacing(8)
    badge = QLabel(number)
    badge.setObjectName("stepbadge")
    badge.setAlignment(Qt.AlignCenter)
    badge.setFixedSize(24, 24)
    top.addWidget(badge)
    t = QLabel(title)
    t.setObjectName("sectiontitle")
    top.addWidget(t)
    chip = QLabel("")
    chip.setObjectName("chip")
    chip.setVisible(False)
    top.addWidget(chip)
    top.addStretch(1)
    if right is not None:
        top.addWidget(right)
    v.addLayout(top)
    if subtitle:
        sl = wrap_label(subtitle, "muted")
        sl.setContentsMargins(32, 0, 0, 0)
        v.addWidget(sl)
    return box, chip


def set_chip(chip: QLabel, text: str, done: bool) -> None:
    chip.setText(text)
    chip.setVisible(bool(text))
    fg, bg = (STATUS["green"][0], STATUS["green"][1]) if done else ("#475569", "#eef1f5")
    chip.setStyleSheet(f"QLabel#chip {{ background: {bg}; color: {fg}; border-radius: 10px; padding: 2px 9px; "
                       f"font-weight: 600; }}")


def group_label(text: str) -> QLabel:
    lb = QLabel(text.upper())
    lb.setObjectName("grouplabel")
    try:   # purely cosmetic: a failure here must never stop a student from opening
        from PySide6.QtGui import QFont
        f = lb.font()
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        lb.setFont(f)
    except Exception:  # noqa: BLE001
        pass
    return lb


_ENTITY_RX = re.compile(r"&(?:[a-zA-Z]+|#x?[0-9a-fA-F]+);")


def wrap_label(text: str, obj: str | None = None) -> QLabel:
    lb = QLabel(text)
    if _ENTITY_RX.search(text):
        # escaped text (&quot;, &#x27;, &amp;) must be shown as formatted text, or the codes appear literally
        lb.setTextFormat(Qt.RichText)
    lb.setWordWrap(True)
    lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
    if obj:
        lb.setObjectName(obj)
    return lb


def evidence_label(evidence: list, on_jump) -> QLabel | None:
    """Clickable, wrapping list of evidence links."""
    items = [e for e in evidence if e.get("page")][:5]
    if not items:
        return None
    parts = []
    for k, ev in enumerate(items):
        exc = (ev.get("excerpt") or "").strip()
        txt = f"p.{ev['page']} {ev.get('source', '')}" + (f": “{html.escape(exc[:90])}”" if exc else "")
        parts.append(f"<a href='{k}' style='color:{ACCENT}; text-decoration:none'>{txt}</a>")
    lb = QLabel("<br/>".join(parts))
    lb.setWordWrap(True)
    lb.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
    lb.linkActivated.connect(lambda h: on_jump(int(items[int(h)]["page"]), (items[int(h)].get("excerpt") or "")))
    return lb


# --------------------------------------------------------------------------
class RerunThread(QThread):
    done = Signal(str, bool, str)

    def __init__(self, state: AppState, sub_id: str, dry: bool, model: str | None = None,
                 effort: str | None = None):
        super().__init__()
        self.state, self.sub_id, self.dry, self.model, self.effort = state, sub_id, dry, model, effort

    def run(self):
        try:
            screener = None if self.dry else Screener(self.state.pack, self.state.api_key())
            process_submission(self.state.store, self.state.pack, self.sub_id, screener, self.dry, self.model,
                               effort=self.effort)
            if not self.dry:
                self.state.count_ai_use()
            self.done.emit(self.sub_id, True, "")
        except Exception as e:  # noqa: BLE001
            self.state.store.save_error(self.sub_id, f"{type(e).__name__}: {e}")
            self.done.emit(self.sub_id, False, str(e))


class RerunDialog(QDialog):
    """Shows the prompt and the AI response, and lets the TA add a
    clarification for this student before re-running."""
    rerun_requested = Signal(str, bool, str, str)

    def __init__(self, state: AppState, sub_id: str, parent=None):
        super().__init__(parent)
        self.state, self.sub_id = state, sub_id
        row = state.store.submission(sub_id)
        self.setWindowTitle(f"AI pre-screen for {row['name'] or sub_id}")
        self.resize(980, 720)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs, 1)

        # clarification + rerun
        w = QWidget()
        wl = QVBoxLayout(w)
        wl.addWidget(wrap_label(
            "Write what the AI should know about this submission, then re-run. Examples: \"The voltage map is "
            "the table on page 5; check its orientation.\" or \"The chat continues in the second part of "
            "Appendix A after the code listing.\" Your note is added to the prompt for this student only, and it "
            "stays with this student for later re-runs, also from the Pre-screen tab. The class-wide instructions "
            "are not changed here. They are set on the Pre-screen tab. Rubric levels you already chose are kept, "
            "decided findings are kept, and new ones are added as pending.", "muted"))
        self.note = QPlainTextEdit()
        self.note.setPlainText(row["ta_note"] or "")
        self.note.setPlaceholderText("Clarification for the AI (optional)")
        wl.addWidget(self.note, 1)
        if state.is_ta:
            wl.addWidget(wrap_label(state.ai_status()[1], "muted"))
        gn = state.meta("global_note", "") or ""
        if gn:
            wl.addWidget(wrap_label(f"Class-wide note also in effect: {gn}", "muted"))
        btns = QHBoxLayout()
        self.dry = QCheckBox("Automatic checks only (no AI)")
        btns.addWidget(self.dry)
        btns.addSpacing(16)
        btns.addWidget(QLabel("Model"))
        self.model = QComboBox()
        mcfg = state.pack.model
        labels = {mcfg.get("name"): mcfg.get("label", mcfg.get("name")),
                  mcfg.get("escalation_name"): mcfg.get("escalation_label", mcfg.get("escalation_name"))}
        for mname in state.allowed_models() or [mcfg.get("name", "")]:
            self.model.addItem(labels.get(mname) or mname, mname)
        self.model.setToolTip("Use the stronger model only for papers the default model handled badly.")
        self.dry.toggled.connect(lambda on: self.model.setEnabled(not on))
        btns.addWidget(self.model)
        btns.addWidget(QLabel("Effort"))
        from .effort import effort_box
        self.effort = effort_box((state.pack.model or {}).get("reasoning_effort"))
        self.dry.toggled.connect(lambda on: self.effort.setEnabled(not on))
        btns.addWidget(self.effort)
        self.cost_label = QLabel("")
        self.cost_label.setObjectName("muted")
        btns.addWidget(self.cost_label)

        def show_cost():
            from ..cost import money, per_student
            if self.dry.isChecked():
                self.cost_label.setText("free")
                return
            e = per_student(state.store, state.pack, self.model.currentData(), self.effort.currentData())
            self.cost_label.setText(money(e["cost"]) if e["cost"] is not None else "")
        self.model.currentIndexChanged.connect(show_cost)
        self.effort.currentIndexChanged.connect(show_cost)
        self.dry.toggled.connect(show_cost)
        show_cost()
        btns.addStretch(1)
        prev = QPushButton("Preview prompt with this note")
        prev.clicked.connect(self.preview)
        btns.addWidget(prev)
        self.can_run = state.ai_status()[0] or not state.is_ta
        go = QPushButton("Save note and re-run" if self.can_run else "Request re-run from the instructor")
        go.setObjectName("primary")
        go.clicked.connect(self.go)
        btns.addWidget(go)
        if state.is_ta:
            self.dry.setChecked(False)
            self.dry.setVisible(False)
        wl.addLayout(btns)
        tabs.addTab(w, "Clarify and re-run")

        self.prompt_view = QPlainTextEdit()
        self.prompt_view.setReadOnly(True)
        self.prompt_view.setPlainText(row["prompt_text"] or "No prompt recorded yet. Use 'Preview prompt'.")
        tabs.addTab(self.prompt_view, "Prompt sent")
        self.tabs = tabs

        resp = QPlainTextEdit()
        resp.setReadOnly(True)
        raw = row["raw_response"]
        if raw:
            try:
                raw = json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
            except Exception:
                pass
        resp.setPlainText(raw or "No AI response recorded (not run yet, or automatic checks only).")
        tabs.addTab(resp, "AI response")

    def preview(self):
        row = self.state.store.submission(self.sub_id)
        ext, checks = load_stage(row)
        if ext is None:
            self.prompt_view.setPlainText("This submission has not been extracted yet. Run the pre-screen first.")
        else:
            inp, _ = build_input(self.state.pack, ext, checks, row["pdf_path"],
                                 self.state.meta("global_note", "") or "", self.note.toPlainText(),
                                 with_images=False)
            self.prompt_view.setPlainText(prompt_as_text(inp, self.state.meta("ai_instructions", "") or ""))
        self.tabs.setCurrentIndex(1)

    def go(self):
        if self.state.is_ta and not self.can_run:
            self.state.store.request_rerun(self.sub_id, self.model.currentData() or None,
                                           self.note.toPlainText().strip())
            self.state.set_meta(f"rerun_effort:{self.sub_id}", self.effort.currentData())
            QMessageBox.information(self, "Request saved",
                                    "Saved. It goes to the instructor with your next return file (Setup tab). "
                                    "You can keep grading this student in the meantime.")
            self.state.submissions_changed.emit()
            self.accept()
            return
        if not self.dry.isChecked() and not self.state.api_key():
            QMessageBox.information(self, "API key needed", "Save an OpenAI API key on the Setup tab first.")
            return
        self.state.store.set_ta_note(self.sub_id, self.note.toPlainText().strip())
        self.rerun_requested.emit(self.sub_id, self.dry.isChecked(), self.model.currentData() or "",
                                  self.effort.currentData() or "")
        self.accept()


# --------------------------------------------------------------------------
class RowCard(QFrame):
    changed = Signal()
    jump = Signal(int, str)

    def __init__(self, row, screen_row: dict | None, checks: list[CheckResult], levels: list[int],
                 level, comment: str, number: int | None = None):
        super().__init__()
        self.row = row
        status = (screen_row or {}).get("status", "gray")
        self.status = status
        self.reason = (screen_row or {}).get("reason", "")
        fg, bg, label = STATUS.get(status, STATUS["gray"])
        self.setObjectName("card")
        self.setStyleSheet(f"QFrame#card {{ border-left: 5px solid {fg}; background: white; }}"
                           f"QFrame#card[current=\"true\"] {{ border: 2px solid {ACCENT}; "
                           f"border-left: 5px solid {fg}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        if number is not None:
            was = (row.handout_was if getattr(row, "handout_was", None) is not None else None)
            t = wrap_label(f"<b>{number}. {row.label}</b> <span style='color:#6b7280'>· max {row.max:g} points"
                           + (f" (originally {was:g})" if was is not None else "") + "</span>")
        else:
            t = wrap_label(f"<b>{row.label}</b> <span style='color:#6b7280'>· {row.group} · max {row.max:g}</span>")
        pills = []
        conf = (screen_row or {}).get("confidence")
        if conf == "low" and status != "gray" and (screen_row or {}).get("reason", "").find("not run") < 0:
            unsure = QLabel("AI unsure")
            unsure.setToolTip("The AI could not verify this row with confidence. Read it yourself.")
            unsure.setStyleSheet("color:#6b7280; border:1px dashed #9aa0a6; border-radius: 9px; padding: 1px 8px;")
            pills.append(unsure)
        pill = QLabel(label)
        pill.setStyleSheet(f"background:{bg}; color:{fg}; border-radius: 9px; padding: 2px 9px; font-weight:600;")
        pills.insert(0, pill)
        lay.addWidget(flow(*pills))
        lay.addWidget(t)
        lay.addWidget(wrap_label(row.description, "muted"))

        if screen_row and screen_row.get("reason"):
            title = "What the AI found:" if status in ("yellow", "red") else "AI note:"
            lay.addWidget(labelled(title, screen_row["reason"]))
        if screen_row and screen_row.get("ta_check") and status in ("yellow", "red", "gray"):
            lay.addWidget(labelled("What to check:", screen_row["ta_check"]))
        ev = evidence_block((screen_row or {}).get("evidence", []), self.jump.emit)
        if ev:
            lay.addWidget(ev)
        self.first_page = next((e.get("page") for e in (screen_row or {}).get("evidence", []) if e.get("page")), None)
        self.first_excerpt = next((e.get("excerpt", "") for e in (screen_row or {}).get("evidence", [])
                                   if e.get("page")), "")
        warn = [c for c in checks if c.row == row.id and c.status == "warn"]
        if warn:
            txt = " ".join(f"{c.label}: {c.detail}" for c in warn[:4])
            lay.addWidget(labelled("Automatic checks:", txt, muted=True))

        level_buttons = []
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for L in levels:
            b = QPushButton(f"{L}%")
            b.setObjectName("level")
            b.setCheckable(True)
            b.setToolTip(f"{row.max * L / 100:g} points")
            if level == L:
                b.setChecked(True)
            self.group.addButton(b, L)
            level_buttons.append(b)
        self.group.idClicked.connect(lambda _id: self.changed.emit())
        self.score = QLabel("")
        lay.addWidget(flow(*level_buttons, self.score, spacing=4))
        self.comment = QLineEdit(comment or "")
        self.comment.setPlaceholderText("Comment for the student (optional)")
        self.comment.textChanged.connect(lambda _t: self.changed.emit())
        self.comment_row = QHBoxLayout()
        self.comment_row.setSpacing(6)
        self.comment_row.addWidget(self.comment, 1)
        lay.addLayout(self.comment_row)

    def level(self):
        i = self.group.checkedId()
        return None if i == -1 else i

    def show_score(self, r: dict):
        if r["score"] is None:
            self.score.setText("<span style='color:#9aa0a6'>not graded</span>")
        elif r["capped"]:
            self.score.setText(f"<b>{fmt(r['score'])}</b> / {fmt(r['max'])} "
                               f"<span style='color:{STATUS['red'][0]}'>(limited to {fmt(r['cap_pct'])}% by a finding)</span>")
        else:
            self.score.setText(f"<b>{fmt(r['score'])}</b> / {fmt(r['max'])}")


class FindingCard(QFrame):
    changed = Signal()
    jump = Signal(int, str)
    remove = Signal(str)
    compare = Signal(str)

    def __init__(self, pack, finding: dict):
        super().__init__()
        self.pack, self.f = pack, finding
        fg = STATUS["red"][0]
        self.setObjectName("card")
        self.setStyleSheet(f"QFrame#card {{ border-left: 5px solid {fg}; background: #fffafa; }}"
                           f"QFrame#card[current=\"true\"] {{ border: 2px solid {ACCENT}; "
                           f"border-left: 5px solid {fg}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        self.cat = QComboBox()
        self.cat.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cat.setMinimumContentsLength(18)
        for c in pack.categories:
            pen = f"{c.points:g} pts" + (f" + items capped at {c.row_cap_pct:g}%" if c.row_cap_pct is not None else "")
            self.cat.addItem(f"{c.label} ({pen})", c.id)
        idx = self.cat.findData(finding.get("category"))
        self.cat.setCurrentIndex(max(0, idx))
        self.cat.currentIndexChanged.connect(self._cat_changed)
        self.cat.setVisible(finding.get("origin") == "ta")      # a TA's own finding starts with the choice open
        self.type_label = WrapLabel("")
        self.change_btn = QPushButton("Change type")
        self.change_btn.setToolTip("Only if the AI chose the wrong kind of problem")
        self.change_btn.clicked.connect(self._open_type)
        self.restore_btn = QPushButton("Restore AI suggestion")
        self.restore_btn.clicked.connect(self._restore_type)
        origin = {"ai": "found by AI", "auto": "automatic check", "ta": "added by TA"}.get(finding.get("origin"), "")
        o = QLabel(origin)
        o.setObjectName("muted")
        head = [QLabel("<b>Finding</b>"), o]
        if finding.get("origin") == "ta":
            rm = QPushButton("Remove")
            rm.clicked.connect(lambda: self.remove.emit(finding["uid"]))
            head.append(rm)
        lay.addWidget(flow(*head))
        lay.addWidget(self.type_label)
        lay.addWidget(self.cat)
        lay.addWidget(flow(self.change_btn, self.restore_btn))
        self._show_type()

        if finding.get("origin") == "ta":
            self.summary = QPlainTextEdit(finding.get("summary", ""))
            self.summary.setPlaceholderText("Describe the concrete issue (for the instructor's summary)")
            self.summary.setMaximumHeight(60)
            self.summary.textChanged.connect(self._summary_changed)
            lay.addWidget(self.summary)
        else:
            summ = html.escape(finding.get("summary", "").removeprefix("Automatic check: "))
            summ = re.sub(r"(https?://[^\s<]+)", r"<a href='\1'>\1</a>", summ)
            sl = wrap_label("<b>The problem:</b> " + summ)
            sl.setOpenExternalLinks(True)
            sl.setTextInteractionFlags(Qt.TextBrowserInteraction)
            lay.addWidget(sl)
        cat_obj = pack.category(finding.get("category"))
        todo = (finding.get("ta_check") or "").strip() or (cat_obj.ta_check if cat_obj else "")
        if todo:
            lay.addWidget(labelled("What to check:", todo))
        ev = evidence_block(finding.get("evidence", []), self.jump.emit)
        if ev:
            lay.addWidget(ev)
        if finding.get("similar_pair"):
            cmp_btn = QPushButton("Compare side by side")
            cmp_btn.setObjectName("primary")
            cmp_btn.setToolTip("Open both papers next to each other with the shared passages marked")
            cmp_btn.clicked.connect(lambda: self.compare.emit(finding["similar_pair"]))
            lay.addWidget(flow(cmp_btn))
        self.first_page = next((e.get("page") for e in finding.get("evidence", []) if e.get("page")), None)
        self.first_excerpt = next((e.get("excerpt", "") for e in finding.get("evidence", []) if e.get("page")), "")

        self.rows_box = QWidget()
        rl = QGridLayout(self.rows_box)
        rl.setContentsMargins(0, 0, 0, 0)
        self.cap_text = WrapLabel("")
        rl.addWidget(self.cap_text, 0, 0, 1, 2)
        self.row_checks = {}
        for k, r in enumerate(pack.rubric):
            cb = QCheckBox(r.label)
            cb.setChecked(r.id in finding.get("affected_rows", []))
            cb.toggled.connect(self._rows_changed)
            self.row_checks[r.id] = cb
            rl.addWidget(cb, 1 + k // 2, k % 2)
        lay.addWidget(self.rows_box)

        self.decision = QComboBox()
        for k, v in DECISIONS.items():
            self.decision.addItem(v, k)
        self.decision.setCurrentIndex(max(0, self.decision.findData(finding.get("decision", "pending"))))
        self.decision.currentIndexChanged.connect(self._decision_changed)
        self.pen_label = QLabel("")
        lay.addWidget(flow(QLabel("<b>Your decision:</b>"), self.decision, self.pen_label))
        self.comment = QLineEdit(finding.get("comment", ""))
        self.comment.setPlaceholderText("Comment (required for half or no penalty; shown to the student)")
        self.comment.textChanged.connect(self._comment_changed)
        self.comment_row = QHBoxLayout()
        self.comment_row.setSpacing(6)
        self.comment_row.addWidget(self.comment, 1)
        lay.addLayout(self.comment_row)
        self._update_visibility()

    def _update_visibility(self):
        cat = self.pack.category(self.f.get("category"))
        has_cap = bool(cat and cat.row_cap_pct is not None)
        self.rows_box.setVisible(has_cap)
        if has_cap:
            half = (f" ({cat.half_row_cap_pct:g}% with half penalty)" if cat.half_row_cap_pct is not None else "")
            self.cap_text.setText(
                f"<b>Item score cap:</b> if you confirm this finding, the rubric items ticked below can score at most "
                f"{cat.row_cap_pct:g}%{half}, whatever level you chose for them, because that work was not "
                f"actually demonstrated. This comes on top of the points above. Tick the rows this problem affects:")

    def _type_text(self, cat_id) -> str:
        c = self.pack.category(cat_id)
        if not c:
            return cat_id or ""
        pen = f"{c.points:g} pts" + (f" + items capped at {c.row_cap_pct:g}%" if c.row_cap_pct is not None else "")
        return f"{c.label} ({pen})"

    def _show_type(self):
        cur = self.f.get("category")
        sug = self.f.get("suggested_category")
        txt = f"<b>{html.escape(self._type_text(cur))}</b>"
        if sug and sug != cur:
            who = "AI" if self.f.get("origin") == "ai" else "automatic check"
            txt += (f"<br/><span style='color:{STATUS['yellow'][0]}'>Changed by you. The {who} suggested: "
                    f"{html.escape(self._type_text(sug))}</span>")
        self.type_label.setText(txt)
        self.type_label.setVisible(not self.cat.isVisible() or bool(sug and sug != cur))
        self.restore_btn.setVisible(bool(sug and sug != cur))
        self.change_btn.setVisible(not self.cat.isVisible())

    def _open_type(self):
        self.cat.setVisible(True)
        self.cat.setFocus()
        self.cat.showPopup()
        self._show_type()

    def _restore_type(self):
        sug = self.f.get("suggested_category")
        if sug:
            self.cat.setCurrentIndex(max(0, self.cat.findData(sug)))
            self.cat.setVisible(False)
            self._show_type()

    def _cat_changed(self):
        self.f["category"] = self.cat.currentData()
        if self.f.get("origin") != "ta":
            self.cat.setVisible(False)          # close the choice again once a type is picked
        if hasattr(self, "type_label"):
            self._show_type()
        cat = self.pack.category(self.f["category"])
        if cat and cat.row_cap_pct is not None and not self.f.get("affected_rows"):
            self.f["affected_rows"] = list(cat.default_rows)
            for rid, cb in self.row_checks.items():
                cb.blockSignals(True)
                cb.setChecked(rid in self.f["affected_rows"])
                cb.blockSignals(False)
        self._update_visibility()
        self.changed.emit()

    def _summary_changed(self):
        self.f["summary"] = self.summary.toPlainText()
        self.changed.emit()

    def _rows_changed(self):
        self.f["affected_rows"] = [rid for rid, cb in self.row_checks.items() if cb.isChecked()]
        self.changed.emit()

    def _decision_changed(self):
        self.f["decision"] = self.decision.currentData()
        self.changed.emit()

    def _comment_changed(self):
        self.f["comment"] = self.comment.text()
        self.changed.emit()

    def show_penalty(self, result: dict):
        d = next((x for x in result["deductions"] if x["uid"] == self.f["uid"]), None)
        if self.f.get("decision") == "rejected":
            self.pen_label.setText("<span style='color:#6b7280'>No effect on the grade.</span>")
        elif self.f.get("decision") == "pending":
            self.pen_label.setText(f"<span style='color:{STATUS['yellow'][0]}'>Needs a decision.</span>")
        elif d and d.get("overlap"):
            self.pen_label.setText(f"<span style='color:#6b7280'>Counted once, under “{d['overlap']}”.</span>")
        else:
            self.pen_label.setText(f"Deduction: <b>{fmt(d['points']) if d else 0}</b> pts")


# --------------------------------------------------------------------------
class ReviewTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.sub_id: str | None = None
        self.review: dict | None = None
        self.row_cards: list[RowCard] = []
        self.finding_cards: list[FindingCard] = []
        self.rerun_threads: dict[str, RerunThread] = {}
        self.regrade_reply = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        split = QSplitter(Qt.Horizontal)
        lay.addWidget(split)

        # left: student list
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.filter = QComboBox()
        self.filter.addItems(["All students", "Not yet reviewed", "Reviewed", "Has integrity findings",
                              "Has red flags", "Errors", "AI re-run, check again", "Regrade requests"])
        self.filter.currentIndexChanged.connect(self.refresh_list)
        ll.addWidget(self.filter)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name or ID")
        self.search.textChanged.connect(self.refresh_list)
        ll.addWidget(self.search)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._select)
        ll.addWidget(self.list, 1)
        self.progress = QLabel("")
        self.progress.setObjectName("muted")
        ll.addWidget(self.progress)
        dot = lambda c, ring=None: (f"<span style='color:{c}'>●</span>" if not ring else
                                    f"<span style='color:{ring}'>○</span>")
        legend = QLabel(
            f"{dot(STATUS['red'][0])} likely problem or integrity finding<br/>"
            f"{dot(STATUS['yellow'][0])} items to check &nbsp;{dot('', '#94a3b8')} nothing flagged<br/>"
            f"{dot(STATUS['green'][0])} reviewed &nbsp;{dot(RECHECK)} AI re-run, check again<br/>"
            f"{dot(REGRADE)} regrade request &nbsp;{dot('#d1d5db')} not pre-screened")
        legend.setObjectName("muted")
        legend.setStyleSheet("font-size: 11px;")
        legend.setTextFormat(Qt.RichText)
        legend.setWordWrap(True)
        ll.addWidget(legend)
        self.legend, self.left_col = legend, left
        split.addWidget(left)

        # center: pdf
        self.pdf = PdfView()
        split.addWidget(self.pdf)

        # right: grading panel
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.panel_scroll = QScrollArea()
        self.panel_scroll.setWidgetResizable(True)
        self.panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.panel_scroll.setMinimumHeight(200)
        rl.addWidget(self.panel_scroll, 1)
        footer = QFrame()
        footer.setObjectName("card")
        fl = QVBoxLayout(footer)
        fl.setContentsMargins(12, 8, 12, 8)
        self.total = QLabel("")
        self.total.setStyleSheet("font-size: 15px;")
        fl.addWidget(self.total)
        self.problems = wrap_label("", "muted")
        fl.addWidget(self.problems)
        from .keys import KeyGrader, hint_text
        self.keys_hint = QToolButton()
        self.keys_hint.setText("Keyboard shortcuts")
        self.keys_hint.setObjectName("linkbtn")
        self.keys_hint.setCursor(Qt.PointingHandCursor)
        self.keys_hint.setToolTip(hint_text().replace(" · ", "<br/>").replace("Keys: ", "<b>Keys</b><br/>"))
        self.keys_hint.clicked.connect(lambda: QToolTip.showText(
            self.keys_hint.mapToGlobal(QPoint(0, 0)), self.keys_hint.toolTip(), self.keys_hint))
        fl.removeWidget(self.total)               # total on the left, the shortcuts link on the same line
        top = QHBoxLayout()
        top.addWidget(self.total, 1)
        top.addWidget(self.keys_hint, 0, Qt.AlignTop)
        fl.insertLayout(0, top)
        self.keys = KeyGrader(self)
        fb = QHBoxLayout()
        self.prev_btn = QPushButton("◀ Previous")
        self.prev_btn.clicked.connect(lambda: self._step(-1))
        fb.addWidget(self.prev_btn)
        fb.addStretch(1)
        self.reviewed_btn = QPushButton("Mark reviewed and next")
        self.reviewed_btn.setObjectName("primary")
        self.reviewed_btn.clicked.connect(self.mark_reviewed)
        fb.addWidget(self.reviewed_btn)
        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(lambda: self._step(1))
        fb.addWidget(self.next_btn)
        fl.addLayout(fb)
        rl.addWidget(footer)
        self.footer = footer
        split.addWidget(right)
        left.setMinimumWidth(170)
        self.pdf.setMinimumWidth(260)
        right.setMinimumWidth(360)
        split.setChildrenCollapsible(False)
        split.setSizes([230, 640, 520])
        split.setStretchFactor(1, 1)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save)
        state.submissions_changed.connect(self.refresh_list)
        state.pack_changed.connect(lambda: self.sub_id and self.state.pack and self.open_student(self.sub_id))
        state.workspace_changed.connect(self._workspace_switched)
        state.flush_hooks.append(self._save)
        state.discard_hooks.append(self._forget)
        state.reload_student.connect(self._reload)
        state.student_updated.connect(self._student_updated)
        self.refresh_list()

    # list ---------------------------------------------------------------
    def _item_state(self, r) -> tuple[str, bool, bool, bool]:
        screen = json.loads(r["screen"]) if r["screen"] else None
        rev = self.state.store.review(r["sub_id"])
        reviewed = bool(rev and rev.get("reviewed"))
        # integrity findings still to decide or confirmed, from any source, as Review lists them
        if rev is not None:
            fs = rev.get("findings", [])
        elif screen:
            fs = new_review_from_screen(self.state.pack, screen)["findings"] if self.state.pack else []
        else:
            fs = []
        has_int = any(f.get("decision", "pending") in ("pending", "full", "half") for f in fs)
        red = bool(screen and any(x["status"] == "red" for x in screen["rows"]))
        yellow = bool(screen and any(x["status"] == "yellow" for x in screen["rows"]))
        if r["status"] == "error":
            color = "#6b7280"
        elif regrade.open_request(self.state.store, r["sub_id"]):
            color = REGRADE
        elif self.state.meta(f"recheck:{r['sub_id']}"):
            color = RECHECK
        elif reviewed:
            color = STATUS["green"][0]
        elif has_int or red:
            color = STATUS["red"][0]              # a likely problem, or an integrity finding
        elif yellow:
            color = STATUS["yellow"][0]           # only items to check
        elif screen:
            color = NOFLAG                        # pre-screened, nothing flagged (still read the work)
        else:
            color = "#d1d5db"                     # not pre-screened yet
        return color, reviewed, has_int, red

    def refresh_list(self):
        cur = self.sub_id
        self.list.blockSignals(True)
        self.list.clear()
        if not self.state.ready:
            self.list.blockSignals(False)
            return
        f = self.filter.currentIndex()
        q = self.search.text().strip().lower()
        n_rev = 0
        rows = self.state.store.submissions()
        for r in rows:
            color, reviewed, has_int, red = self._item_state(r)
            n_rev += reviewed
            if q and q not in (r["name"] or "").lower() and q not in r["sub_id"].lower():
                continue
            if (f == 1 and reviewed) or (f == 2 and not reviewed) or (f == 3 and not has_int) \
                    or (f == 4 and not red) or (f == 5 and r["status"] != "error") \
                    or (f == 6 and color != RECHECK) \
                    or (f == 7 and not regrade.requests(self.state.store, r["sub_id"])):
                continue
            recheck = color == RECHECK
            it = QListWidgetItem(list_dot(color), f"{r['name'] or r['sub_id']}\n{r['sub_id']}"
                                 + (" · AI re-run, check again" if recheck else "")
                                 + (" · regrade request" if color == REGRADE else "")
                                 + (" · reviewed" if reviewed else "")
                                 + (" · error" if r["status"] == "error" else ""))
            it.setData(Qt.UserRole, r["sub_id"])
            self.list.addItem(it)
            if r["sub_id"] == cur:
                self.list.setCurrentItem(it)
        self.list.blockSignals(False)
        self.progress.setText(f"{n_rev} of {len(rows)} reviewed")
        if self.list.currentItem() is None and self.list.count() and cur is None:
            self.list.setCurrentRow(0)

    def _select(self, item, _prev=None):
        if item is None:
            return
        self._save()
        self.open_student(item.data(Qt.UserRole))

    def select_student(self, sid: str):
        """Show one student, clearing the filter and search so they are in the list."""
        for w, reset in ((self.filter, lambda: self.filter.setCurrentIndex(0)), (self.search, self.search.clear)):
            w.blockSignals(True)
            reset()
            w.blockSignals(False)
        self.refresh_list()
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == sid:
                if self.list.currentRow() == i:
                    self.open_student(sid)
                else:
                    self.list.setCurrentRow(i)
                self.list.scrollToItem(self.list.item(i))
                return

    def _step(self, d):
        i = self.list.currentRow() + d
        if 0 <= i < self.list.count():
            self.list.setCurrentRow(i)

    # panel --------------------------------------------------------------
    def _load_review(self, row, screen) -> dict:
        st, pack = self.state.store, self.state.pack
        rev = st.review(row["sub_id"])
        reviewer = self.state.meta("reviewer", "") or ""
        if rev is None:
            rev = new_review_from_screen(pack, screen, reviewer)
            rev["screen_at"] = row["screened_at"]
            st.save_review(row["sub_id"], rev)
            rev = st.review(row["sub_id"]) | {"screen_at": row["screened_at"]}
        # a newer pre-screen (for example from an instructor update): keep the grader's work, flag a re-check
        if screen:
            try:
                merge_new_screen(st, pack, row["sub_id"])
                rev = st.review(row["sub_id"]) or rev
            except Exception:  # noqa: BLE001
                pass
        # remember (or recover) what the AI or automatic check originally suggested for each finding
        if screen:
            originals = list(screen.get("integrity", [])) + list(screen.get("auto_integrity", []))
            changed = False
            for f in rev.get("findings", []):
                if f.get("origin") == "ta" or f.get("suggested_category"):
                    continue
                match = next((o for o in originals if o.get("summary") == f.get("summary")), None)
                f["suggested_category"] = (match or {}).get("category") or f.get("category")
                changed = True
            if changed:
                st.save_review(row["sub_id"], rev)
        if screen:
            from ..pipeline import restore_lost_findings
            if restore_lost_findings(st, pack, row["sub_id"]):
                rev = st.review(row["sub_id"]) | {"screen_at": row["screened_at"]}
        for r in pack.rubric:
            rev.setdefault("levels", {}).setdefault(r.id, None)
            rev.setdefault("comments", {}).setdefault(r.id, "")
        return rev

    def open_student(self, sub_id: str):
        st, pack = self.state.store, self.state.pack
        row = st.submission(sub_id)
        if row is None:
            return
        if sub_id != self.sub_id:
            self._removed_uids = set()
        self.sub_id = sub_id
        screen = json.loads(row["screen"]) if row["screen"] else None
        ext_obj, checks = load_stage(row)
        checks = checks or []
        late_hidden = []
        if ext_obj is not None and not getattr(ext_obj, "hidden_checked", False):
            # pre-screened by an older version, before hidden text was checked: look now (quick, read only)
            try:
                import pymupdf
                from pathlib import Path as _P
                from ..hidden import find_hidden
                with pymupdf.open(stream=_P(row["pdf_path"]).read_bytes(), filetype="pdf") as d:
                    late_hidden = [(i + 1, h) for i, pg in enumerate(d) for h in find_hidden(pg)]
            except Exception:  # noqa: BLE001
                late_hidden = []
        self.review = self._load_review(row, screen)
        try:
            self.bank = build_bank(st, exclude_sid=sub_id)
        except Exception:  # noqa: BLE001
            self.bank = {}
        self.pdf.load(row["pdf_path"])

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(4, 4, 8, 8)
        lay.setSpacing(10)

        head = QHBoxLayout()
        h = wrap_label(f"{row['name'] or sub_id}", "h1")
        head.addWidget(h, 1)
        rr = QPushButton("Re-run AI / view prompt…" if (not self.state.is_ta or self.state.ai_status()[0])
                         else "Request re-run / view prompt…")
        rr.clicked.connect(self.open_rerun)
        head.addWidget(rr)
        lay.addLayout(head)
        open_req = regrade.open_request(st, sub_id)
        if self.review.get("reviewed") and not open_req:
            rq = QPushButton("Regrade request…")
            rq.setToolTip("The student asked for this grade to be looked at again")
            rq.clicked.connect(self.start_regrade)
            head.insertWidget(1, rq)
        ext_json = json.loads(row["extraction"]) if row["extraction"] else {}
        try:
            sinfo = json.loads(row["info"] or "{}")
        except Exception:
            sinfo = {}
        idpart = f"Student ID {sinfo['id_number']} · " if sinfo.get("id_number") else ""
        fname = html.escape(sinfo.get("original_file", ""))
        fname = re.sub(r"([_.\-])", "\\1\u200b", fname)     # allow line breaks inside long file names
        info = f"{idpart}Moodle {sub_id} · file “{fname}” · " \
               f"{ext_json.get('page_count', '?')} pages · main report about " \
               f"{ext_json.get('report_pages_used', '?')} pages"
        if screen:
            meta = screen.get("_meta", {})
            info += " · " + ("automatic checks only" if meta.get("model") == "offline"
                             else f"AI: {meta.get('model')}"
                             + (f", {meta['effort']} effort" if meta.get("effort") not in (None, "not supported")
                                else ""))
            if meta.get("model") not in (None, "offline"):
                from ..pipeline import current_prompt_version, prompt_version_of
                from .instructions import version_label
                v = prompt_version_of(row)
                info += f", prompt {version_label(self.state, v)}" + (" with a student note"
                                                                      if meta.get("student_note") else "")
                if v is not None and v != current_prompt_version(st):
                    info += (" <span style='color:#b7791f'>(earlier than the current prompt: re-screen from the "
                             "Pre-screen tab if needed)</span>")
        if row["ta_note"]:
            info += " · TA note in prompt"
        info_label = wrap_label(info, "muted")
        info_label.setTextFormat(Qt.RichText)          # the file name is escaped and the line may carry a colour
        lay.addWidget(info_label)
        if late_hidden:
            shown = "<br/>".join(f"p.{p}, {html.escape(h['reason'])}: “{html.escape(h['text'][:120])}”"
                                 for p, h in late_hidden[:4])
            lay.addWidget(wrap_label(
                f"<b style='color:{STATUS['red'][0]}'>Hidden text in this PDF.</b> Text a reader cannot see was "
                f"found. This student was pre-screened by an earlier version, so the AI may have read it. "
                f"Re-run the AI to pre-screen without it, and add a finding if it was meant to influence the "
                f"grading.<br/>{shown}"))
        note = self.state.meta(f"recheck:{sub_id}")
        if note:
            lay.addWidget(recheck_banner(note))
        for req in regrade.requests(st, sub_id):
            if req.get("closed_at"):
                lay.addWidget(wrap_label(
                    f"<b>Regrade request</b>, closed {_day(req['closed_at'])}. "
                    f"{html.escape(regrade.summary(pack, req))} "
                    f"<span style='color:#6b7280'>Request: {html.escape(req.get('request', '')[:200])}</span>",
                    "muted"))
        self.regrade_reply = None
        if open_req:
            lay.addWidget(self._regrade_banner(open_req))
        if row["rerun_requested"]:
            lay.addWidget(wrap_label(f"<b style='color:{ACCENT}'>Re-run requested</b>"
                                     + (f" with {row['rerun_model']}" if row["rerun_model"] else "")
                                     + (". Waiting for the instructor." if self.state.is_ta else
                                        ". Start on the Pre-screen tab processes it.")))
        if sub_id in self.rerun_threads:
            lay.addWidget(wrap_label(f"<b style='color:{ACCENT}'>Re-running the pre-screen for this "
                                     "student…</b>"))
        if row["status"] == "error":
            lay.addWidget(wrap_label(f"<b style='color:{STATUS['red'][0]}'>Pre-screen error:</b> {row['error']}"))
        if screen and screen.get("overall_note"):
            lay.addWidget(wrap_label(f"<i>{screen['overall_note']}</i>"))
        for w in (ext_json.get("warnings") or []):
            lay.addWidget(wrap_label(f"<span style='color:{STATUS['yellow'][0]}'>{w}</span>"))
        general = [c for c in checks if c.row in ("info",) and c.status == "warn"]
        for c in general:
            lay.addWidget(wrap_label(f"<span style='color:{STATUS['yellow'][0]}'>{c.label}: {c.detail}</span>"))
        for c in checks:
            if c.id == "headings" and c.status == "info":
                lay.addWidget(wrap_label(f"{c.label}. {html.escape(c.detail)}", "muted"))

        start, _ = section_header("✓", "Start here")
        lay.addWidget(start)
        self.todo_box = QVBoxLayout()
        self.todo_box.setSpacing(4)
        todo_frame = QFrame()
        todo_frame.setObjectName("card")
        todo_frame.setLayout(self.todo_box)
        self.todo_box.setContentsMargins(10, 8, 10, 8)
        lay.addWidget(todo_frame)

        n_rows = len(pack.rubric)
        hdr, self.rubric_chip = section_header(
            "1", "Grade the rubric",
            f"Read the work and choose a level for each of the {n_rows} items "
            f"({pack.total_max:g} points in total). The AI's notes are hints, not grades.")
        lay.addWidget(hdr)
        self.row_cards = []
        srows = {x["row_id"]: x for x in (screen or {}).get("rows", [])}
        last_group = None
        for k, r in enumerate(pack.rubric, 1):
            if r.group and r.group != last_group:
                pts = sum(x.max for x in pack.rubric if x.group == r.group)
                lay.addWidget(group_label(f"{r.group}  ·  {pts:g} points"))
                last_group = r.group
            r.handout_was = pack.handout_points(r.id)
            card = RowCard(r, srows.get(r.id), checks, pack.levels, self.review["levels"].get(r.id),
                           self.review["comments"].get(r.id, ""), number=k)
            card.changed.connect(self._changed)
            card.jump.connect(self.pdf.goto)
            self._attach_bank(card.comment, card.comment_row, lambda rid=r.id: rid)
            lay.addWidget(card)
            self.row_cards.append(card)

        add = QPushButton("Add finding")
        add.clicked.connect(self.add_finding)
        cap = (f" Total integrity deductions are capped at {pack.integrity_cap:g} points."
               if pack.integrity_cap and pack.integrity_cap < pack.total_max else "")
        hdr, self.finding_chip = section_header(
            "2", "Decide integrity findings",
            "Check each possible problem yourself and choose a decision. Confirm only concrete issues." + cap,
            right=add)
        lay.addWidget(hdr)
        self.finding_cards = []
        if not self.review["findings"]:
            lay.addWidget(wrap_label("No findings for this student. Use Add finding if you see a problem.", "muted"))
        for f in self.review["findings"]:
            fc = FindingCard(pack, f)
            fc.changed.connect(self._changed)
            fc.jump.connect(self.pdf.goto)
            fc.remove.connect(self.remove_finding)
            fc.compare.connect(self.open_compare)
            self._attach_bank(fc.comment, fc.comment_row, lambda f=f: f"finding:{f.get('category')}")
            lay.addWidget(fc)
            self.finding_cards.append(fc)

        hdr, _ = section_header("3", "Comment and finish",
                                "An optional overall comment for the student. Then press Mark reviewed and next "
                                "below.")
        lay.addWidget(hdr)
        self.overall = QPlainTextEdit(self.review.get("overall_comment", ""))
        self.overall.setMaximumHeight(90)
        self.overall.textChanged.connect(self._changed)
        lay.addWidget(self.overall)
        overall_row = QHBoxLayout()
        overall_row.addStretch(1)
        lay.addLayout(overall_row)
        self._attach_bank(self.overall, overall_row, lambda: "overall")
        lay.addStretch(1)

        self._fill_todo()
        old = self.panel_scroll.takeWidget()
        if old:
            old.deleteLater()
        self.panel_scroll.setWidget(body)
        try:
            self.keys.set_items(self.row_cards + self.finding_cards)
            for c in self.row_cards + self.finding_cards:
                c.changed.connect(lambda c=c: self.keys.select_card(c))    # mouse and keys can be mixed
            if not isinstance(QApplication.focusWidget(), (QLineEdit, QPlainTextEdit)):
                self.panel_scroll.setFocus()
        except Exception:  # noqa: BLE001
            pass
        self._update_totals()
        self._snapshot = self._fingerprint()      # what was loaded: saving is skipped until something changes

    def _fingerprint(self) -> str:
        if self.review is None:
            return ""
        try:
            self._collect()
            return json.dumps(self.review, sort_keys=True, default=str)
        except Exception:  # noqa: BLE001
            return ""

    # similar work -------------------------------------------------------
    def open_compare(self, key: str):
        from .. import similarity
        from .compare import CompareWindow
        pair = similarity.find_pair(self.state.meta(similarity.REPORT_KEY) or {}, key)
        if pair is None:
            QMessageBox.information(self, "Not in the latest check",
                                    "The latest similarity check no longer lists this pair, for example because a "
                                    "submission was replaced. Decide the finding from what you know, or reject it.")
            return
        win = CompareWindow(self.state, pair, me=self.sub_id, parent=self)
        win.show()
        self._compare_win = win

    # regrade requests ---------------------------------------------------
    def _regrade_banner(self, req: dict) -> QFrame:
        box = QFrame()
        box.setObjectName("card")
        box.setStyleSheet(f"QFrame#card {{ background: #f0fdfa; border: 1px solid #99f6e4; "
                          f"border-left: 5px solid {REGRADE}; }}")
        v = QVBoxLayout(box)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(6)
        v.addWidget(wrap_label(f"<b style='color:{REGRADE}'>Regrade request</b> · opened {_day(req['opened_at'])}"
                               f" · {html.escape(regrade.summary(self.state.pack, req))}"))
        v.addWidget(labelled("The student asks:", req.get("request") or "(no text)"))
        v.addWidget(wrap_label("Look at the work again and change any level or decision that is warranted. Then "
                               "write a reply for the student and press <i>Mark reviewed</i>. The reply and what "
                               "changed go on the feedback page.", "muted"))
        self.regrade_reply = QPlainTextEdit(req.get("reply", ""))
        self.regrade_reply.setPlaceholderText("Reply to the student (required)")
        self.regrade_reply.setMaximumHeight(80)
        self.regrade_reply.textChanged.connect(
            lambda: (regrade.set_reply(self.state.store, self.sub_id, self.regrade_reply.toPlainText()),
                     self._update_totals()))
        v.addWidget(self.regrade_reply)
        cancel = QPushButton("Withdraw request")
        cancel.setToolTip("Remove this request, for example if it was opened by mistake")
        cancel.clicked.connect(self.cancel_regrade)
        v.addWidget(flow(cancel))
        return box

    def start_regrade(self):
        if not self.sub_id:
            return
        self._save()
        text, ok = QInputDialog.getMultiLineText(
            self, "Regrade request", "What does the student ask? Paste their message or summarise it.")
        if not ok:
            return
        regrade.start(self.state.store, self.state.pack, self.sub_id, text)
        glog.info("Regrade request opened: %s", self.sub_id)
        self.review = None                     # reload: the student is no longer marked reviewed
        sid = self.sub_id
        self.refresh_list()
        self.open_student(sid)
        self.state.reviews_changed.emit()

    def cancel_regrade(self):
        if QMessageBox.question(self, "Withdraw request?", "Remove this regrade request? Grading changes you "
                                "made are kept.") != QMessageBox.Yes:
            return
        regrade.cancel(self.state.store, self.sub_id)
        self._collect()
        if not readiness_problems(self.state.pack, self.review):
            self.review["reviewed"] = True
        self._save()
        sid = self.sub_id
        self.refresh_list()
        self.open_student(sid)
        self.state.reviews_changed.emit()

    # comment bank -------------------------------------------------------
    def _attach_bank(self, field, row_layout, key_fn):
        """Comments already written for this item for other students: a small icon inside the comment box opens
        the list, and matching ones are suggested while typing. Picking one adds it; it can still be edited.
        Nothing is shown when there are no earlier comments."""
        items = lambda: self.bank.get(key_fn(), [])
        line = isinstance(field, QLineEdit)
        if line:
            ctrl = field.addAction(_bank_icon(), QLineEdit.TrailingPosition)
        else:
            ctrl = QToolButton()
            ctrl.setText("Earlier comments")
            ctrl.setObjectName("linkbtn")
            ctrl.setCursor(Qt.PointingHandCursor)
            row_layout.addWidget(ctrl)   # give it a parent first: showing a parentless button opens a window
            if ctrl.parentWidget() is None:
                ctrl.setParent(self)

        def put(text):
            if line:
                field.setText(insert_text(field.text(), text))
                field.setCursorPosition(len(field.text()))
            else:
                field.setPlainText(insert_text(field.toPlainText(), text))
                field.moveCursor(QTextCursor.End)
            field.setFocus()

        def drop(text):
            key = key_fn()
            try:
                bank_hide(self.state.store, key, text)
            except Exception:  # noqa: BLE001
                return
            self.bank[key] = [x for x in self.bank.get(key, []) if x[0] != text]
            refresh()

        def short(t):
            return t if len(t) <= 90 else t[:87].rsplit(" ", 1)[0] + "…"

        def show_menu():
            # the menu is made only when asked for: a hidden menu per comment box would be one more window
            menu = QMenu(self)
            title = menu.addAction("Earlier comments for this item")
            title.setEnabled(False)
            menu.addSeparator()
            its = items()[:15]
            for text, n in its:
                a = menu.addAction(short(text) + (f"   ({n}×)" if n > 1 else ""))
                a.setToolTip(text)
                a.triggered.connect(lambda _=False, t=text: put(t))
            if its:
                menu.addSeparator()
                sub = menu.addMenu("Remove from this list")
                for text, _n in its:
                    sub.addAction(short(text)).triggered.connect(lambda _=False, t=text: drop(t))
            self._bank_menu = menu
            anchor = field if line else ctrl
            menu.exec(anchor.mapToGlobal(anchor.rect().bottomRight()) - QPoint(menu.sizeHint().width(), 0))
            menu.deleteLater()

        def refresh():
            its = items()
            ctrl.setVisible(bool(its))
            ctrl.setToolTip(f"Earlier comments for this item ({len(its)}). Click to pick one.")
            if line:
                comp = QCompleter([t for t, _ in its], field)
                comp.setCaseSensitivity(Qt.CaseInsensitive)
                comp.setFilterMode(Qt.MatchContains)
                comp.setMaxVisibleItems(8)
                field.setCompleter(comp)

        (ctrl.triggered if line else ctrl.clicked).connect(show_menu)
        ctrl._items = items                      # for tests
        ctrl._put, ctrl._drop, ctrl._show = put, drop, show_menu
        refresh()
        return ctrl

    def _fill_todo(self):
        """Numbered list of everything that needs the grader's attention, each jumping to its card and page."""
        while self.todo_box.count():
            it = self.todo_box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        items = []
        for c in self.row_cards:
            if c.status in ("red", "yellow"):
                items.append((STATUS[c.status][0], f"{c.row.label}: {c.reason}", c))
        for fc in self.finding_cards:
            cat = self.state.pack.category(fc.f.get("category"))
            dec = fc.f.get("decision", "pending")
            if dec == "pending":
                text = fc.f.get("summary", "").removeprefix("Automatic check: ")
                items.append((STATUS["red"][0], f"Finding, {cat.label if cat else ''}: {text}", fc))
        t = QLabel(f"<b>To check ({len(items)})</b>" if items else
                   "<b>To check:</b> <span style='color:#6b7280'>nothing flagged. Still read the work.</span>")
        self.todo_box.addWidget(t)
        if items:
            self.todo_box.addWidget(QLabel("<span style='color:#6b7280'>Click an item to open its card and the "
                                           "page it refers to.</span>"))
        for k, (colour, text, card) in enumerate(items, 1):
            short = text if len(text) <= 170 else text[:167].rsplit(" ", 1)[0] + "…"
            self.todo_box.addWidget(ClickCard(f"{k}.  {html.escape(short)}", colour,
                                              lambda c=card: self._go_to(c)))

    def _go_to(self, card):
        self.panel_scroll.verticalScrollBar().setValue(max(0, card.y() - 8))
        if getattr(card, "first_page", None):
            self.pdf.goto(int(card.first_page), card.first_excerpt or "")
        card.setStyleSheet(card.styleSheet() + " QFrame#card { border: 2px solid " + ACCENT + "; }")
        QTimer.singleShot(1400, lambda: card.setStyleSheet(card.styleSheet().rsplit(" QFrame#card { border: 2px", 1)[0]))

    def _collect(self):
        if not self.review:
            return
        for card in self.row_cards:
            self.review["levels"][card.row.id] = card.level()
            self.review["comments"][card.row.id] = card.comment.text()
        self.review["overall_comment"] = self.overall.toPlainText()
        self.review["reviewer"] = self.review.get("reviewer") or (self.state.meta("reviewer", "") or "")

    def _changed(self):
        self._collect()
        if hasattr(self, "todo_box"):
            pending = sum(1 for f in self.review.get("findings", []) if f.get("decision", "pending") == "pending")
            if pending != getattr(self, "_last_pending", None):
                self._last_pending = pending
                self._fill_todo()
        if self.review.get("reviewed") and readiness_problems(self.state.pack, self.review):
            self.review["reviewed"] = False
        self._update_totals()
        self._save_timer.start(400)

    def _reload(self):
        """Show the current student again after their grading was changed elsewhere (for example a new finding),
        keeping the place in the panel."""
        if not (self.sub_id and self.state.ready):
            return
        y = self.panel_scroll.verticalScrollBar().value()
        self.open_student(self.sub_id)
        QTimer.singleShot(0, lambda: self.panel_scroll.verticalScrollBar().setValue(y))

    def _forget(self):
        """Drop the student on screen without saving it (its data is about to be replaced)."""
        self._save_timer.stop()
        self.sub_id = None
        self.review = None

    def _workspace_switched(self):
        # start clean: the panel's student belongs to the workspace that was open before
        self._save_timer.stop()
        self.sub_id = None
        self.review = None
        self.refresh_list()

    def _save(self):
        """Save the student on screen. Findings that were added to this student elsewhere since it was opened
        (a new pre-screen result, a similar-work check) are kept, never written over by the copy on screen."""
        if self.sub_id and self.review is not None:
            fp = self._fingerprint()
            if fp and fp == getattr(self, "_snapshot", None):
                return                  # nothing was changed on screen: never write a stale copy over the file
            try:
                stored = self.state.store.review(self.sub_id)
            except Exception:  # noqa: BLE001
                stored = None
            if stored:
                mine = {f.get("uid") for f in self.review.get("findings", [])}
                gone = getattr(self, "_removed_uids", set())
                extra = [f for f in stored.get("findings", []) if f.get("uid") not in mine and f.get("uid") not in gone]
                if extra:
                    self.review.setdefault("findings", []).extend(extra)
                    if any(f.get("decision", "pending") == "pending" for f in extra):
                        self.review["reviewed"] = False
                    glog.info("Kept %s finding(s) added to %s while it was on screen", len(extra), self.sub_id)
            self.state.store.save_review(self.sub_id, self.review)
            self._snapshot = self._fingerprint()

    def _student_updated(self, sid: str):
        """A new pre-screen result arrived for the student on screen: save what was typed, then show it again
        with the new result."""
        if sid and sid == self.sub_id and self.state.ready:
            self._save()
            self._reload()

    def _update_totals(self):
        pack = self.state.pack
        res = compute(pack, self.review)
        for card, r in zip(self.row_cards, res["rows"]):
            card.show_score(r)
        for fc in self.finding_cards:
            fc.show_penalty(res)
        ded = f" − integrity {fmt(res['deduction_total'])}" if res["deduction_total"] else ""
        self.total.setText(f"Rubric {fmt(res['rubric_total'])}{ded} = <b>{fmt(res['total'])}</b> / "
                           f"{fmt(res['max'])}" + ("" if res["complete"] else
                                                   " <span style='color:#9aa0a6'>(incomplete)</span>"))
        if getattr(self, "rubric_chip", None) is not None:
            graded = sum(1 for r in pack.rubric if self.review.get("levels", {}).get(r.id) is not None)
            set_chip(self.rubric_chip, f"{graded} of {len(pack.rubric)} graded", graded == len(pack.rubric))
            fs = self.review.get("findings", [])
            decided = sum(1 for f in fs if f.get("decision", "pending") != "pending")
            set_chip(self.finding_chip, f"{decided} of {len(fs)} decided" if fs else "none",
                     decided == len(fs))
        probs = readiness_problems(pack, self.review)
        if getattr(self, "regrade_reply", None) is not None and not self.regrade_reply.toPlainText().strip():
            probs = probs + ["Write a reply to the regrade request."]
        if self.review.get("reviewed"):
            self.problems.setText(f"<span style='color:{STATUS['green'][0]}'>Marked as reviewed.</span>")
            self.reviewed_btn.setText("Next unreviewed ▶")
        else:
            self.problems.setText(" ".join(probs[:3]) + (" …" if len(probs) > 3 else ""))
            self.reviewed_btn.setText("Mark reviewed and next")

    def mark_reviewed(self):
        if not self.review:
            return
        self._collect()
        open_req = regrade.open_request(self.state.store, self.sub_id)
        if not self.review.get("reviewed"):
            probs = readiness_problems(self.state.pack, self.review)
            if open_req and not (self.regrade_reply and self.regrade_reply.toPlainText().strip()):
                probs = probs + ["Write a reply to the student's regrade request."]
            if probs:
                QMessageBox.information(self, "Not finished yet", "\n".join(probs))
                return
            self.review["reviewed"] = True
            self._save()
            glog.info("Marked reviewed: %s (total %s)", self.sub_id, compute(self.state.pack, self.review)["total"])
            if open_req:
                req = regrade.close(self.state.store, self.state.pack, self.sub_id)
                glog.info("Regrade closed: %s. %s", self.sub_id, regrade.summary(self.state.pack, req or {}))
        if self.state.meta(f"recheck:{self.sub_id}"):
            self.state.set_meta(f"recheck:{self.sub_id}", None)
        self.refresh_list()
        self.state.reviews_changed.emit()
        # go to the next unreviewed student in the current list
        start = self.list.currentRow()
        for k in range(1, self.list.count() + 1):
            i = (start + k) % self.list.count()
            sid = self.list.item(i).data(Qt.UserRole)
            rv = self.state.store.review(sid)
            if not (rv and rv.get("reviewed")):
                self.list.setCurrentRow(i)
                return
        QMessageBox.information(self, "All done", "Every student in this list is reviewed.")

    def add_finding(self):
        if not self.review:
            return
        cat = self.state.pack.categories[0] if self.state.pack.categories else None
        self.review["findings"].append({
            "uid": uuid.uuid4().hex[:10], "origin": "ta", "category": cat.id if cat else "other",
            "summary": "", "affected_rows": list(cat.default_rows) if cat else [], "evidence": [],
            "decision": "pending", "comment": ""})
        self._save()
        self.open_student(self.sub_id)

    def remove_finding(self, uid):
        self._removed_uids = getattr(self, "_removed_uids", set()) | {uid}
        self.review["findings"] = [f for f in self.review["findings"] if f["uid"] != uid]
        self._save()
        self.open_student(self.sub_id)

    # rerun --------------------------------------------------------------
    def open_rerun(self):
        if not self.sub_id:
            return
        self._save()
        dlg = RerunDialog(self.state, self.sub_id, self)
        dlg.rerun_requested.connect(self.start_rerun)
        dlg.exec()

    def start_rerun(self, sub_id: str, dry: bool, model: str = "", effort: str = ""):
        if sub_id in self.rerun_threads:
            return
        if self.state.is_demo and not dry and not self.state.api_key():
            QMessageBox.information(self, "Demo workspace",
                                    "The demo comes with sample AI results. To try the real AI on these made-up "
                                    "students, save an OpenAI API key on the Setup tab first.")
            return
        self.state.store.reset_screen(sub_id)
        glog.info("Re-run started for %s (model %s, effort %s, %s)", sub_id, model or "default",
                  effort or "default", "checks only" if dry else "AI")
        th = RerunThread(self.state, sub_id, dry, model or None, effort or None)
        th.done.connect(self._rerun_done)
        self.rerun_threads[sub_id] = th
        th.start()
        if sub_id == self.sub_id:
            self.open_student(sub_id)

    def _rerun_done(self, sub_id, ok, msg):
        self.rerun_threads.pop(sub_id, None)
        self.state.submissions_changed.emit()
        if sub_id == self.sub_id:
            self.open_student(sub_id)
        if not ok:
            glog.error("Re-run failed for %s: %s", sub_id, msg[:500])
            QMessageBox.warning(self, "Re-run failed", msg[:800])
        else:
            glog.info("Re-run finished for %s", sub_id)
