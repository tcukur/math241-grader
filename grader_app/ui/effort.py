"""Reasoning effort: how long the AI thinks before answering. More effort is usually more careful on proofs and
code, and slower and more expensive, because the thinking is billed as output."""
from __future__ import annotations

from PySide6.QtWidgets import QComboBox

LEVELS = [("low", "Low"), ("medium", "Medium"), ("high", "High")]
TIP = ("How long the AI thinks before answering. Higher is usually more careful on proofs and code, but slower and "
       "more expensive, because the thinking is billed. Medium is the default.")


def effort_box(default: str | None) -> QComboBox:
    box = QComboBox()
    box.setToolTip(TIP)
    for key, label in LEVELS:
        box.addItem(label + (" (default)" if key == (default or "medium") else ""), key)
    box.setCurrentIndex(max(0, box.findData(default or "medium")))
    return box
