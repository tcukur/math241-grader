"""Dialogs for TA packages (instructor side) and return files (TA side)."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QCheckBox, QDateEdit, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QRadioButton,
                               QSpinBox, QVBoxLayout, QWidget)

from ..keyshare import seal
from ..sync import create_package, import_package, new_workspace_from_package, read_manifest
from .state import AppState, get_api_key, output_dir, save_access_file, show_in_folder, workspace_access_path


class TaPackageDialog(QDialog):
    """Instructor chooses which students go to which TA."""

    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Create a TA package")
        self.resize(620, 820)
        lay = QVBoxLayout(self)
        intro = QLabel("Tick the students this TA will grade. The package contains their PDFs, the AI pre-screen "
                       "results, the assignment and the grading worksheet, and, if you allow it below, sealed AI "
                       "access so the TA can re-run papers. Students already given to a TA show that TA's name.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        row = QHBoxLayout()
        row.addWidget(QLabel("TA name"))
        self.ta = QLineEdit()
        self.ta.setPlaceholderText("Used in the file name and to track who grades whom")
        row.addWidget(self.ta, 1)
        lay.addLayout(row)
        sel = QHBoxLayout()
        for text, fn in (("All", lambda: self._set_all(True)), ("None", lambda: self._set_all(False)),
                         ("Unassigned only", self._unassigned)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            sel.addWidget(b)
        sel.addStretch(1)
        lay.addLayout(sel)
        self.list = QListWidget()
        lay.addWidget(self.list, 1)
        for r in state.store.submissions():
            info = json.loads(r["info"] or "{}")
            who = info.get("assigned_ta", "")
            st = "pre-screened" if r["status"] == "screened" else r["status"]
            it = QListWidgetItem(f"{r['name'] or r['sub_id']}  ({r['sub_id']})  ·  {st}"
                                 + (f"  ·  given to {who}" if who else ""))
            it.setData(Qt.UserRole, r["sub_id"])
            it.setData(Qt.UserRole + 1, who)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self.list.addItem(it)
        self.count = QLabel("")
        lay.addWidget(self.count)

        # AI access ---------------------------------------------------------
        box = QFrame()
        box.setObjectName("card")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(12, 10, 12, 10)
        self.ai_on = QCheckBox("Let this TA re-run papers with the AI")
        self.ai_on.setChecked(True)
        bl.addWidget(self.ai_on)
        self.ai_opts = QWidget()
        ol = QFormLayout(self.ai_opts)
        ol.setContentsMargins(22, 4, 0, 0)
        kr = QHBoxLayout()
        self.key_mine = QRadioButton("My saved key")
        self.key_sep = QRadioButton("A separate key for this TA (recommended)")
        self.key_mine.setChecked(True)
        kr.addWidget(self.key_mine)
        kr.addWidget(self.key_sep)
        kr.addStretch(1)
        ol.addRow("Key", kr)
        self.sep_key = QLineEdit()
        self.sep_key.setEchoMode(QLineEdit.Password)
        self.sep_key.setPlaceholderText("sk-...  (a key you created for this TA)")
        self.sep_key.setEnabled(False)
        self.key_sep.toggled.connect(self.sep_key.setEnabled)
        ol.addRow("", self.sep_key)
        self.max_runs = QSpinBox()
        self.max_runs.setRange(0, 1000)
        self.max_runs.setValue(30)
        self.max_runs.setSpecialValueText("No limit")
        ol.addRow("Re-runs allowed", self.max_runs)
        self.expires = QDateEdit(QDate.currentDate().addDays(30))
        self.expires.setCalendarPopup(True)
        ol.addRow("Valid until", self.expires)
        mc = state.pack.model if state.pack else {}
        self.allow_strong = QCheckBox(f"Allow the stronger model ({mc.get('escalation_name', 'none')})")
        self.allow_strong.setEnabled(bool(mc.get("escalation_name")))
        ol.addRow("", self.allow_strong)
        bl.addWidget(self.ai_opts)
        note = QLabel("The key is sealed inside the package and never shown in the app. It is hidden, not "
                      "unbreakable, so also set a spending limit for the key on the OpenAI side.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        bl.addWidget(note)
        self.ai_on.toggled.connect(self.ai_opts.setEnabled)
        lay.addWidget(box)
        self.list.itemChanged.connect(self._update_count)
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        ok = QPushButton("Save package…")
        ok.setObjectName("primary")
        ok.clicked.connect(self.save)
        btns.addWidget(ok)
        lay.addLayout(btns)
        self._update_count()

    def _items(self):
        return [self.list.item(i) for i in range(self.list.count())]

    def _set_all(self, on):
        for it in self._items():
            it.setCheckState(Qt.Checked if on else Qt.Unchecked)

    def _unassigned(self):
        for it in self._items():
            it.setCheckState(Qt.Unchecked if it.data(Qt.UserRole + 1) else Qt.Checked)

    def _update_count(self, *_):
        n = sum(1 for it in self._items() if it.checkState() == Qt.Checked)
        self.count.setText(f"{n} students selected")

    def save(self):
        ids = [it.data(Qt.UserRole) for it in self._items() if it.checkState() == Qt.Checked]
        ta = self.ta.text().strip()
        if not ids:
            QMessageBox.information(self, "No students", "Tick at least one student.")
            return
        if not ta:
            QMessageBox.information(self, "TA name", "Enter the TA's name.")
            return
        st = self.state
        unscreened = [i for i in ids if st.store.submission(i)["status"] != "screened"]
        if unscreened and QMessageBox.question(
                self, "Not pre-screened yet",
                f"{len(unscreened)} of the selected students have no pre-screen yet. Include them anyway?"
        ) != QMessageBox.Yes:
            return
        safe = re.sub(r"[^\w\-]+", "_", ta)
        tag = (st.pack.data.get("short_name") or st.pack.id) if st.pack else "grading"
        path = output_dir("packages") / f"{tag}_TA_package_{safe}_{date.today().isoformat()}.zip"
        access = None
        if self.ai_on.isChecked():
            key = self.sep_key.text().strip() if self.key_sep.isChecked() else get_api_key()
            if not key:
                QMessageBox.information(self, "No key", "Enter the TA's key, or save your own key on the Setup "
                                                        "tab first.")
                return
            mc = st.pack.model
            models = [mc.get("name")] + ([mc["escalation_name"]] if self.allow_strong.isChecked()
                                          and mc.get("escalation_name") else [])
            access = {"key": seal(key), "max_reruns": self.max_runs.value(),
                      "expires": self.expires.date().toString("yyyy-MM-dd"), "models": models,
                      "separate_key": self.key_sep.isChecked()}
        ws = st.meta("worksheet_path")
        res = create_package(st.store, st.workspace, Path(st.meta("pack_path")), ids, Path(path), "to_ta",
                             sender=st.meta("reviewer", "") or "Instructor", worksheet=Path(ws) if ws else None,
                             ai_access=access)
        for sid in ids:
            info = json.loads(st.store.submission(sid)["info"] or "{}")
            info["assigned_ta"] = ta
            st.store.set_info(sid, info)
        saved_box(self, "Package saved",
                  f"Package for {ta} with {res['students']} students, saved in this workspace's "
                  f"packages folder:\n{Path(res['path']).name}\n\n"
                  + ("The TA can run the AI with the sealed key. "
                     if access else "The TA has no AI access and will send re-run requests. ")
                  + "Send this file to the TA.", Path(res["path"]))
        self.accept()


def saved_box(parent, title: str, text: str, path: Path) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    show = box.addButton("Show in folder", QMessageBox.ActionRole)
    box.addButton(QMessageBox.Ok)
    box.exec()
    if box.clickedButton() is show:
        show_in_folder(path)


def create_return_file(state: AppState, parent) -> None:
    st = state
    ids = [r["sub_id"] for r in st.store.submissions()]
    name = re.sub(r"[^\w\-]+", "_", st.meta("reviewer", "") or "TA")
    tag = (st.pack.data.get("short_name") or st.pack.id) if st.pack else "grading"
    path = output_dir("packages") / f"{tag}_return_{name}_{date.today().isoformat()}.zip"
    res = create_package(st.store, st.workspace, None, ids, Path(path), "to_instructor",
                         sender=st.meta("reviewer", "") or "TA")
    c = st.store.counts()
    saved_box(parent, "Return file saved",
              f"Saved in this workspace's packages folder:\n{Path(res['path']).name}\n\nIt holds your grading "
              f"for {res['reviews']} students and {c.get('rerun_requests', 0)} re-run requests. "
              "Send it to the instructor.", Path(res["path"]))


def import_into_current(state: AppState, parent) -> None:
    st = state
    title = "Import an update from the instructor" if st.is_ta else "Import a TA's return file"
    path, _ = QFileDialog.getOpenFileName(parent, title, str(output_dir("packages")), "Grader package (*.zip)")
    if not path:
        return
    try:
        st.flush()
        st.backup("before-import")
        res = import_package(st.store, st.workspace, Path(path), "ta" if st.is_ta else "instructor")
    except Exception as e:  # noqa: BLE001
        QMessageBox.warning(parent, "Could not import", str(e))
        return
    if st.pack is not None:
        # newer AI results from the instructor: keep the TA's grading, flag those students for a re-check
        from ..pipeline import merge_new_screen
        for r in st.store.submissions():
            try:
                merge_new_screen(st.store, st.pack, r["sub_id"])
            except Exception:  # noqa: BLE001
                pass
    if res["kind"] == "to_ta":
        st.reload_pack()
        msg = (f"Update imported: {res['students']} students, {res['screens_updated']} with new AI results. "
               "Your grading was kept.")
    else:
        msg = (f"Return file from {res['sender'] or 'a TA'} imported: grading updated for "
               f"{res['reviews_updated']} students, {res['requests']} re-run requests waiting. "
               "Process the requests on the Pre-screen tab with Start, then send that TA an updated package.")
    st.submissions_changed.emit()
    st.reviews_changed.emit()
    QMessageBox.information(parent, "Imported", msg)


def open_ta_package(state: AppState, parent) -> bool:
    path, _ = QFileDialog.getOpenFileName(parent, "Open the package from the instructor", str(Path.home()),
                                          "Grader package (*.zip)")
    if not path:
        return False
    try:
        m = read_manifest(Path(path))
    except Exception as e:  # noqa: BLE001
        QMessageBox.warning(parent, "Not a package", str(e))
        return False
    if m["kind"] != "to_ta":
        QMessageBox.warning(parent, "Wrong file", "This is a TA return file. Import it into the instructor's "
                                                  "workspace instead.")
        return False
    folder = QFileDialog.getExistingDirectory(parent, "Choose an empty folder for this grading workspace")
    if not folder:
        return False
    try:
        new_workspace_from_package(Path(path), Path(folder))
        state.open_workspace(folder, create=True)
        state.store.set_meta("mode", "ta")
        import_package(state.store, Path(folder), Path(path), "ta")
        state.reload_pack()
    except Exception as e:  # noqa: BLE001
        QMessageBox.warning(parent, "Could not open the package", str(e))
        return False
    state.workspace_changed.emit()
    state.submissions_changed.emit()
    QMessageBox.information(parent, "Ready", f"Workspace ready with {len(m['submissions'])} students. "
                                             "Enter your name on this tab, then go to Review and grade.")
    return True


class AccessFileDialog(QDialog):
    """Instructor creates a one-time access file for a TA."""

    def __init__(self, parent, state: AppState):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Create a TA access file")
        self.resize(560, 360)
        lay = QVBoxLayout(self)
        intro = QLabel("The access file is saved inside this workspace folder. Whoever you give the folder to can "
                       "run the pre-screen and re-runs, and it carries over to new workspaces they make. The key is "
                       "sealed inside the file and never shown, though it is hidden rather than unbreakable, so keep "
                       "a spending limit on the key at OpenAI.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        form = QFormLayout()
        self.label = QLineEdit()
        self.label.setPlaceholderText("TA name, for your own records")
        form.addRow("TA", self.label)
        kr = QHBoxLayout()
        self.key_mine = QRadioButton("My saved key")
        self.key_sep = QRadioButton("A separate key for this TA (recommended)")
        self.key_mine.setChecked(True)
        kr.addWidget(self.key_mine)
        kr.addWidget(self.key_sep)
        kr.addStretch(1)
        form.addRow("Key", kr)
        self.sep_key = QLineEdit()
        self.sep_key.setEchoMode(QLineEdit.Password)
        self.sep_key.setPlaceholderText("sk-...  (a key you created for this TA)")
        self.sep_key.setEnabled(False)
        self.key_sep.toggled.connect(self.sep_key.setEnabled)
        form.addRow("", self.sep_key)
        er = QHBoxLayout()
        self.has_exp = QCheckBox("Expires on")
        self.has_exp.setChecked(True)
        self.expires = QDateEdit(QDate.currentDate().addMonths(5))
        self.expires.setCalendarPopup(True)
        self.has_exp.toggled.connect(self.expires.setEnabled)
        er.addWidget(self.has_exp)
        er.addWidget(self.expires)
        er.addStretch(1)
        form.addRow("Validity", er)
        self.allow_strong = QCheckBox("Allow the stronger model for single-paper re-runs")
        form.addRow("", self.allow_strong)
        lay.addLayout(form)
        lay.addStretch(1)
        b = QHBoxLayout()
        b.addStretch(1)
        c = QPushButton("Cancel")
        c.clicked.connect(self.reject)
        b.addWidget(c)
        ok = QPushButton("Save access file")
        ok.setObjectName("primary")
        ok.clicked.connect(self.save)
        b.addWidget(ok)
        lay.addLayout(b)

    def save(self):
        key = self.sep_key.text().strip() if self.key_sep.isChecked() else get_api_key()
        if not key:
            QMessageBox.information(self, "No key", "Enter the TA's key, or save your own key first.")
            return
        label = self.label.text().strip() or "TA"
        data = {"format": "math241grader-access", "version": 1, "label": label,
                "created": date.today().isoformat(),
                "expires": self.expires.date().toString("yyyy-MM-dd") if self.has_exp.isChecked() else "",
                "allow_strong": self.allow_strong.isChecked(), "models": [],
                "separate_key": self.key_sep.isChecked(), "key": seal(key)}
        wp = workspace_access_path()
        if wp and wp.exists() and QMessageBox.question(
                self, "Replace?", "This workspace already has an access file. Replace it?") != QMessageBox.Yes:
            return
        try:
            path = save_access_file(data)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Could not save", str(e))
            return
        saved_box(self, "Saved", f"The access file is saved inside this workspace as {path.name}.\n\n"
                  f"When you give this workspace folder to {label}, their copy of the app can run the AI "
                  + (f"until {data['expires']}" if data["expires"] else "with no end date")
                  + ". Your own key is never shown to them.", path)
        self.accept()
