"""Keyboard grading for the Review tab.

There is one current item (a rubric item or an integrity finding), shown with a blue outline. Keys act on that
item, whatever has the keyboard focus, and the panel scrolls to keep it in view. Plain keys never act while
the grader is typing in a text box (a comment, the PDF page number), so typing is never turned into grades.

    1-5          level of the current rubric item (100, 75, 50, 25, 0 %), then move on
    F H N R      decision on the current finding: full, half, no penalty, rejected
    C            type a comment for the current item
    Esc          stop typing, keys work again
    Alt+Down/Up  next / previous item          (Option on a Mac)
    Alt+Right/Left  next / previous student
    Ctrl+Enter   mark reviewed and next        (Cmd on a Mac)
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QComboBox, QLineEdit, QPlainTextEdit, QTextEdit)

MAC = sys.platform == "darwin"
DECISION_KEYS = {Qt.Key_F: "full", Qt.Key_H: "half", Qt.Key_N: "none", Qt.Key_R: "rejected"}
LEVEL_KEYS = {Qt.Key_1: 0, Qt.Key_2: 1, Qt.Key_3: 2, Qt.Key_4: 3, Qt.Key_5: 4}


def hint_text() -> str:
    alt, cmd = ("⌥", "⌘") if MAC else ("Alt+", "Ctrl+")
    return (f"Keys: 1–5 level · F H N R finding decision · C comment · Esc stop typing · "
            f"{alt}↓ ↑ item · {alt}→ ← student · {cmd}Enter mark reviewed")


def _typing(w) -> bool:
    if w is None:
        return False
    if isinstance(w, (QLineEdit, QPlainTextEdit, QTextEdit, QAbstractSpinBox)):
        return not getattr(w, "isReadOnly", lambda: False)()
    if isinstance(w, QComboBox):
        return w.isEditable() or w.view().isVisible()
    return False


class KeyGrader(QObject):
    """Installed on the application; acts only while the Review tab is on screen and its window is active."""

    def __init__(self, tab):
        super().__init__(tab)
        self.tab = tab
        self.items: list = []
        self.index = -1
        QApplication.instance().installEventFilter(self)

    # current item ------------------------------------------------------------------------------
    def set_items(self, items: list):
        self.items = list(items)
        self.index = -1
        # start at the first item that still needs a decision
        first = next((i for i, c in enumerate(self.items) if self._open(c)), 0 if self.items else -1)
        self.select(first, scroll=False)

    def _open(self, card) -> bool:
        if hasattr(card, "level"):
            return card.level() is None
        return getattr(card, "f", {}).get("decision", "pending") == "pending"

    def select(self, i: int, scroll: bool = True):
        if not self.items:
            self.index = -1
            return
        i = max(0, min(len(self.items) - 1, i))
        for k, c in enumerate(self.items):
            want = k == i
            if bool(c.property("current")) != want:
                c.setProperty("current", want)
                c.style().unpolish(c)
                c.style().polish(c)
        self.index = i
        if scroll:
            self._scroll_to(self.items[i])

    def select_card(self, card):
        if card in self.items:
            self.select(self.items.index(card), scroll=False)

    def _scroll_to(self, card):
        area = self.tab.panel_scroll
        bar = area.verticalScrollBar()
        top, h = card.y(), card.height()
        view_top, view_h = bar.value(), area.viewport().height()
        if top < view_top or top + min(h, view_h) > view_top + view_h:
            bar.setValue(max(0, top - 12))

    def current(self):
        return self.items[self.index] if 0 <= self.index < len(self.items) else None

    # keys ----------------------------------------------------------------------------------------
    def eventFilter(self, obj, ev):
        if ev.type() != QEvent.KeyPress:
            return False
        tab = self.tab
        try:
            if not tab.isVisible() or not tab.window().isActiveWindow() or not tab.review:
                return False
        except RuntimeError:
            return False
        fw = QApplication.focusWidget()
        # handle each key press once, where it is delivered (not again as it travels up to parent widgets)
        if obj is not (fw or tab.window()):
            return False
        try:
            return self._key(ev, fw)
        except Exception:  # noqa: BLE001
            return False       # a keyboard shortcut must never break the app

    def _key(self, ev, fw) -> bool:
        key, mods = ev.key(), ev.modifiers()
        ctrl = bool(mods & Qt.ControlModifier)          # Cmd on a Mac
        alt = bool(mods & Qt.AltModifier)               # Option on a Mac
        typing = _typing(fw)
        if ctrl and key in (Qt.Key_Return, Qt.Key_Enter):
            self.tab.mark_reviewed()
            return True
        if typing:
            if key == Qt.Key_Escape:
                fw.clearFocus()
                self.tab.panel_scroll.setFocus()
                return True
            return False                                # typing goes to the text box, untouched
        if alt and not ctrl:
            if key == Qt.Key_Down:
                self.select(self.index + 1)
                return True
            if key == Qt.Key_Up:
                self.select(self.index - 1)
                return True
            if key == Qt.Key_Right:
                self.tab._step(1)
                return True
            if key == Qt.Key_Left:
                self.tab._step(-1)
                return True
            return False
        if ctrl or alt or (mods & Qt.MetaModifier):
            return False
        card = self.current()
        if card is None:
            return False
        if key in LEVEL_KEYS and hasattr(card, "group"):
            levels = [b for b in card.group.buttons()]
            n = LEVEL_KEYS[key]
            if n < len(levels):
                levels[n].click()
                self.select(self.index + 1)
            return True
        if key in DECISION_KEYS and hasattr(card, "decision"):
            combo = card.decision
            j = combo.findData(DECISION_KEYS[key])
            if j >= 0:
                combo.setCurrentIndex(j)
                if DECISION_KEYS[key] in ("half", "none"):
                    card.comment.setFocus()             # a reduced penalty needs a comment for the student
                else:
                    self.select(self.index + 1)
            return True
        if key == Qt.Key_C and hasattr(card, "comment"):
            self._scroll_to(card)
            card.comment.setFocus()
            return True
        return False
