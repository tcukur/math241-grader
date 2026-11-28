"""Small layout helpers that keep the interface readable at any window size."""
from __future__ import annotations

import html

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLabel, QLayout, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from .theme import ACCENT


class FlowLayout(QLayout):
    """Lays widgets out left to right and wraps to the next line when there is no room,
    so buttons never overlap or get cut off on a narrow window."""

    def __init__(self, parent=None, spacing: int = 6):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test=False)

    def sizeHint(self):
        """Preferred size: everything on one line."""
        w = h = 0
        for it in self._items:
            if it.widget() is not None and not it.widget().isVisibleTo(self.parentWidget()):
                continue
            hint = it.sizeHint()
            w += hint.width() + self._spacing
            h = max(h, hint.height())
        m = self.contentsMargins()
        return QSize(max(0, w - self._spacing) + m.left() + m.right(), h + m.top() + m.bottom())

    def minimumSize(self):
        size = QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, test):
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = eff.x(), eff.y(), 0
        for it in self._items:
            if it.widget() is not None and not it.widget().isVisibleTo(self.parentWidget()):
                continue
            hint = it.sizeHint()
            nx = x + hint.width() + self._spacing
            if nx - self._spacing > eff.right() + 1 and line_h > 0:
                x, y = eff.x(), y + line_h + self._spacing
                nx = x + hint.width() + self._spacing
                line_h = 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x, line_h = nx, max(line_h, hint.height())
        return y + line_h - rect.y() + m.bottom()


def flow(*widgets, spacing: int = 6) -> QWidget:
    w = QWidget()
    lay = FlowLayout(w, spacing)
    for x in widgets:
        lay.addWidget(x)
    w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
    return w


def labelled(title: str, text: str, muted: bool = False) -> QLabel:
    """A paragraph with a bold lead-in, for example 'What to check: ...'."""
    colour = "color:#6b7280;" if muted else ""
    lb = QLabel(f"<span style='{colour}'><b>{html.escape(title)}</b> {html.escape(text)}</span>")
    lb.setWordWrap(True)
    lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lb


def evidence_block(evidence: list, on_jump) -> QWidget | None:
    """'Where:' with one button per cited page, and the quoted words under it."""
    items = [e for e in evidence if e.get("page")][:6]
    if not items:
        return None
    box = QWidget()
    v = QVBoxLayout(box)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(3)
    buttons = []
    quotes = []
    for ev in items:
        src = {"report": "report", "chat": "AI record", "code": "code"}.get(ev.get("source"), ev.get("source", ""))
        b = QPushButton(f"Go to p.{ev['page']}" + (f" · {src}" if src else ""))
        b.setObjectName("jump")
        b.setCursor(Qt.PointingHandCursor)
        exc = (ev.get("excerpt") or "").strip()
        if exc:
            b.setToolTip(f"Highlights: “{exc}”")
            note = (" <span style='color:#b7791f'>(quote not found in the PDF, check it)</span>"
                    if ev.get("unverified") else "")
            quotes.append(f"p.{ev['page']}: “{html.escape(exc[:110])}”{note}")
        b.clicked.connect(lambda _=False, p=ev["page"], e=exc: on_jump(int(p), e))
        buttons.append(b)
    head = QLabel("<b>Where:</b>")
    v.addWidget(flow(head, *buttons))
    if quotes:
        q = QLabel("<span style='color:#6b7280'>" + "<br/>".join(quotes) + "</span>")
        q.setWordWrap(True)
        q.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(q)
    return box


JUMP_STYLE = f"""
QPushButton#jump {{ padding: 3px 10px; border: 1px solid #c9d4f5; color: {ACCENT}; border-radius: 11px;
                    background: #f3f6fe; font-weight: 500; }}
QPushButton#jump:hover {{ background: #e6ecfc; border-color: {ACCENT}; }}
QPushButton#todo {{ text-align: left; padding: 6px 8px; border: 1px solid #e3e7ee; border-radius: 8px;
                    background: white; }}
QPushButton#todo:hover {{ background: #f3f6fe; border-color: {ACCENT}; }}
"""


class ClickCard(QWidget):
    """A whole-row clickable item with wrapped text, used for the 'To check' list."""

    def __init__(self, text: str, colour: str, on_click):
        super().__init__()
        from .theme import WrapLabel
        self.on_click = on_click
        self.setObjectName("todoitem")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"QWidget#todoitem {{ background: white; border: 1px solid #e3e7ee; "
                           f"border-left: 4px solid {colour}; border-radius: 8px; }}"
                           f"QWidget#todoitem:hover {{ background: #f3f6fe; border-color: #c9d4f5; "
                           f"border-left: 4px solid {colour}; }}")
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        self.label = WrapLabel(text)
        self.label.setTextFormat(Qt.RichText)   # the text is HTML-escaped; render it, do not show &quot;
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self.label)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.on_click()
        super().mouseReleaseEvent(e)
