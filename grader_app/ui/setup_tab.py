"""Setup: workspace, assignment pack, submissions, worksheet, API key."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThread, Signal
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QVBoxLayout, QWidget)

from ..applog import log as glog
from ..pipeline import register_submissions
from ..workspace import (copy_workspace, find_workspaces, import_classlist, is_cloud_folder,
                         local_workspaces_dir)
from .new_pack import NewPackDialog
from .penalties import PenaltyDialog
from .packages import AccessFileDialog, TaPackageDialog, create_return_file, import_into_current, open_ta_package
from .theme import WrapLabel
from .widgets import flow
from .state import (AppState, access_valid, get_api_key, key_source, load_access_file, own_api_key,
                    workspace_access_path,
                    remove_access_file, remove_api_key, set_api_key)


class PathRow(QWidget):
    """A read-only path display with one or more browse buttons."""

    def __init__(self, placeholder: str, buttons: list[tuple[str, callable]]):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setReadOnly(True)
        self.edit.setPlaceholderText(placeholder)
        lay.addWidget(self.edit, 1)
        self.buttons = {}
        for text, cb in buttons:
            b = QPushButton(text)
            b.clicked.connect(cb)
            lay.addWidget(b)
            self.buttons[text] = b

    def set(self, path: str | None):
        self.edit.setText(path or "")
        self.edit.setToolTip(path or "")


class TestKeyThread(QThread):
    done = Signal(bool, str)

    def __init__(self, key, model):
        super().__init__()
        self.key, self.model = key, model

    def run(self):
        try:
            from openai import OpenAI
            c = OpenAI(api_key=self.key, timeout=30, max_retries=0)
            ok, missing = [], []
            for m in self.model:
                try:
                    c.models.retrieve(m)
                    ok.append(m)
                except Exception as e:  # noqa: BLE001
                    if "401" in str(e) or "api key" in str(e).lower():
                        raise
                    missing.append(m)
            msg = "Connected. Available: " + (", ".join(ok) or "none")
            if missing:
                msg += ". Not available to this key: " + ", ".join(missing)
            self.done.emit(bool(ok), msg + ".")
        except Exception as e:  # noqa: BLE001
            self.done.emit(False, f"{type(e).__name__}: {e}")


class SetupTab(QWidget):
    go_next = Signal()

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.pending = {"pack": None, "classlist": None}     # chosen, copied in by Import all documents
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(14)

        title = QLabel("Set up a grading session")
        title.setObjectName("h1")
        lay.addWidget(title)
        intro = QLabel("Open a workspace, or make a new one for a new assignment. Everything is saved in that one "
                       "folder as you go: the grading, and copies of the student PDFs, the assignment and the class "
                       "list. You can move, rename or copy the folder, and open it on another computer.")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        card = QFrame()
        card.setObjectName("card")
        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.ws_row = PathRow("Folder where this grading session is saved",
                              [("Open…", self.choose_workspace), ("New…", self.new_workspace),
                               ("Backups…", self.open_backups)])
        self.recent = QComboBox()
        self.recent.setMinimumWidth(160)
        self.recent.activated.connect(self.open_recent)
        self.ws_row.layout().addWidget(self.recent)
        form.addRow("Workspace", self.ws_row)
        self.reviewer = QLineEdit()
        self.reviewer.setPlaceholderText("Your name, shown on the feedback page")
        self.reviewer.editingFinished.connect(lambda: self.state.set_meta("reviewer", self.reviewer.text().strip()))
        form.addRow("Grader name", self.reviewer)
        lay.addWidget(card)

        # instructor-only settings, hidden in TA workspaces
        card2 = QFrame()
        card2.setObjectName("card")
        self.instr_card = card2
        form = QFormLayout(card2)
        form.setContentsMargins(18, 16, 18, 16)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.pack_row = PathRow("Assignment (folder with the handout, instructor guide and rubric)",
                                [("Choose…", self.choose_pack), ("New from documents…", self.new_pack),
                                 ("Points and penalties…", self.edit_penalties)])
        form.addRow("Assignment", self.pack_row)
        pts = self.pack_row.buttons["Points and penalties…"]
        pts.setObjectName("primary")            # the setting instructors most often want to adjust
        pts.setToolTip("Set the points of each rubric item and the deduction for each integrity finding")
        self.pack_info = WrapLabel("", "muted")
        form.addRow("", self.pack_info)

        self.sub_row = PathRow("The Moodle ZIP or its unzipped folder",
                               [("Folder…", self.choose_sub_folder), ("ZIP…", self.choose_sub_zip)])
        form.addRow("Submissions", self.sub_row)

        self.ws_csv_row = PathRow("Optional: Moodle gradebook export (.xlsx/.csv) or assignment grading worksheet",
                                  [("Choose…", self.choose_worksheet), ("Clear", lambda: self._set_ws_csv(None))])
        form.addRow("Class list", self.ws_csv_row)

        key_row = QWidget()
        self.key_row = key_row
        kl = QHBoxLayout(key_row)
        kl.setContentsMargins(0, 0, 0, 0)
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("sk-...  (stored on this computer only)")
        kl.addWidget(self.key_edit, 1)
        b = QPushButton("Save key")
        b.clicked.connect(self.save_key)
        kl.addWidget(b)
        rm = QPushButton("Remove")
        rm.setToolTip("Delete the saved key from this computer")
        rm.clicked.connect(self.remove_key)
        kl.addWidget(rm)
        self.test_btn = QPushButton("Test")
        self.test_btn.clicked.connect(self.test_key)
        kl.addWidget(self.test_btn)
        acc_btn = QPushButton("Load access file…")
        acc_btn.setToolTip("Use the access file your instructor gave you instead of typing a key")
        acc_btn.clicked.connect(self.load_access)
        kl.addWidget(acc_btn)
        form.addRow("AI access", key_row)
        self.key_status = WrapLabel("", "muted")
        form.addRow("", self.key_status)
        lay.addWidget(card2)

        act = QHBoxLayout()
        self.scan_btn = QPushButton("Import all documents")
        self.scan_btn.setObjectName("primary")
        self.scan_btn.setToolTip("Copy the assignment, the class list and the submissions chosen above into this "
                                 "workspace, and match each submission to the class list. Use it again after "
                                 "choosing a new Moodle download for late or re-uploaded work.")
        self.scan_btn.clicked.connect(self.import_all)
        act.addWidget(self.scan_btn, 0, Qt.AlignTop)
        self.scan_status = WrapLabel("", None)
        self.scan_status.setTextFormat(Qt.RichText)
        act.addWidget(self.scan_status, 1)
        lay.addLayout(act)


        # working with TAs -------------------------------------------------
        pk = QFrame()
        pk.setObjectName("card")
        pl = QVBoxLayout(pk)
        pl.setContentsMargins(18, 14, 18, 14)
        pt = QLabel("Working with TAs")
        pt.setObjectName("h2")
        pl.addWidget(pt)
        self.pk_info = WrapLabel("", "muted")
        pl.addWidget(self.pk_info)
        self.open_pkg_btn = QPushButton("Open a package from the instructor…")
        self.open_pkg_btn.clicked.connect(lambda: open_ta_package(self.state, self) and self.refresh())
        self.make_access_btn = QPushButton("Create TA access file…")
        self.make_access_btn.setObjectName("primary")
        self.make_access_btn.clicked.connect(lambda: AccessFileDialog(self, self.state).exec())
        self.make_pkg_btn = QPushButton("Create TA package…")
        self.make_pkg_btn.clicked.connect(lambda: TaPackageDialog(self.state, self).exec())
        self.import_btn = QPushButton("Import TA return file…")
        self.import_btn.clicked.connect(lambda: import_into_current(self.state, self))
        self.return_btn = QPushButton("Create return file for the instructor…")
        self.return_btn.setObjectName("primary")
        self.return_btn.clicked.connect(lambda: create_return_file(self.state, self))
        pl.addWidget(flow(self.make_access_btn, self.open_pkg_btn, self.make_pkg_btn, self.import_btn,
                          self.return_btn))
        lay.addWidget(pk)
        lay.addStretch(1)

        state.workspace_changed.connect(lambda: self.pending.update(pack=None, classlist=None))
        state.workspace_changed.connect(self.refresh)
        state.workspace_changed.connect(lambda: self.refresh_key())
        state.pack_changed.connect(self.refresh)
        self.refresh_recent()
        self.refresh_key()
        self.refresh()

    # -------------------------------------------------------------------
    def refresh_recent(self):
        self.recent.clear()
        self.recent.addItem("Recent…")
        for p in QSettings().value("recent_workspaces", []) or []:
            self.recent.addItem(Path(p).name, p)

    def open_recent(self, idx):
        p = self.recent.itemData(idx)
        if p:
            if not Path(p).exists():
                QMessageBox.information(self, "Not found", f"This workspace is no longer at\n{p}\n\n"
                                        "Press Open… and choose where it is now.")
                self.recent.setCurrentIndex(0)
                return
            self._open(Path(p))

    def _mode_ui(self):
        st = self.state
        ta = st.is_ta
        has_ws = st.store is not None
        self.instr_card.setVisible(not ta)
        self.scan_btn.setVisible(not ta)
        self.scan_status.setVisible(not ta)
        self.open_pkg_btn.setVisible(not has_ws)
        self.make_pkg_btn.setVisible(has_ws and not ta)
        self.make_access_btn.setVisible(key_source() == "own" and not ta)
        self.import_btn.setVisible(has_ws)
        self.import_btn.setText("Import update from the instructor…" if ta else "Import TA return file…")
        self.return_btn.setVisible(has_ws and ta)
        if not has_ws:
            self.pk_info.setText("TAs: if the instructor sent you a package, open it here. It creates your "
                                 "workspace. You do not need an API key.")
        elif ta:
            n = st.store.counts().get("rerun_requests", 0)
            ok, line = st.ai_status()
            self.pk_info.setText(
                "This is a TA workspace. No API key setup is needed here. " + line + " When you have graded, "
                "create a return file and send it to the instructor."
                + (f" {n} re-run request(s) are waiting to go with it." if n else ""))
        elif key_source() == "own":
            self.pk_info.setText(
                "Give each TA an access file once. With it, their copy of the app can run the pre-screen and "
                "re-runs for any assignment, and the key is never shown to them. Packages are optional: use them "
                "to hand a TA specific students with the AI results you already have.")
        else:
            self.pk_info.setText(
                "Packages let you pass students and grading between computers. Import a return file from a TA to "
                "collect their grading.")

    def _repair_note(self) -> str:
        rep = getattr(self.state, "last_repair", {}) or {}
        parts = []
        if rep.get("copied"):
            parts.append("Copied into this workspace so it no longer depends on other folders: "
                         + ", ".join(rep["copied"]) + ".")
        if rep.get("missing"):
            parts.append("Could not find " + ", ".join(rep["missing"]) + ". Choose them again below and scan.")
        return " ".join(parts)

    def refresh(self):
        st = self.state
        self._mode_ui()
        enabled = st.store is not None
        for w in (self.pack_row, self.sub_row, self.ws_csv_row, self.reviewer, self.scan_btn):
            w.setEnabled(enabled)
        self.ws_row.set(str(st.workspace) if st.workspace else None)
        if not enabled:
            self.pack_info.setText("")
            return
        self.pack_row.set(st.meta("pack_path"))
        self.sub_row.set(st.meta("submissions_path"))
        if st.meta("submissions_source"):
            self.sub_row.edit.setToolTip(f"Copied from {st.meta('submissions_source')}")
        self.ws_csv_row.set(st.meta("worksheet_path"))
        self.reviewer.setText(st.meta("reviewer", "") or "")
        note = self._repair_note()
        if note:
            self.scan_status.setText(note)
        if st.pack:
            rows = ", ".join(f"{r.label} ({r.max:g})" for r in st.pack.rubric)
            self.pack_info.setText(f"{st.pack.title}. Rubric: {rows}. Total {st.pack.total_max:g} points.")
        else:
            self.pack_info.setText("No assignment yet. Choose the assignment folder the instructor shared, or make a "
                                   "new one with New from documents. It is copied into the workspace.")
        counts = st.store.counts()
        if counts.get("total"):
            restored = getattr(st, "restored_findings", None) or []
            self.scan_status.setText(f"{counts['total']} submissions in this workspace."
                                     + (f" {note}" if note else "")
                                     + (f" Integrity findings that an earlier version had lost were put back for "
                                        f"{len(restored)} {'student' if len(restored) == 1 else 'students'}, now "
                                        f"marked to decide again: "
                                        f"{', '.join((st.store.submission(x) or {}).get('name') or x for x in restored[:8])}."
                                        if restored else ""))
        self._show_pending()

    def _open(self, folder: Path, create: bool = False) -> bool:
        if not create and is_cloud_folder(folder):
            box = QMessageBox(self)
            box.setWindowTitle("Workspace in a cloud folder")
            box.setText("This workspace is in a synced cloud folder (Google Drive, Dropbox, OneDrive or iCloud). "
                        "Grading inside it can lose work when the folder syncs from two computers.\n\n"
                        "Copy it to this computer and work on the copy? Share it again later by copying the "
                        "folder back, or with TA packages.")
            copy_btn = box.addButton("Copy to this computer and open", QMessageBox.AcceptRole)
            box.addButton("Open in place", QMessageBox.DestructiveRole)
            cancel = box.addButton(QMessageBox.Cancel)
            box.exec()
            if box.clickedButton() is cancel:
                return False
            if box.clickedButton() is copy_btn:
                try:
                    folder = copy_workspace(folder, local_workspaces_dir())
                except Exception as e:  # noqa: BLE001
                    QMessageBox.warning(self, "Could not copy", str(e))
                    return False
                QMessageBox.information(self, "Copied", f"Working on the copy in\n{folder}")
        try:
            self.state.open_workspace(folder, create=create)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Could not open the workspace", str(e))
            return False
        self.refresh_recent()
        return True

    def open_backups(self):
        if not self.state.workspace:
            QMessageBox.information(self, "No workspace", "Open a workspace first.")
            return
        from .backups import BackupDialog
        BackupDialog(self.state, self).exec()
        self.refresh()

    def choose_workspace(self):
        d = QFileDialog.getExistingDirectory(self, "Choose the workspace folder (or a folder that contains it)",
                                             str(Path.home()))
        if not d:
            return
        found = find_workspaces(Path(d))
        if not found:
            if QMessageBox.question(self, "No workspace here",
                                    "There is no grading workspace in this folder or the folders inside it.\n\n"
                                    "Make a new, empty workspace here?") == QMessageBox.Yes:
                self._create(Path(d))
            return
        if len(found) > 1:
            from PySide6.QtWidgets import QInputDialog
            names = [str(f.relative_to(d)) if f != Path(d) else f.name for f in found]
            name, ok = QInputDialog.getItem(self, "Several workspaces", "Open which workspace?", names, 0, False)
            if not ok:
                return
            folder = found[names.index(name)]
        else:
            folder = found[0]
        self._open(folder)

    def new_workspace(self):
        d = QFileDialog.getExistingDirectory(self, "Choose an empty folder for the new workspace", str(Path.home()))
        if not d:
            return
        d = Path(d)
        if find_workspaces(d, depth=1):
            QMessageBox.information(self, "Already a workspace", "This folder already holds a workspace. Use Open… "
                                    "to continue it, or choose an empty folder.")
            return
        self._create(d)

    def _create(self, d: Path):
        import shutil
        old_access = workspace_access_path()
        old_access = old_access if old_access and old_access.exists() else None
        if not self._open(d, create=True):
            return
        new_access = workspace_access_path()
        if old_access and new_access and not new_access.exists():
            shutil.copy2(old_access, new_access)   # AI access carries over to the new workspace
        self.refresh_key()

    def choose_pack(self):
        d = QFileDialog.getExistingDirectory(self, "Choose the assignment folder (contains pack.json). It is copied "
                                             "into the workspace.", str(Path.home()))
        if d:
            if not (Path(d) / "pack.json").exists():
                QMessageBox.warning(self, "Not an assignment folder",
                                    "This folder has no pack.json. Choose the assignment folder the instructor shared.")
                return
            self.pending["pack"] = d
            self._show_pending()

    def edit_penalties(self):
        if not self.state.pack or not self.state.store:
            QMessageBox.information(self, "No assignment", "Open a workspace and choose the assignment first.")
            return
        if PenaltyDialog(self.state, self).exec():
            self.refresh()

    def new_pack(self):
        dlg = NewPackDialog(self.state, self)
        if dlg.exec():
            self.refresh()

    def choose_sub_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Choose the folder with student submissions")
        if d:
            self.state.set_meta("submissions_path", d)
            self.refresh()
            self._show_pending()

    def choose_sub_zip(self):
        f, _ = QFileDialog.getOpenFileName(self, "Choose the Moodle download ZIP", "", "ZIP files (*.zip)")
        if f:
            self.state.set_meta("submissions_path", f)
            self.refresh()
            self._show_pending()

    def choose_worksheet(self):
        f, _ = QFileDialog.getOpenFileName(self, "Choose the class list", "",
                                           "Class list (*.xlsx *.csv);;All files (*)")
        if f:
            self.pending["classlist"] = f
            self._show_pending()

    def _show_pending(self):
        """Chosen but not copied in yet: say so, and point at the import button."""
        if self.pending.get("pack"):
            self.pack_row.set(self.pending["pack"])
            self.pack_info.setText("Chosen. Press Import all documents below to copy it into the workspace.")
        if self.pending.get("classlist"):
            self.ws_csv_row.set(self.pending["classlist"])
        waiting = [n for n, v in (("assignment", self.pending.get("pack")), ("class list", self.pending.get("classlist")))
                   if v]
        st = self.state
        sub = st.meta("submissions_path") if st.store else None
        if sub and st.workspace and Path(sub).resolve() != (st.workspace / "submissions").resolve():
            waiting.append("submissions")
        if waiting:
            self.scan_status.setText("<b>Not imported yet:</b> " + ", ".join(waiting) + ". Press Import all "
                                     "documents.")

    def _set_ws_csv(self, f):
        if f is None:                           # Clear: no class list
            self.pending["classlist"] = None
            self.state.set_meta("worksheet_path", None)
            self.refresh()
            return
        try:
            dest = import_classlist(self.state.store, Path(f))
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Could not copy the class list", str(e))
            return
        # students added before the class list was chosen are matched now, so the order of the steps does not matter
        if self.state.store.counts().get("total"):
            try:
                from ..pipeline import rematch_classlist
                m = rematch_classlist(self.state.store, dest)
                self.scan_status.setText(f"Class list applied: {m['matched']} students matched"
                                         + (f", {m['unmatched']} not found in it." if m["unmatched"] else "."))
                self.state.submissions_changed.emit()
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "Could not read the class list", str(e))
        self.refresh()

    def refresh_key(self, note: str = ""):
        src = key_source()
        if src == "own":
            self.key_edit.setEnabled(True)
            self.key_edit.setText(own_api_key())
            self.key_edit.setPlaceholderText("sk-...  (stored on this computer only)")
            msg = "Your own key is saved on this computer."
        elif src == "access":
            self.key_edit.clear()
            self.key_edit.setEnabled(False)
            self.key_edit.setPlaceholderText("Provided by the instructor's access file")
            msg = access_valid()[1]
        else:
            self.key_edit.setEnabled(True)
            self.key_edit.setPlaceholderText("sk-...  (stored on this computer only)")
            msg = access_valid()[1] or ("Type your key and press Save key, or load an access file from the "
                                        "instructor. It is kept inside this workspace.")
        self.key_status.setText((note + " " if note else "") + msg)
        if hasattr(self, "make_access_btn"):
            self.make_access_btn.setVisible(src == "own")

    def save_key(self):
        key = self.key_edit.text().strip()
        if not key:
            return
        where = set_api_key(key)
        self.refresh_key(f"Key saved in the {where}.")

    def remove_key(self):
        if key_source() == "own":
            remove_api_key()
            msg = "Your key was removed from this computer."
        else:
            remove_access_file()
            msg = "The access file was removed from this workspace."
        self.key_edit.clear()
        self.refresh_key(msg)

    def load_access(self):
        f, _ = QFileDialog.getOpenFileName(self, "Open the access file from your instructor", str(Path.home()),
                                           "Access file (*.m241access);;All files (*)")
        if not f:
            return
        try:
            load_access_file(f)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Could not load", str(e))
            return
        self.refresh_key("Access file loaded into this workspace." if workspace_access_path() else
                         "Access file loaded.")

    def test_key(self):
        key = self.key_edit.text().strip() or get_api_key()
        if not key:
            self.key_status.setText("Enter a key or load an access file first.")
            return
        mc = self.state.pack.model if self.state.pack else {"name": "gpt-6-luna"}
        model = [x for x in (mc.get("name"), mc.get("escalation_name")) if x]
        self.test_btn.setEnabled(False)
        self.key_status.setText("Testing…")
        self._t = TestKeyThread(key, model)
        self._t.done.connect(self._tested)
        self._t.start()

    def _tested(self, ok, msg):
        self.test_btn.setEnabled(True)
        self.key_status.setText(("✓ " if ok else "✗ ") + msg)

    def import_all(self):
        """Copy everything chosen above into the workspace: assignment, class list, then submissions (matched to the
        class list as they come in). Each part is reported on the status line."""
        st = self.state
        if not st.store:
            QMessageBox.information(self, "No workspace", "Open or make a workspace first.")
            return
        done = []
        if self.pending.get("pack"):
            try:
                st.set_pack(self.pending["pack"])
                self.pending["pack"] = None
                done.append("Assignment copied in.")
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "Not an assignment pack", str(e))
                return
        new_classlist = None
        if self.pending.get("classlist"):
            try:
                new_classlist = import_classlist(st.store, Path(self.pending["classlist"]))
                self.pending["classlist"] = None
                done.append("Class list copied in.")
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "Could not copy the class list", str(e))
                return
        sub = st.meta("submissions_path")
        fresh = sub and Path(sub).exists() and Path(sub).resolve() != (st.workspace / "submissions").resolve()
        if fresh:
            msg = self.scan(quiet=True)
            if msg is None:
                return
            done.append(msg)
        elif new_classlist is not None and st.store.counts().get("total"):
            from ..pipeline import rematch_classlist
            m = rematch_classlist(st.store, new_classlist)
            done.append(f"Students matched to the class list: {m['matched']}"
                        + (f", {m['unmatched']} not found in it." if m["unmatched"] else "."))
            st.submissions_changed.emit()
        elif not done:
            n = st.store.counts().get("total", 0)
            done.append(f"Everything is already in the workspace ({n} submissions). For late or re-uploaded work, "
                        "choose the new Moodle download above, then import again." if n else
                        "Choose the assignment and the submissions above first.")
        self.refresh()
        self.scan_status.setText(" ".join(done))
        glog.info("Import all documents: %s", " ".join(done))
        if fresh and getattr(self, "_added", 0):
            self.go_next.emit()                 # on to the Pre-screen tab

    def scan(self, quiet: bool = False):
        st = self.state
        if not st.pack:
            QMessageBox.information(self, "Assignment missing", "Choose the assignment folder first.")
            return None
        root = st.meta("submissions_path")
        if not root or not Path(root).exists():
            QMessageBox.information(self, "Submissions missing", "Choose the Moodle ZIP or submissions folder first.")
            return None
        self.state.set_meta("reviewer", self.reviewer.text().strip())
        internal = st.workspace / "submissions"
        if Path(root).resolve() == internal.resolve() and st.store.counts().get("total"):
            # older workspaces may still hold an unpacked Moodle download in submissions/; scan that once
            if not any(p.is_dir() for p in internal.iterdir()):
                return (f"All {st.store.counts()['total']} submissions are already in this workspace. To add new "
                        "or re-uploaded work, choose the new Moodle ZIP or folder above and import again.")
        ws = st.meta("worksheet_path")
        self.scan_status.setText("Copying the PDFs into the workspace…")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        try:
            stats = register_submissions(st.store, Path(root), Path(ws) if ws else None)
        except Exception as e:  # noqa: BLE001
            glog.exception("Adding submissions from %s failed: %s", root, e)
            self.scan_status.setText("")
            QMessageBox.warning(self, "Could not add the submissions", str(e))
            return None
        if stats["total"]:
            # from now on the workspace's own copies are the submissions; the download is no longer needed
            st.set_meta("submissions_source", str(root))
            st.set_meta("submissions_path", str(internal))
            self.sub_row.set(str(internal))
            self.sub_row.edit.setToolTip(f"Copied from {root}")
        msg = (f"Added to the workspace: {stats['total']} submissions, {stats['new']} new, {stats['same']} "
               f"unchanged, {stats['changed']} changed since last time. The Moodle download can be deleted.")
        if stats["notes"]:
            msg += " " + " ".join(stats["notes"][:3])
        self.scan_status.setText(msg)
        st.submissions_changed.emit()
        self._added = stats["total"]
        return msg
