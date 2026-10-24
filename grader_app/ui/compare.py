"""Similar work: the automatic check after a pre-screen, and the side-by-side window opened from a finding."""
from __future__ import annotations

import html

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QScrollArea, QSplitter, QVBoxLayout, QWidget

from ..applog import log as glog
from .. import similarity
from .pdf_view import PdfView
from .state import AppState
from .theme import ACCENT, WrapLabel
from .widgets import ClickCard

GUIDE = ("Signs of copying are the same unusual wording or explanation, identical code down to comments, variable "
         "names and layout, the same mistakes or typos, and the same AI conversation. Standard definitions, "
         "textbook proof steps and short standard code are ordinary overlap. A match alone is not proof.")


class CompareThread(QThread):
    """Runs the similarity check and turns flagged pairs into findings. Emits (report, new findings, error)."""
    progress = Signal(str, int, int)
    done = Signal(dict, int, str)

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.workspace = state.workspace          # the results belong to this workspace only
        self.store, self.pack = state.store, state.pack
        self._stop = False

    def stop(self):
        """Ask the check to end early, for example when the app is closed. Nothing is saved then."""
        self._stop = True

    def _progress(self, stage, i, n):
        if self._stop:
            raise InterruptedError("stopped")
        self.progress.emit(stage, i, n)

    def run(self):
        try:
            rep = similarity.run(self.store, self.pack, self.workspace, progress=self._progress)
            self.done.emit(rep, 0, "")
        except InterruptedError:
            self.done.emit({}, 0, "stopped")
        except Exception as e:  # noqa: BLE001
            self.done.emit({}, 0, f"{type(e).__name__}: {e}")


def save_and_apply(state: AppState, rep: dict, workspace=None) -> int | None:
    """Keep the report in the workspace and add a finding to each student of a flagged pair (once). Runs on the
    main thread. The student on screen is saved first and shown again afterwards, so grading can go on during a
    check. Returns None when the workspace was switched while the check ran (the result is then dropped)."""
    if workspace is not None and state.workspace != workspace:
        return None
    state.flush()
    state.set_meta(similarity.REPORT_KEY, rep)
    n = similarity.add_findings(state.store, state.pack, rep, state.meta("reviewer", "") or "")
    if n:
        glog.info("Similar work findings added: %s (pairs: %s)", n,
                  ", ".join(f"{p['a']}-{p['b']}" for p in rep.get("pairs", [])))
    if n:
        state.reload_student.emit()
        state.reviews_changed.emit()
        state.submissions_changed.emit()
    return n


class SideView(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        self.head = QLabel("")
        self.head.setTextFormat(Qt.RichText)
        v.addWidget(self.head)
        self.where = QLabel("")
        self.where.setObjectName("muted")
        v.addWidget(self.where)
        self.pdf = PdfView()
        v.addWidget(self.pdf, 1)

    def show_student(self, name: str, sid: str, path: str | None):
        self.head.setText(f"<b>{html.escape(name)}</b> <span style='color:#64748b'>({html.escape(sid)})</span>")
        self.pdf.load(path)
        if path:
            self.pdf.fit_width()          # two papers side by side: show whole page widths


class CompareWindow(QDialog):
    """Two papers next to each other, with the shared passages listed. Opened from a Similar work finding."""

    def __init__(self, state: AppState, pair: dict, me: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compare side by side")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.resize(1500, 950)
        # the student being graded on the left
        if me and pair["b"] == me:
            pair = similarity.swap(pair)
        self.pair = pair
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        split = QSplitter(Qt.Horizontal)
        lay.addWidget(split)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(4, 4, 10, 10)
        lv.setSpacing(8)
        t = QLabel("Shared passages")
        t.setObjectName("h1")
        lv.addWidget(t)
        secs = ", ".join(f"{k} {v:,}" for k, v in sorted(pair["by_section"].items(), key=lambda x: -x[1]))
        lv.addWidget(WrapLabel(
            f"<b>{html.escape(pair['a_name'])}</b> (left) and <b>{html.escape(pair['b_name'])}</b> (right) share "
            f"{pair['shared_words']:,} words in {len(pair['passages'])} passages ({html.escape(secs)}). Click a "
            "passage to see it in both papers, marked in yellow."))
        g = WrapLabel(GUIDE, "muted")
        lv.addWidget(g)
        lv.addWidget(WrapLabel("Decide the finding in the grading panel when you are done: Rejected if the overlap "
                               "is ordinary, or a penalty if it is copying.", "muted"))
        self.cards = []
        for k, q in enumerate(pair["passages"], 1):
            sec = q["section"] if q["section"] == q["b_section"] else f"{q['section']} ↔ {q['b_section']}"
            txt = (f"<b>{k}. {html.escape(sec)}</b> · p.{q['a_page']} ↔ p.{q['b_page']} · {q['words']:,} words"
                   f"<br/><span style='color:#475569'>“{html.escape(q['preview'][:160])}”</span>")
            c = ClickCard(txt, ACCENT, lambda q=q, k=k: self.show_passage(q, k))
            lv.addWidget(c)
            self.cards.append(c)
        lv.addStretch(1)
        left_scroll.setWidget(left)
        left_scroll.setMinimumWidth(280)
        split.addWidget(left_scroll)

        pdfs = QSplitter(Qt.Horizontal)
        self.side_a, self.side_b = SideView(), SideView()
        pdfs.addWidget(self.side_a)
        pdfs.addWidget(self.side_b)
        split.addWidget(pdfs)
        split.setChildrenCollapsible(False)
        split.setSizes([360, 1100])
        split.setStretchFactor(1, 1)
        st = state.store
        ra, rb = st.submission(pair["a"]), st.submission(pair["b"])
        self.side_a.show_student(pair["a_name"], pair["a"], ra["pdf_path"] if ra else None)
        self.side_b.show_student(pair["b_name"], pair["b"], rb["pdf_path"] if rb else None)
        if pair["passages"]:
            # after the papers are laid out, so the page positions are known
            QTimer.singleShot(80, lambda: self.show_passage(pair["passages"][0], 1))

    def show_passage(self, q: dict, k: int):
        self.side_a.pdf.show_rects({int(pg): r for pg, r in q["a_rects"].items()}, q["a_page"])
        self.side_b.pdf.show_rects({int(pg): r for pg, r in q["b_rects"].items()}, q["b_page"])
        self.side_a.where.setText(f"Passage {k}: page {q['a_page']}, {q['section']}")
        self.side_b.where.setText(f"Passage {k}: page {q['b_page']}, {q['b_section']}")
