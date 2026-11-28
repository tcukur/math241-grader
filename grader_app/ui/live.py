"""Live view of the pre-screen: one row per document in progress, showing which step it is on."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from .theme import ACCENT, ACCENT_SOFT, STATUS

STEPS = [("text", "Read PDF"), ("checks", "Checks"), ("prepare", "Prepare"), ("ai", "AI"), ("save", "Save")]
STEP_HELP = {
    "text": "Reading the PDF and finding the report, AI record and code",
    "checks": "Automatic checks: screenshots, links, headings, reference values",
    "prepare": "Removing names and IDs, preparing pages for the AI",
    "ai": "Waiting for the AI's answer (usually under a minute)",
    "save": "Saving the result",
}
_CHIP = "border-radius: 9px; padding: 2px 8px; font-size: 12px;"


def _fmt(sec: float) -> str:
    s = int(sec)
    return f"{s // 60}:{s % 60:02d}"


class LiveRow(QFrame):
    def __init__(self, name: str, dry: bool, started: float | None = None):
        super().__init__()
        self.setObjectName("liverow")
        self.setFixedHeight(32)     # rows never squash; the box scrolls instead
        self.started = started or time.monotonic()
        self.finished_at: float | None = None
        self.state = "running"
        self.steps = [s for s in STEPS if not (dry and s[0] in ("prepare", "ai"))]
        self.current = None
        self.done: set[str] = set()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 5, 10, 5)
        lay.setSpacing(6)
        self.name = QLabel()
        self.name.setFixedWidth(230)    # same on every row, so the step chips line up
        self.name.setText(QFontMetrics(self.name.font()).elidedText(name, Qt.ElideRight, 224))
        self.name.setToolTip(name)
        lay.addWidget(self.name)
        self.chips = {}
        for key, label in self.steps:
            c = QLabel(label)
            c.setToolTip(STEP_HELP.get(key, ""))
            c.setAlignment(Qt.AlignCenter)
            # fixed width, wide enough for the longest form ("✓ Read PDF" in bold), so chips never jump or clip
            f = c.font()
            f.setBold(True)
            c.setFixedWidth(QFontMetrics(f).horizontalAdvance("✓ " + label) + 22)
            self.chips[key] = c
            lay.addWidget(c)
        self.detail = QLabel("")
        self.detail.setObjectName("muted")
        self.detail.setMinimumWidth(0)
        self.detail.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.detail.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.detail, 1)
        self.clock = QLabel("0:00")
        self.clock.setObjectName("muted")
        self.clock.setFixedWidth(64)
        self.clock.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.clock)
        self._paint()

    def set_stage(self, stage: str):
        retry = stage.startswith("retry")
        key = "ai" if retry else stage
        order = [k for k, _ in self.steps]
        if key in order:
            for k in order[:order.index(key)]:
                self.done.add(k)
            self.current = key
        self.detail.setText(f"retrying, attempt {stage[5:]} of 4" if retry else STEP_HELP.get(key, ""))
        self._paint()

    def finish(self, state: str, msg: str = "", when: float | None = None):
        self.finished_at = when or time.monotonic()
        self.state = "error" if state == "error" else "done"
        if self.state == "done":
            self.done.update(k for k, _ in self.steps)
            self.current = None
            self.detail.setText("Done")
        else:
            self.detail.setText("Error: " + (msg[:80] or "see the log below"))
        self._paint()
        self.tick()

    def tick(self):
        end = self.finished_at or time.monotonic()
        self.clock.setText(_fmt(end - self.started))

    def _paint(self):
        green_fg, green_bg = STATUS["green"][0], STATUS["green"][1]
        red_fg, red_bg = STATUS["red"][0], STATUS["red"][1]
        for key, c in self.chips.items():
            if key in self.done:
                c.setText("✓ " + dict(self.steps)[key])
                c.setStyleSheet(f"{_CHIP} background: {green_bg}; color: {green_fg};")
            elif key == self.current and self.state == "error":
                c.setText(dict(self.steps)[key])
                c.setStyleSheet(f"{_CHIP} background: {red_bg}; color: {red_fg}; font-weight: 600;")
            elif key == self.current:
                c.setText("● " + dict(self.steps)[key])
                c.setStyleSheet(f"{_CHIP} background: {ACCENT_SOFT}; color: {ACCENT}; font-weight: 600;")
            else:
                c.setText(dict(self.steps)[key])
                c.setStyleSheet(f"{_CHIP} background: #f1f3f6; color: #94a3b8;")
        if self.state == "error":
            self.detail.setStyleSheet(f"color: {red_fg};")
        elif self.state == "done":
            self.detail.setStyleSheet(f"color: {green_fg};")
        else:
            self.detail.setStyleSheet("")


class LivePanel(QFrame):
    """'Now processing' box. Keeps the documents in progress, plus the most recent finished ones until their
    place is needed."""

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 8)
        outer.setSpacing(4)
        head = QHBoxLayout()
        t = QLabel("<b>Now processing</b>")
        head.addWidget(t)
        self.summary = QLabel("Idle. Press Start to pre-screen.")
        self.summary.setObjectName("muted")
        head.addWidget(self.summary, 1)
        outer.addLayout(head)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.NoFrame)
        self.inner = QWidget()
        self.rows_lay = QVBoxLayout(self.inner)
        self.rows_lay.setContentsMargins(0, 0, 0, 0)
        self.rows_lay.setSpacing(3)
        self.rows_lay.addStretch(1)
        self.area.setWidget(self.inner)
        outer.addWidget(self.area, 1)
        self.rows: dict[str, LiveRow] = {}
        self.max_rows = 4
        self.dry = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    def begin(self, workers: int, dry: bool, total: int):
        self.clear()
        self.max_rows = max(1, workers)
        self.dry = dry
        self.total, self.finished = total, 0
        self.summary.setText(f"Starting {total} {'document' if total == 1 else 'documents'}…")
        self.timer.start(1000)

    def clear(self):
        for r in list(self.rows.values()):
            r.setParent(None)
            r.deleteLater()
        self.rows = {}

    def stage(self, sid: str, name: str, label: str, stage: str, when: float | None = None):
        row = self.rows.get(sid)
        if row is None:
            # make room: drop the oldest finished rows beyond the number of parallel workers
            finished = [k for k, r in self.rows.items() if r.state != "running"]
            while len(self.rows) >= self.max_rows + 2 and finished:
                old = self.rows.pop(finished.pop(0))
                old.setParent(None)
                old.deleteLater()
            row = LiveRow(label, self.dry, when)
            self.rows[sid] = row
            running = sum(1 for r in self.rows.values() if r.state == "running")
            self.rows_lay.insertWidget(running - 1, row)
            row.show()
        row.set_stage(stage)
        self._summary()

    def note_finish_time(self, sid: str, when: float):
        self._finish_times = getattr(self, "_finish_times", {})
        self._finish_times[sid] = when

    def finish(self, sid: str, state: str, msg: str):
        row = self.rows.get(sid)
        if row is not None:
            row.finish(state, msg, getattr(self, "_finish_times", {}).pop(sid, None))
            # finished rows move below the ones still running
            self.rows_lay.removeWidget(row)
            running = sum(1 for r in self.rows.values() if r.state == "running")
            self.rows_lay.insertWidget(running, row)
            row.show()
        self.finished += 1
        self._summary()

    def end(self, stopped: bool):
        self.timer.stop()
        for r in self.rows.values():
            if r.state == "running":
                r.detail.setText("paused")
        self.summary.setText(("Paused. " if stopped else "Finished. ")
                             + f"{self.finished} of {self.total} done in this run.")

    def _summary(self):
        running = sum(1 for r in self.rows.values() if r.state == "running")
        self.summary.setText(f"{self.finished} of {self.total} done · {running} in progress")

    def _tick(self):
        for r in self.rows.values():
            if r.state == "running":
                r.tick()
