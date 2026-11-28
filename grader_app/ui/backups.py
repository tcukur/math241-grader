"""Backups window: see the automatic copies of the grading, make one now, or restore one."""
from __future__ import annotations

import datetime as _dt

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..applog import log as glog
from ..dates import day_month
from ..backup import backup_dir, list_backups, restore_backup
from .state import AppState
from .theme import WrapLabel


def _when(b) -> str:
    w = b["when"]
    today = _dt.date.today()
    day = "Today" if w.date() == today else "Yesterday" if w.date() == today - _dt.timedelta(days=1) \
        else day_month(w)
    return f"{day}, {w.hour:02d}:{w.minute:02d}"


class BackupDialog(QDialog):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Backups")
        self.resize(720, 480)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        intro = WrapLabel(
            "The grading is copied automatically when the workspace is opened each day, every 15 minutes while "
            "you work if something changed, when the app is closed, and before the assignment, the penalties or "
            "an imported package change anything. The newest 30 copies are kept in the workspace's backups "
            "folder. Restoring first backs up the current state, so a restore can be undone.", "muted")
        lay.addWidget(intro)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Made", "Why", "Grading in this copy"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._selected)
        lay.addWidget(self.table, 1)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        lay.addWidget(self.status)
        row = QHBoxLayout()
        now = QPushButton("Back up now")
        now.clicked.connect(self.backup_now)
        folder = QPushButton("Open backups folder")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(backup_dir(self.state.workspace)))))
        row.addWidget(now)
        row.addWidget(folder)
        row.addStretch(1)
        self.restore_btn = QPushButton("Restore selected")
        self.restore_btn.setObjectName("primary")
        self.restore_btn.setEnabled(False)
        self.restore_btn.clicked.connect(self.restore)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(self.restore_btn)
        row.addWidget(close)
        lay.addLayout(row)
        self.fill()

    def fill(self):
        self.items = list_backups(self.state.workspace) if self.state.workspace else []
        self.table.setRowCount(len(self.items))
        for i, b in enumerate(self.items):
            what = (f"{b['reviewed']} of {b['students']} reviewed" if b.get("students") is not None
                    else "could not be read")
            for j, v in enumerate((_when(b), b["label"].capitalize(), what)):
                it = QTableWidgetItem(v)
                if j == 2:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(i, j, it)
        self.status.setText(f"{len(self.items)} backups." if self.items else
                            "No backups yet. The first is made when the workspace has students.")

    def _selected(self):
        self.restore_btn.setEnabled(bool(self.table.selectionModel().selectedRows()))

    def backup_now(self):
        self.state.flush()
        p = self.state.backup("manual")
        self.fill()
        self.status.setText("Backup made." if p else "Could not make a backup (see the log file).")

    def restore(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        b = self.items[rows[0].row()]
        cur = self.state.store.counts() if self.state.store else {}
        if QMessageBox.question(
                self, "Restore this backup?",
                f"Replace the current grading ({cur.get('reviewed', 0)} of {cur.get('total', 0)} reviewed) with the "
                f"copy from {_when(b).lower()} ({b.get('reviewed')} of {b.get('students')} reviewed)?\n\n"
                "The current grading is backed up first, so you can come back to it from this list.") \
                != QMessageBox.Yes:
            return
        self.state.flush()          # pending edits are saved, so the pre-restore backup includes them
        self.state.discard()        # and the screen must not write its old copy back over the restored grading
        try:
            before = restore_backup(self.state.workspace / "grading.db", b["path"])
            glog.info("Backup restored: %s (the state before it was saved as %s)", b["path"].name,
                      before.name if before else "nothing")
        except Exception as e:  # noqa: BLE001
            glog.exception("Restore failed: %s", e)
            QMessageBox.warning(self, "Could not restore", str(e))
            return
        self.state.open_workspace(self.state.workspace)      # reload everything from the restored grading
        self.fill()
        self.status.setText(f"Restored the copy from {_when(b).lower()}. The state before the restore is at the "
                            "top of the list.")
