"""Grade overview for the Export tab: how the grades are spread, and which students may deserve a second look.

Each student is one dot. Dots stack in columns by score, so the stacks form a histogram and every dot can still
be pointed at: hovering shows the student, clicking opens them in Review and grade."""
from __future__ import annotations

import html
import json
import math
import statistics

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QToolTip,
                               QVBoxLayout, QWidget)

from ..names import sort_key
from ..scoring import compute, fmt
from .theme import ACCENT, MUTED, STATUS, WrapLabel
from .widgets import ClickCard, flow

GREY = "#94a3b8"


def quartiles(vals):
    """First and third quartile, or (None, None) with fewer than four values."""
    if len(vals) < 4:
        return None, None
    q = statistics.quantiles(vals, n=4, method="inclusive")
    return q[0], q[2]


class DotPlot(QWidget):
    open_student = Signal(str)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(230)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setMouseTracking(True)
        self.points: list[dict] = []     # {sid, name, value, reviewed}
        self.vmax = 100.0
        self.step = 5.0
        self.median = self.q1 = self.q3 = None
        self.dots: list[tuple[QPointF, float, dict]] = []
        self.hover = None
        self.setCursor(Qt.ArrowCursor)

    def sizeHint(self):
        return QSize(400, 240)

    def minimumSizeHint(self):
        return QSize(200, 230)

    def set_data(self, points: list[dict], vmax: float, step: float):
        self.points, self.vmax, self.step = points, max(vmax, 1e-9), step
        vals = [p["value"] for p in points]
        self.median = statistics.median(vals) if vals else None
        self.q1, self.q3 = quartiles(vals)
        self.hover = None
        self.update()

    def _layout(self):
        m_left, m_right, m_top, m_bottom = 36, 16, 14, 34
        plot = QRectF(m_left, m_top, max(10, self.width() - m_left - m_right),
                      max(10, self.height() - m_top - m_bottom))
        nb = max(1, int(round(self.vmax / self.step)) + 1)
        bins: dict[int, list[dict]] = {}
        for p in self.points:
            b = int(round(p["value"] / self.step))
            bins.setdefault(min(max(b, 0), nb - 1), []).append(p)
        tallest = max((len(v) for v in bins.values()), default=1)
        col_w = plot.width() / nb
        r = max(2.5, min(6.5, col_w / 2 - 3.5, (plot.height() / max(tallest, 1)) / 2 - 2.5))
        dots = []
        for b, items in bins.items():
            cx = plot.left() + (b + 0.5) * col_w
            items = sorted(items, key=lambda p: (not p["reviewed"], sort_key(p["name"])))
            per_row = max(1, int((col_w - 2) // (2 * r + 5)))
            for k, p in enumerate(items):
                row, colk = divmod(k, per_row)
                off = (colk - (min(per_row, len(items)) - 1) / 2) * (2 * r + 5)
                cy = plot.bottom() - r - 4 - row * (2 * r + 5)
                dots.append((QPointF(cx + off, cy), r, p))
        return plot, nb, col_w, dots, tallest

    def x_of(self, plot, v):
        return plot.left() + (v / self.step + 0.5) * (plot.width() / (int(round(self.vmax / self.step)) + 1))

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        plot, nb, col_w, dots, tallest = self._layout()
        self.dots = dots
        f = QFont(self.font())
        f.setPixelSize(11)
        p.setFont(f)
        # axis and ticks
        p.setPen(QPen(QColor("#cbd5e1"), 1))
        p.drawLine(QPointF(plot.left(), plot.bottom() + 0.5), QPointF(plot.right(), plot.bottom() + 0.5))
        tick = next(t for t in (1, 2, 5, 10, 20, 25, 50) if self.vmax / t <= 12) if self.vmax <= 600 else 100
        k = 0
        while k * tick <= self.vmax + 1e-9:
            x = self.x_of(plot, k * tick)
            p.setPen(QPen(QColor("#e2e8f0"), 1))
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            p.setPen(QColor(MUTED))
            p.drawText(QRectF(x - 20, plot.bottom() + 6, 40, 14), Qt.AlignCenter, fmt(k * tick))
            k += 1
        if not self.points:
            p.setPen(QColor(MUTED))
            p.drawText(plot, Qt.AlignCenter, "No fully graded students yet.")
            return
        # the middle half of the class as a shaded band, with the median as a line through it
        if self.q1 is not None and self.q3 is not None:
            x1, x3 = self.x_of(plot, self.q1), self.x_of(plot, self.q3)
            band = QColor(ACCENT)
            band.setAlpha(28)
            p.fillRect(QRectF(x1, plot.top(), max(x3 - x1, 2), plot.height()), band)
        if self.median is not None:
            x = self.x_of(plot, self.median)
            p.setPen(QPen(QColor(ACCENT), 1.6))
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            text = f"median {fmt(round(self.median, 1))}"
            if self.q1 is not None:
                text += f" · middle half {fmt(round(self.q1, 1))}–{fmt(round(self.q3, 1))}"
            tw = p.fontMetrics().horizontalAdvance(text) + 8
            box = QRectF(x - tw - 2, plot.top() - 2, tw, 14) if x + tw + 4 > plot.right() \
                else QRectF(x + 3, plot.top() - 2, tw, 14)
            p.fillRect(box, QColor("#ffffff"))
            p.setPen(QColor(ACCENT))
            p.drawText(box, Qt.AlignCenter, text)
        # dots: filled when reviewed, hollow when not, with an amber ring around those worth a second look
        for c, r, d in dots:
            if d.get("flag"):
                p.setPen(QPen(QColor(STATUS["yellow"][0]), 2))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(c, r + 2, r + 2)
            p.setPen(QPen(QColor(ACCENT) if d["reviewed"] else QColor(GREY), 1.2))
            p.setBrush(QColor(ACCENT) if d["reviewed"] else QColor("#ffffff"))
            p.drawEllipse(c, r, r)
        if self.hover is not None:
            c, r, d = self.hover
            p.setPen(QPen(QColor("#0f172a"), 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(c, r + 4, r + 4)

    def _hit(self, pos):
        best = None
        for c, r, d in self.dots:
            dist = math.hypot(c.x() - pos.x(), c.y() - pos.y())
            if dist <= r + 3 and (best is None or dist < best[0]):
                best = (dist, (c, r, d))
        return best[1] if best else None

    def mouseMoveEvent(self, e):
        h = self._hit(e.position())
        if (h and h[2]) != (self.hover and self.hover[2]):
            self.hover = h
            self.update()
        if h:
            d = h[2]
            self.setCursor(Qt.PointingHandCursor)
            QToolTip.showText(e.globalPosition().toPoint(),
                              f"<b>{html.escape(d['name'])}</b> ({html.escape(d['sid'])})<br/>{fmt(round(d['value'], 2))} / {fmt(self.vmax)}"
                              + ("" if d["reviewed"] else "<br/><i>not marked reviewed</i>")
                              + (f"<br/>{html.escape(d['flag'])}" if d.get("flag") else "")
                              + "<br/><span style='color:#64748b'>Click to open</span>", self)
        else:
            self.setCursor(Qt.ArrowCursor)
            QToolTip.hideText()

    def leaveEvent(self, _e):
        self.hover = None
        self.update()

    def mousePressEvent(self, e):
        h = self._hit(e.position())
        if h and e.button() == Qt.LeftButton:
            self.open_student.emit(h[2]["sid"])


class OverviewCard(QFrame):
    open_student = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 18, 16)
        v.setSpacing(8)
        t = QLabel("Grade overview")
        t.setObjectName("sectiontitle")
        v.addWidget(t)
        v.addWidget(WrapLabel("Each dot is a student, and stacked dots show how many share a score. The line is the "
                              "median and the shaded band holds the middle half of the class. Filled dots are "
                              "reviewed, hollow ones are graded but not yet marked reviewed, and an amber ring "
                              "means the student is on the list below. Hover for the name, click to open the "
                              "student.", "muted"))
        self.picker_box = QWidget()
        self.picker_lay = QHBoxLayout(self.picker_box)
        self.picker_lay.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.picker_box)
        self.plot = DotPlot()
        self.plot.open_student.connect(self.open_student)
        v.addWidget(self.plot)
        self.stats = QLabel("")
        self.stats.setObjectName("muted")
        v.addWidget(self.stats)
        h = QLabel("Worth a second look")
        h.setStyleSheet("font-weight: 600; padding-top: 6px;")
        v.addWidget(h)
        self.look_info = WrapLabel("", "muted")
        v.addWidget(self.look_info)
        self.look_box = QVBoxLayout()
        self.look_box.setSpacing(4)
        v.addLayout(self.look_box)
        self.measure = "total"
        self.show_all = False
        self.group = None
        self.pack = None
        self.data = []

    # -------------------------------------------------------------------------------------------------
    def _build_picker(self, pack):
        sig = ["total"] + [r.id for r in pack.rubric] + ["deductions"]
        if getattr(self, "_picker_sig", None) == sig:
            return
        self._picker_sig = sig
        while self.picker_lay.count():
            it = self.picker_lay.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().setParent(None)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        buttons = []
        for key, label in [("total", "Total")] + [(r.id, r.label) for r in pack.rubric] + \
                          [("deductions", "Integrity deductions")]:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setProperty("key", key)
            b.setChecked(key == self.measure)
            self.group.addButton(b)
            buttons.append(b)
        self.group.buttonClicked.connect(lambda b: self._pick(b.property("key")))
        self.picker_lay.addWidget(flow(*buttons, spacing=6))

    def _pick(self, key):
        self.measure = key
        self._draw()

    def refresh(self, state):
        st, pack = state.store, state.pack
        if not st or not pack:
            return
        self.pack = pack
        self._build_picker(pack)
        rows = st.submissions()
        data, flags = [], []
        for r in rows:
            rev = st.review(r["sub_id"])
            if not rev:
                continue
            res = compute(pack, rev)
            name = r["name"] or r["sub_id"]
            item = {"sid": r["sub_id"], "name": name, "rev": rev, "res": res,
                    "reviewed": bool(rev.get("reviewed")), "complete": res["complete"]}
            item["reasons"] = self._reasons(pack, r, rev, res, state)
            data.append(item)
        totals = [d["res"]["total"] for d in data if d["complete"]]
        if len(totals) >= 8:
            q1, q3 = quartiles(totals)
            reach = 1.5 * max(q3 - q1, pack.total_max * 0.05)
            for d in data:
                t = d["res"]["total"]
                if d["complete"] and (t < q1 - reach or t > q3 + reach):
                    d["reasons"].append(f"Total {fmt(t)} is far from the rest of the class (middle half "
                                        f"{fmt(round(q1, 1))}–{fmt(round(q3, 1))}).")
        self.data = data
        self._draw()
        self._fill_list()

    def _reasons(self, pack, row, rev, res, state) -> list[str]:
        out = []
        comments = rev.get("comments") or {}
        silent = [r["label"] for r in res["rows"] if r["level"] is not None and r["level"] <= 50
                  and not (comments.get(r["id"]) or "").strip()]
        if silent:
            out.append("Points lost without a comment for the student: " + ", ".join(silent) + ".")
        try:
            screen = json.loads(row["screen"]) if row["screen"] else {}
        except Exception:  # noqa: BLE001
            screen = {}
        if screen and screen.get("_meta", {}).get("model") not in (None, "offline"):
            srows = {x["row_id"]: x for x in screen.get("rows", [])}
            for r in res["rows"]:
                s = srows.get(r["id"], {})
                if r["level"] is None or s.get("confidence") != "high":
                    continue
                if s.get("status") == "red" and r["level"] == 100:
                    out.append(f"{r['label']}: the AI was confident of a problem, but it got 100%.")
                elif s.get("status") == "green" and r["level"] <= 25:
                    out.append(f"{r['label']}: the AI saw no problem, but it got {r['level']}%.")
        if state.meta(f"recheck:{row['sub_id']}"):
            out.append("AI re-run since grading: check again.")
        return out

    def _draw(self):
        pack = self.pack
        if pack is None:
            return
        key = self.measure
        pts = []
        for d in self.data:
            if key == "total":
                if not d["complete"]:
                    continue
                val, vmax, step = d["res"]["total"], pack.total_max, max(pack.total_max / 40, 1.0)
            elif key == "deductions":
                val, vmax = d["res"]["deduction_total"], max(pack.integrity_cap or pack.total_max, 1)
                step = max(vmax / 40, 1.0)
            else:
                r = next((x for x in d["res"]["rows"] if x["id"] == key), None)
                if not r or r["score"] is None:
                    continue
                val, vmax, step = r["score"], r["max"], r["max"] / 4
            pts.append({"sid": d["sid"], "name": d["name"], "value": float(val), "reviewed": d["reviewed"],
                        "flag": " ".join(d["reasons"])[:200] if d["reasons"] else ""})
        if key == "total":
            vmax, step = pack.total_max, max(pack.total_max / 40, 1.0)
        elif key == "deductions":
            vmax = max(pack.integrity_cap or pack.total_max, 1)
            step = max(vmax / 40, 1.0)
        else:
            row = next(x for x in pack.rubric if x.id == key)
            vmax, step = row.max, row.max / 4
        self.plot.set_data(pts, vmax, step)
        if pts:
            vals = [p["value"] for p in pts]
            q1, q3 = quartiles(vals)
            left = sum(1 for d in self.data if not d["complete"]) if key == "total" else 0
            self.stats.setText(f"{len(vals)} students · median {fmt(round(statistics.median(vals), 2))}"
                               + (f" · middle half {fmt(round(q1, 2))} to {fmt(round(q3, 2))}" if q1 is not None
                                  else "")
                               + f" · lowest {fmt(round(min(vals), 2))} · highest {fmt(round(max(vals), 2))} "
                               f"(out of {fmt(vmax)})"
                               + (f" · {left} not fully graded, not shown" if left else ""))
        else:
            self.stats.setText("")

    def _fill_list(self):
        while self.look_box.count():
            it = self.look_box.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().setParent(None)
        flagged = [d for d in self.data if d["reasons"]]
        if not flagged:
            self.look_info.setText("Nothing stands out. Students appear here when points were lost without a "
                                   "comment, a grade differs sharply from a confident AI flag, a total is far from "
                                   "the rest, or the AI was re-run after grading.")
            return
        self.look_info.setText(f"{len(flagged)} {'student' if len(flagged) == 1 else 'students'}. These are "
                               "prompts, not errors. Click a student to open them.")
        flagged.sort(key=lambda d: (-len(d["reasons"]), sort_key(d["name"])))
        shown = flagged if self.show_all or len(flagged) <= 8 else flagged[:6]
        for d in shown:
            txt = f"<b>{html.escape(d['name'])}</b> ({html.escape(d['sid'])}): " + html.escape(" ".join(d["reasons"]))
            self.look_box.addWidget(ClickCard(txt, STATUS["yellow"][0], lambda s=d["sid"]: self.open_student.emit(s)))
        if len(shown) < len(flagged):
            more = QPushButton(f"Show all {len(flagged)}")
            more.clicked.connect(self._show_all)
            self.look_box.addWidget(flow(more))

    def _show_all(self):
        self.show_all = True
        self._fill_list()
