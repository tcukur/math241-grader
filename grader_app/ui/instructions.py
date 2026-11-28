"""AI instructions: what the AI is told for every student, editable by the instructor.

The instructions are kept in the workspace, so a workspace handed to a TA carries them, read-only there. A short
fixed part is always added by the app and cannot be removed. Saving a change is a new version of the class-wide
prompt; the Pre-screen tab then offers to re-screen the students done with the earlier version."""
from __future__ import annotations

import json
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QTabWidget,
                               QVBoxLayout, QWidget)

from .. import llm
from .state import AppState, key_source
from .theme import WrapLabel


def can_edit(state: AppState) -> tuple[bool, str]:
    """Only the instructor edits: not in a TA workspace, and only with an API key entered on this computer."""
    if state.is_ta:
        return False, "Set by the instructor. In a TA workspace the instructions can be read but not changed."
    try:
        if key_source() != "own":
            return False, ("Read only. The instructions can be changed on the computer where the OpenAI API key "
                           "was entered on the Setup tab.")
    except Exception:  # noqa: BLE001
        return False, "Read only."
    return True, ""


def record_prompt_change(state: AppState) -> None:
    """Remember when this version of the class-wide prompt was set, for the labels shown with results."""
    from ..pipeline import current_prompt_version
    hist = state.meta("prompt_history", {}) or {}
    v = current_prompt_version(state.store)
    hist.setdefault(v, time.time())
    state.set_meta("prompt_history", hist)


def version_label(state: AppState, version: str | None) -> str:
    """'default', or 'edited 23 Oct, 10:15' for the version of the class-wide prompt that was set then."""
    if not version or version == "default":
        return "default"
    hist = state.meta("prompt_history", {}) or {}
    if version in hist:
        from ..dates import stamp
        return f"edited {stamp(hist[version], year=False)}"
    return f"version {version}"


class InstructionsDialog(QDialog):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.saved = False
        self.setWindowTitle("AI instructions")
        self.resize(1000, 780)
        editable, why = can_edit(state)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs, 1)

        # the instructions ------------------------------------------------------------------------
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(WrapLabel(
            "These instructions are sent to the AI for every student, before the assignment documents and the "
            "student's work. Change anything you like. Changes apply to the next students pre-screened, and saving "
            "offers to re-screen the students already done. Restore default brings back the original.", "muted"))
        if not editable:
            note = WrapLabel(f"<b>{why}</b>")
            note.setTextFormat(Qt.RichText)
            v.addWidget(note)
        current = state.meta("ai_instructions", "") or ""
        self.edit = QPlainTextEdit(current.strip() or llm.DEFAULT_INSTRUCTIONS)
        self.edit.setReadOnly(not editable)
        v.addWidget(self.edit, 3)
        h = QLabel("Always added by the app (cannot be changed)")
        h.setObjectName("h2")
        v.addWidget(h)
        v.addWidget(WrapLabel("These keep the app's safeguards working: names removed before the AI sees the work, "
                              "instructions hidden in a submission ignored, and answers in the format the app reads.",
                              "muted"))
        fixed = QPlainTextEdit(llm.PROTECTED)
        fixed.setReadOnly(True)
        fixed.setMaximumHeight(150)
        v.addWidget(fixed, 1)
        tabs.addTab(page, "Instructions")

        # the full prompt for one student ---------------------------------------------------------
        prev = QWidget()
        pv = QVBoxLayout(prev)
        pv.addWidget(WrapLabel("Everything sent for one student, with the instructions as they stand in the first "
                               "tab, so you can check the whole prompt before spending anything. Page images are "
                               "shown as placeholders.", "muted"))
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        pv.addWidget(self.preview, 1)
        tabs.addTab(prev, "Full prompt for one student")
        tabs.currentChanged.connect(lambda i: i == 1 and self._fill_preview())

        row = QHBoxLayout()
        self.restore_btn = QPushButton("Restore default")
        self.restore_btn.clicked.connect(lambda: self.edit.setPlainText(llm.DEFAULT_INSTRUCTIONS))
        self.restore_btn.setEnabled(editable)
        row.addWidget(self.restore_btn)
        row.addStretch(1)
        close = QPushButton("Cancel" if editable else "Close")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        if editable:
            save = QPushButton("Save")
            save.setObjectName("primary")
            save.clicked.connect(self.save)
            row.addWidget(save)
        lay.addLayout(row)

    def _fill_preview(self):
        st = self.state
        from ..pipeline import load_stage
        row = next((r for r in st.store.submissions() if r["extraction"]), None) if st.store else None
        if row is None:
            self.preview.setPlainText("No student has been read yet. Import the submissions and run the automatic "
                                      "checks or the pre-screen first.")
            return
        ext, checks = load_stage(row)
        inp, _ = llm.build_input(st.pack, ext, checks or [], row["pdf_path"], st.meta("global_note", "") or "",
                                 row["ta_note"] or "", with_images=False)
        text = self.edit.toPlainText()
        custom = "" if text.strip() == llm.DEFAULT_INSTRUCTIONS.strip() else text
        self.preview.setPlainText(f"(Sample student: {row['name'] or row['sub_id']})\n\n"
                                  + llm.prompt_as_text(inp, custom))

    def save(self):
        text = self.edit.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "Empty", "The instructions cannot be empty. Use Restore default instead.")
            return
        custom = "" if text == llm.DEFAULT_INSTRUCTIONS.strip() else text
        if custom == (self.state.meta("ai_instructions", "") or "").strip():
            self.accept()                       # nothing changed
            return
        self.state.backup("before-instructions")
        self.state.set_meta("ai_instructions", custom)
        record_prompt_change(self.state)
        from ..applog import log as glog
        from ..pipeline import current_prompt_version
        glog.info("AI instructions changed (%s, prompt version %s)", "edited" if custom else "back to the default",
                  current_prompt_version(self.state.store))
        self.saved = True
        self.accept()
