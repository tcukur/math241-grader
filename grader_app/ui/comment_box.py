"""The comment box for a rubric item or a finding: what the student will read.

It grows from one line to a few as the text needs, and can show a suggested comment drafted by the AI in grey
inside the empty box. Grey text is never saved or sent: Tab (or the small arrow at the right) makes it a real
comment, typing replaces it. Small icons can sit at the right inside the box (the earlier-comments list)."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QTextCursor, QTextOption
from PySide6.QtWidgets import QCompleter, QFrame, QHBoxLayout, QPlainTextEdit, QToolButton, QWidget

MAX_LINES = 5


class CommentBox(QPlainTextEdit):
    edited = Signal(str)

    def __init__(self, text: str = "", placeholder: str = ""):
        super().__init__()
        self._default_placeholder = placeholder
        self.suggestion = ""
        self._shown = False                      # whether the grey text is the suggestion just now
        self.setPlaceholderText(placeholder)
        self.setTabChangesFocus(True)
        self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.StyledPanel)
        self._icons = QWidget(self.viewport().parentWidget())
        self._icons.setAttribute(Qt.WA_TranslucentBackground)
        self._icon_row = QHBoxLayout(self._icons)
        self._icon_row.setContentsMargins(0, 0, 0, 0)
        self._icon_row.setSpacing(2)
        self.use_btn = self.add_icon(None, "Use the suggested comment (Tab)", self.use_suggestion, text="↵")
        self.use_btn.setVisible(False)
        self._completer: QCompleter | None = None
        self.setPlainText(text or "")
        self.textChanged.connect(self._changed)
        self.document().documentLayout().documentSizeChanged.connect(lambda _s: self._fit())
        self._fit()

    # the QLineEdit-like part the panel uses ---------------------------------------------------------
    def text(self) -> str:
        return self.toPlainText()

    def setText(self, t: str):
        self.setPlainText(t or "")
        self.moveCursor(QTextCursor.End)

    def setCursorPosition(self, _pos: int):
        self.moveCursor(QTextCursor.End)

    # icons inside the box, at the right -----------------------------------------------------------
    def add_icon(self, icon: QIcon | None, tip: str, slot, text: str = "") -> QToolButton:
        b = QToolButton(self._icons)
        if icon is not None:
            b.setIcon(icon)
        else:
            b.setText(text)
        b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        b.setAutoRaise(True)
        b.setFixedSize(QSize(22, 20))
        b.setStyleSheet("QToolButton { border: none; color: #2563eb; font-weight: 600; }"
                        "QToolButton:hover { background: #e8eefc; border-radius: 4px; }")
        b.clicked.connect(slot)
        self._icon_row.addWidget(b)
        self._place_icons()
        return b

    def _place_icons(self):
        n = sum(1 for i in range(self._icon_row.count()) if self._icon_row.itemAt(i).widget().isVisibleTo(self))
        w = n * 24
        self.setViewportMargins(0, 0, w, 0)
        self._icons.setGeometry(self.width() - w - 4, 3, w, 20)
        self._icons.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place_icons()
        self._fit()

    def showEvent(self, e):
        super().showEvent(e)
        self._place_icons()

    # the suggestion ---------------------------------------------------------------------------------
    def set_suggestion(self, text: str, show: bool):
        """Offer `text` in grey while the box is empty and `show` is true."""
        self.suggestion = (text or "").strip()
        self._shown = bool(show and self.suggestion)
        self.setPlaceholderText(self.suggestion if self._shown else self._default_placeholder)
        self.setToolTip(f"Suggested comment (Tab to use it):\n{self.suggestion}" if self._shown else "")
        self.use_btn.setVisible(self._shown and not self.toPlainText().strip())
        self._place_icons()
        self._fit()

    @property
    def suggestion_shown(self) -> bool:
        return self._shown and not self.toPlainText().strip()

    def use_suggestion(self):
        if self.suggestion:
            self.setText(self.suggestion)
            self.setFocus()

    def event(self, e):
        # Tab normally moves the focus before the box sees the key: with a suggestion showing, it takes it
        if e.type() == QEvent.KeyPress and e.key() == Qt.Key_Tab and not e.modifiers() and self.suggestion_shown:
            self.use_suggestion()
            return True
        return super().event(e)

    def keyPressEvent(self, e):
        if self._completer is not None and self._completer.popup().isVisible() \
                and e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape, Qt.Key_Up, Qt.Key_Down):
            e.ignore()
            return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not e.modifiers():
            self.focusNextChild()            # one comment is one paragraph: Enter moves on, as in a line box
            return
        super().keyPressEvent(e)

    # earlier comments offered while typing ----------------------------------------------------------
    def setCompleter(self, comp: QCompleter):
        if self._completer is not None:
            self._completer.activated.disconnect()
        self._completer = comp
        comp.setWidget(self)
        comp.setCompletionMode(QCompleter.PopupCompletion)
        comp.activated.connect(self.setText)

    def _changed(self):
        t = self.toPlainText()
        self.use_btn.setVisible(self._shown and not t.strip())
        self._place_icons()
        self._fit()
        c = self._completer
        if c is not None and self.hasFocus():
            if len(t.strip()) >= 3:
                c.setCompletionPrefix(t.strip())
                if c.completionCount() and c.currentCompletion() != t:
                    r = self.cursorRect()
                    r.setWidth(min(self.width(), 520))
                    c.complete(r)
                else:
                    c.popup().hide()
            else:
                c.popup().hide()
        self.edited.emit(t)

    # height: one line to a few, as the text needs ---------------------------------------------------
    def _fit(self):
        fm = self.fontMetrics()
        line = fm.lineSpacing()
        if self.toPlainText():
            # the box's own layout counts the wrapped lines of real text
            lines = int(self.document().documentLayout().documentSize().height() + 0.5)
        else:
            width = max(50, self.viewport().width() - 10)
            lines = 0
            for para in (self.placeholderText() or " ").split("\n"):
                lines += max(1, -(-int(fm.horizontalAdvance(para) * 1.08) // width))
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded if lines > MAX_LINES else Qt.ScrollBarAlwaysOff)
        lines = max(1, min(MAX_LINES, lines))
        h = lines * line + 2 * int(self.document().documentMargin()) + 6
        if self.height() != h:
            self.setFixedHeight(h)

    def sizeHint(self):
        return QSize(300, self.height())
