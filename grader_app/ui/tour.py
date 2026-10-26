"""The guided tour: a short walk through the four tabs on the demo workspace.

Each step dims the window, leaves the part it talks about lit, and shows a note next to it. The note always has
Skip tour, Back and Next, the step number, and links to jump to any tab's part of the tour. Arrow keys and Enter
move on, Escape ends it. While the tour runs, the window cannot be clicked, so nothing changes by accident."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from .theme import ACCENT

TABS = ["Setup", "Pre-screen", "Review and grade", "Export"]


@dataclass
class Step:
    tab: int | None                     # which tab to show; None keeps the current one
    title: str
    text: str
    targets: Callable[[], list] | None = None     # widgets to light up; none means a note in the middle
    before: Callable[[], None] | None = None     # anything to arrange before the step is shown


def steps(win) -> list[Step]:
    s, r, v, e = win.setup, win.run, win.review, win.export
    btn = lambda row, name: row.buttons.get(name)

    def ceren():
        v.select_student("7003")

    def first_card():
        cards = [c for c in getattr(v, "row_cards", []) if c.isVisible()]
        return cards[:1] or [v.panel_scroll]

    def show_first_card():
        cards = getattr(v, "row_cards", [])
        if cards:
            v.panel_scroll.ensureWidgetVisible(cards[0], 0, 40)

    def findings():
        cards = [c for c in getattr(v, "finding_cards", []) if c.isVisible()]
        return cards[:1] or [v.panel_scroll]

    def show_finding():
        cards = getattr(v, "finding_cards", [])
        if cards:
            v.panel_scroll.ensureWidgetVisible(cards[0], 0, 40)

    def top_of_panel():
        v.panel_scroll.verticalScrollBar().setValue(0)

    return [
        Step(None, "Welcome",
             "This short tour shows how a grading session goes, from importing the submissions to the files for "
             "Moodle. It runs on a demo workspace with six made-up students. Their AI results were written in "
             "advance, so the tour needs no API key.<br/><br/>It takes about three minutes. You can "
             "skip it at any point and take it again from <b>Help › Take the tour</b>."),
        Step(0, "Four steps, left to right",
             "A grading session goes through these tabs in order. You can come back to any of them later.",
             lambda: [win.tabs.tabbar]),
        Step(0, "One workspace per assignment",
             "A workspace is a folder that holds everything for one assignment: the grading, and copies of the "
             "student PDFs, the assignment and the class list. Everything is saved as you go. <b>Backups…</b> "
             "lets you go back to an earlier state.",
             lambda: [s.ws_row, s.reviewer]),
        Step(0, "The assignment and its rubric",
             "The assignment folder holds the handout, the instructor guide and the rubric. <b>Points and "
             "penalties…</b> sets the points of each rubric item and what each integrity finding costs. <b>New "
             "from documents…</b> has the AI draft a rubric from a handout and a solution.",
             lambda: [s.pack_row, s.pack_info]),
        Step(0, "Bring in the submissions",
             "Choose the Moodle download and, if you have it, the class list. <b>Import all documents</b> copies "
             "them in and matches each submission to a student. Use it again later for late uploads.",
             lambda: [s.sub_row, s.ws_csv_row, s.scan_btn]),
        Step(0, "AI access",
             "The AI pre-screen needs an OpenAI API key, which stays on this computer. A TA can load an access "
             "file from the instructor instead. The demo works without one. With a key saved, the AI parts work "
             "here too, on the made-up students.",
             lambda: [s.key_row]),
        Step(1, "Pre-screen with the AI",
             "<b>Start</b> sends each submission to the AI, which marks what looks fine and what needs a closer "
             "look. Choose the model and how much effort it spends. The cost estimate above is shown before "
             "anything is spent. The demo students are already done. With a key, select some and press <b>Re-screen "
             "selected</b>, then <b>Start</b>, to see the real AI at work.",
             lambda: [r.summary, r.opts_row]),
        Step(1, "What the AI is told",
             "<b>AI instructions…</b> shows exactly what the AI is told for every student. A note here adds "
             "guidance for the whole class, for example an answer format that is acceptable.",
             lambda: [r.instr_btn, r.global_note]),
        Step(1, "One line per student",
             "What the automatic checks and the AI flagged for each student. Double-click a student to open them "
             "for grading.",
             lambda: [r.table]),
        Step(2, "The class list",
             "The coloured dot shows what needs attention. In the demo, three students are graded and three are "
             "left for you: Ceren, Deniz and İlker.",
             lambda: [v.left_col], ceren),
        Step(2, "The submission",
             "The student's PDF. Where the AI points to a passage, it is highlighted here.",
             lambda: [v.pdf]),
        Step(2, "Grade each rubric item",
             "Each item shows what the AI saw, coloured green, amber or red. You pick the level and can add a "
             "comment for the student. Comments you wrote for other students are offered again.",
             first_card, show_first_card),
        Step(2, "Integrity findings",
             "Problems such as results the code does not produce, or work very similar to another student's, "
             "come as findings. You decide each one, and only confirmed findings cost points. Ceren and Deniz "
             "share long passages: <b>Compare side by side</b> shows them next to each other.",
             findings, show_finding),
        Step(2, "Finish a student",
             "The total updates as you grade. <b>Mark reviewed and next</b> saves and moves on. Keyboard "
             "shortcuts let you grade without the mouse.",
             lambda: [v.footer], top_of_panel),
        Step(3, "See the whole class",
             "The grade overview shows the median, the middle half of the class, and any scores worth a second "
             "look.",
             lambda: [e.overview]),
        Step(3, "Export",
             "<b>Export</b> writes one feedback PDF per student, with the scores, comments and confirmed "
             "findings, and the files to upload to Moodle.",
             lambda: [e.go]),
        Step(None, "That's the tour",
             "Try grading Ceren, Deniz and İlker on <b>Review and grade</b>. Nothing here affects real work. With an "
             "API key saved, you can also re-screen students, re-run the AI for one student, or have the AI draft "
             "a rubric (<b>New from documents…</b> on Setup, with the demo's handout and guide already filled in).<br/>"
             "<br/>When you are ready, open or make your own workspace on <b>Setup</b>. The tour stays under "
             "<b>Help › Take the tour</b>."),
    ]


class TourOverlay(QWidget):
    """Covers the main window while the tour runs."""

    def __init__(self, win, on_finish: Callable[[bool], None] | None = None):
        super().__init__(win)
        self.win = win
        self.on_finish = on_finish
        self.steps = steps(win)
        self.i = 0
        self.hole = QRect()
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setFocusPolicy(Qt.StrongFocus)
        self.bubble = QFrame(self)
        self.bubble.setObjectName("tourbubble")
        self.bubble.setStyleSheet(
            "QFrame#tourbubble { background: white; border-radius: 12px; border: 1px solid #d5dbe5; }"
            "QLabel#tourtitle { font-size: 16px; font-weight: 600; }"
            "QLabel#tourcount { color: #64748b; font-size: 12px; }"
            "QPushButton#tourjump { border: none; background: transparent; color: #64748b; padding: 1px 4px; "
            "font-size: 12px; }"
            "QPushButton#tourjump:hover { color: " + ACCENT + "; text-decoration: underline; }"
            "QPushButton#tourjump:disabled { color: " + ACCENT + "; font-weight: 600; }")
        b = QVBoxLayout(self.bubble)
        b.setContentsMargins(18, 14, 18, 14)
        b.setSpacing(8)
        top = QHBoxLayout()
        self.count = QLabel("")
        self.count.setObjectName("tourcount")
        top.addWidget(self.count)
        top.addStretch(1)
        self.jumps = []
        for k, name in enumerate(TABS):
            j = QPushButton(name)
            j.setObjectName("tourjump")
            j.setCursor(Qt.PointingHandCursor)
            j.setToolTip(f"Jump to the {name} part of the tour")
            j.clicked.connect(lambda _c=False, k=k: self.jump(k))
            top.addWidget(j)
            self.jumps.append(j)
        b.addLayout(top)
        self.title = QLabel("")
        self.title.setObjectName("tourtitle")
        self.title.setWordWrap(True)
        b.addWidget(self.title)
        self.text = QLabel("")
        self.text.setWordWrap(True)
        self.text.setTextFormat(Qt.RichText)
        self.text.setStyleSheet("line-height: 140%;")
        b.addWidget(self.text)
        row = QHBoxLayout()
        self.skip = QPushButton("Skip tour")
        self.skip.setToolTip("End the tour (Esc). You can take it again from Help.")
        self.skip.clicked.connect(lambda: self.finish(False))
        row.addWidget(self.skip)
        row.addStretch(1)
        self.back = QPushButton("Back")
        self.back.clicked.connect(lambda: self.go(self.i - 1))
        row.addWidget(self.back)
        self.next = QPushButton("Next")
        self.next.setObjectName("primary")
        self.next.clicked.connect(lambda: self.go(self.i + 1))
        row.addWidget(self.next)
        b.addLayout(row)
        win.installEventFilter(self)
        self.setGeometry(win.rect())
        self.show()
        self.raise_()
        self.go(0)

    # moving through the steps -------------------------------------------------------------------
    def jump(self, tab: int):
        k = next((n for n, st in enumerate(self.steps) if st.tab == tab), None)
        if k is not None:
            self.go(k)

    def go(self, k: int):
        if k >= len(self.steps):
            self.finish(True)
            return
        self.i = max(0, k)
        st = self.steps[self.i]
        if st.tab is not None and self.win.tabs.currentIndex() != st.tab:
            self.win.tabs.setCurrentIndex(st.tab)
        if st.before:
            try:
                st.before()
            except Exception:  # noqa: BLE001
                pass
        n = len(self.steps)
        self.count.setText(f"{self.i + 1} of {n}")
        self.title.setText(st.title)
        self.text.setText(st.text)
        self.back.setEnabled(self.i > 0)
        last = self.i == n - 1
        self.next.setText("Finish" if last else "Next")
        self.skip.setVisible(not last)
        current = st.tab if st.tab is not None else -1
        for j, btn in enumerate(self.jumps):
            btn.setEnabled(j != current)
        self.setFocus()
        # let the tab lay itself out before measuring where the lit part is
        QTimer.singleShot(0, self.place)
        QTimer.singleShot(120, self.place)

    def _targets(self) -> list[QWidget]:
        st = self.steps[self.i]
        if not st.targets:
            return []
        try:
            return [w for w in st.targets() if w is not None and w.isVisible()]
        except Exception:  # noqa: BLE001
            return []

    def _scroll_into_view(self, w: QWidget):
        p = w.parentWidget()
        while p is not None:
            if isinstance(p, QScrollArea) and p is not getattr(self.win.review, "panel_scroll", None):
                p.ensureWidgetVisible(w, 0, 30)
                return
            p = p.parentWidget()

    def place(self):
        if not self.isVisible():
            return
        self.setGeometry(self.win.rect())
        ts = self._targets()
        rect = QRect()
        for w in ts:
            self._scroll_into_view(w)
        for w in ts:
            r = QRect(w.mapTo(self.win, QPoint(0, 0)), w.size())
            rect = r if rect.isNull() else rect.united(r)
        self.hole = rect.adjusted(-6, -6, 6, 6).intersected(self.rect().adjusted(4, 4, -4, -4)) if ts else QRect()
        self._place_bubble()
        self.update()

    def _place_bubble(self):
        W, H = self.width(), self.height()
        bw = min(440, W - 32)
        self.bubble.setFixedWidth(bw)
        self.bubble.adjustSize()
        bh = self.bubble.sizeHint().height()
        self.bubble.resize(bw, bh)
        h = self.hole
        if h.isNull():
            x, y = (W - bw) // 2, (H - bh) // 2
        else:
            gap = 14
            spots = [(h.left(), h.bottom() + gap),                      # below
                     (h.left(), h.top() - gap - bh),                    # above
                     (h.right() + gap, h.top()),                        # right
                     (h.left() - gap - bw, h.top())]                    # left
            m = 16                                                      # kept clear of the window edge
            fits = [(x, y) for x, y in spots if m <= y and y + bh <= H - m and
                    (m <= x <= W - bw - m or (x == h.left() and not QRect(max(m, min(x, W - bw - m)), y, bw, bh)
                                               .intersects(h)))]
            if fits:
                x, y = fits[0]
            else:
                # a small window or a big lit area: top or bottom corner, whichever covers less of it
                cands = [(cx, cy) for cy in (16, H - bh - 16) for cx in (16, W - bw - 16)]
                x, y = min(cands, key=lambda c: (QRect(c[0], c[1], bw, bh).intersected(h).width()
                                                  * QRect(c[0], c[1], bw, bh).intersected(h).height()))
        x = max(16, min(x, W - bw - 16))
        y = max(16, min(y, H - bh - 16))
        self.bubble.move(x, y)
        self.bubble.raise_()

    # drawing and input ----------------------------------------------------------------------------
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        if not self.hole.isNull():
            lit = QPainterPath()
            lit.addRoundedRect(QRectF(self.hole), 10, 10)
            path = path.subtracted(lit)
        p.fillPath(path, QColor(15, 23, 42, 150))
        if not self.hole.isNull():
            p.setPen(QPen(QColor(ACCENT), 3))
            p.drawRoundedRect(QRectF(self.hole), 10, 10)

    def mousePressEvent(self, e):
        e.accept()          # the window under the tour is not clickable while it runs

    def wheelEvent(self, e):
        e.accept()

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_Right, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.go(self.i + 1)
        elif k == Qt.Key_Left:
            self.go(self.i - 1)
        elif k == Qt.Key_Escape:
            self.finish(False)
        else:
            e.accept()

    def eventFilter(self, obj, ev):
        if obj is self.win and ev.type() == QEvent.Resize:
            QTimer.singleShot(0, self.place)
        return False

    def finish(self, completed: bool):
        self.win.removeEventFilter(self)
        self.hide()
        self.deleteLater()
        if self.on_finish:
            self.on_finish(completed)
