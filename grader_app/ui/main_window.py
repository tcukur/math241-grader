"""Main window: four tabs in workflow order."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu, QPushButton, QScrollArea, QStackedWidget,
                               QTabBar, QVBoxLayout, QWidget)

from .. import APP_NAME, APP_VERSION
from .export_tab import ExportTab
from .help import HelpDialog
from .review_tab import ReviewTab
from .run_tab import RunTab
from .setup_tab import SetupTab
from .state import AppState


class AppTabs(QWidget):
    """The steps as a menu in a dark app bar, with the pages below. Offers the parts of the QTabWidget
    interface the rest of the app uses (addTab, setCurrentIndex, currentChanged, widget, currentWidget)."""
    currentChanged = Signal(int)

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.bar = QFrame()
        self.bar.setObjectName("appbar")
        self.bar.setAttribute(Qt.WA_StyledBackground, True)
        h = QHBoxLayout(self.bar)
        h.setContentsMargins(16, 10, 16, 10)
        h.setSpacing(10)
        self.brand_box = QWidget()
        bl = QHBoxLayout(self.brand_box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(10)
        logo = QLabel("M")
        logo.setObjectName("logo")
        logo.setAlignment(Qt.AlignCenter)
        logo.setFixedSize(32, 32)
        bl.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        self.brand = QLabel(APP_NAME)
        self.brand.setObjectName("brand")
        self.sub = QLabel("No workspace open")
        self.sub.setObjectName("brandsub")
        self.sub.setMaximumWidth(280)
        names.addWidget(self.brand)
        names.addWidget(self.sub)
        bl.addLayout(names)
        h.addWidget(self.brand_box)
        h.addSpacing(18)
        self.tabbar = QTabBar()
        self.tabbar.setObjectName("nav")
        self.tabbar.setDrawBase(False)
        self.tabbar.setExpanding(False)
        self.tabbar.setUsesScrollButtons(False)
        self.tabbar.setElideMode(Qt.ElideNone)
        self.tabbar.setCursor(Qt.PointingHandCursor)
        self.tabbar.setFocusPolicy(Qt.NoFocus)
        h.addWidget(self.tabbar)
        h.addStretch(1)
        self.right = h
        v.addWidget(self.bar)
        self.stack = QStackedWidget()
        self.stack.setObjectName("pages")
        v.addWidget(self.stack, 1)
        self.tabbar.currentChanged.connect(self._changed)

    def add_right(self, w):
        self.right.addWidget(w)

    def addTab(self, widget, title):
        self.stack.addWidget(widget)
        self.titles = getattr(self, "titles", []) + [title]
        return self.tabbar.addTab(title)

    def _short_titles(self, short: bool):
        for i, t in enumerate(getattr(self, "titles", [])):
            num, _, rest = t.partition("  ")
            self.tabbar.setTabText(i, f"{num}  {rest.split()[0]}" if short and rest else t)

    def _changed(self, i):
        self.stack.setCurrentIndex(i)
        self.currentChanged.emit(i)

    def setCurrentIndex(self, i):
        self.tabbar.setCurrentIndex(i)

    def currentIndex(self):
        return self.tabbar.currentIndex()

    def count(self):
        return self.tabbar.count()

    def widget(self, i):
        return self.stack.widget(i)

    def currentWidget(self):
        return self.stack.currentWidget()

    def resizeEvent(self, e):
        # on a narrow window the steps keep their room and the name block steps aside
        self.brand_box.setVisible(e.size().width() >= 820)
        self._short_titles(e.size().width() < 1060)      # "3  Review" instead of "3  Review and grade"
        super().resizeEvent(e)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1440, 900)
        self.state = AppState()
        self.tabs = AppTabs()
        self.setup = SetupTab(self.state)
        self.run = RunTab(self.state)
        self.review = ReviewTab(self.state)
        self.export = ExportTab(self.state)
        # Every tab sits in a scroll area: when the window is smaller than a tab's content, scroll bars
        # appear instead of the window being forced larger than the screen.
        self.pages = {}
        for widget, title in ((self.setup, "1  Setup"), (self.run, "2  Pre-screen"),
                              (self.review, "3  Review and grade"), (self.export, "4  Export")):
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setFrameShape(QFrame.NoFrame)
            sa.setWidget(widget)
            self.pages[sa] = widget
            self.tabs.addTab(sa, title)
        self.setMinimumSize(640, 480)
        self.demo_btn = QPushButton("Demo workspace · Leave")
        self.demo_btn.setObjectName("demobadge")
        self.demo_btn.setStyleSheet("QPushButton#demobadge { background: #fde68a; color: #78350f; border: none; "
                                    "border-radius: 8px; font-weight: 600; padding: 5px 12px; }"
                                    "QPushButton#demobadge:hover { background: #fcd34d; }")
        self.demo_btn.setCursor(Qt.PointingHandCursor)
        self.demo_btn.setToolTip("Made-up students for trying the app. Click to go back to your own work.")
        self.demo_btn.clicked.connect(self.leave_demo)
        self.demo_btn.hide()
        self.tabs.add_right(self.demo_btn)
        self.asg_btn = QPushButton("Assignment")
        self.asg_btn.setObjectName("appbarbtn")
        self.asg_btn.setCursor(Qt.PointingHandCursor)
        self.asg_btn.setToolTip("The rubric, the handout and the solution, in a window you can keep open while "
                                "grading")
        self.asg_btn.clicked.connect(self.show_assignment)
        self.tabs.add_right(self.asg_btn)
        self.state.pack_changed.connect(self._asg_enabled)
        self.state.workspace_changed.connect(self._asg_enabled)
        help_btn = QPushButton("Help")
        help_btn.setObjectName("appbarbtn")
        help_btn.setCursor(Qt.PointingHandCursor)
        help_btn.setToolTip("User guide, what's new and version")
        menu = QMenu(help_btn)
        menu.addAction("Take the tour", self.start_tour)
        menu.addSeparator()
        menu.addAction("User guide", lambda: self._help("guide"))
        menu.addAction("What's new", lambda: self._help("changes"))
        menu.addAction("Open log folder", self._open_logs)
        menu.addSeparator()
        menu.addAction("About", lambda: self._help("about"))
        help_btn.setMenu(menu)
        self.tabs.add_right(help_btn)
        quit_btn = QPushButton("Quit")
        quit_btn.setObjectName("appbarbtn")
        quit_btn.setCursor(Qt.PointingHandCursor)
        quit_btn.setToolTip("Close the app. Your grading is already saved.")
        quit_btn.clicked.connect(self.close)
        self.tabs.add_right(quit_btn)
        self.setCentralWidget(self.tabs)
        self.setup.go_next.connect(lambda: self.tabs.setCurrentIndex(1))
        self.export.open_student.connect(self._open_student)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.state.workspace_changed.connect(self._title)
        from PySide6.QtCore import QTimer
        self._backup_timer = QTimer(self)
        self._backup_timer.timeout.connect(self._auto_backup)
        self._backup_timer.start(15 * 60 * 1000)      # every 15 minutes, only if something changed
        self._title()
        self._asg_enabled()

        last = QSettings().value("last_workspace", "")
        if last and Path(last).exists() and (Path(last) / "grading.db").exists():
            try:
                self.state.open_workspace(last)
            except Exception:  # noqa: BLE001
                pass  # the Setup tab lets the user open it again and shows the reason
        if not self.state.workspace and not QSettings().value("tour_offer_off", False, type=bool):
            QTimer.singleShot(500, self._offer_tour)       # a first start: offer the tour once the window is up

    def _help(self, kind: str):
        dlg = HelpDialog(self, kind)
        dlg.show()
        self._help_dialogs = [d for d in getattr(self, "_help_dialogs", []) if d.isVisible()] + [dlg]

    def _asg_enabled(self):
        self.asg_btn.setEnabled(bool(self.state.pack))

    def show_assignment(self):
        from .assignment_view import AssignmentWindow
        if getattr(self, "_asg", None) is None:
            self._asg = AssignmentWindow(self.state, self)
        self._asg.show_again()

    # the tour and the demo workspace ------------------------------------------------------------------
    def _offer_tour(self):
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox(self)
        box.setWindowTitle("Welcome")
        box.setIcon(QMessageBox.NoIcon)
        box.setText("<b>Welcome to the MATH241 Grader</b>")
        box.setInformativeText("New here? A short tour shows each step on six made-up students. It takes about "
                               "three minutes and needs no API key. You can also start it later from "
                               "Help › Take the tour.")
        go = box.addButton("Take the tour", QMessageBox.AcceptRole)
        box.addButton("Not now", QMessageBox.RejectRole)
        never = box.addButton("Don't ask again", QMessageBox.DestructiveRole)
        go.setObjectName("primary")
        go.style().unpolish(go)
        go.style().polish(go)
        box.setDefaultButton(go)
        box.exec()
        if box.clickedButton() is never:
            QSettings().setValue("tour_offer_off", True)
        elif box.clickedButton() is go:
            QSettings().setValue("tour_offer_off", True)
            self.start_tour()

    def start_tour(self):
        """Open a fresh demo workspace and walk through it. The workspace that was open is remembered, so the
        user can go back to it."""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QApplication, QMessageBox
        from .. import demo
        from ..workspace import local_workspaces_dir
        if getattr(self, "_tour", None) is not None:
            return
        st = self.state
        if not st.is_demo:
            QSettings().setValue("before_demo", str(st.workspace) if st.workspace else "")
            self.review._save()
            folder = local_workspaces_dir() / demo.DEMO_NAME
            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
            try:
                try:
                    demo.build(folder)
                except OSError:
                    # an older demo could not be removed (for example still open elsewhere): use a new folder
                    import time
                    folder = local_workspaces_dir() / f"{demo.DEMO_NAME} {time.strftime('%H%M%S')}"
                    demo.build(folder)
                st.open_workspace(folder)
            except Exception as e:  # noqa: BLE001
                QApplication.restoreOverrideCursor()
                QMessageBox.warning(self, "Tour", f"The demo workspace could not be made: {e}")
                return
            QApplication.restoreOverrideCursor()
        from .tour import TourOverlay
        self.tabs.setCurrentIndex(0)
        self._tour = TourOverlay(self, self._tour_done)

    def _tour_done(self, completed: bool):
        self._tour = None
        if not completed:
            self.tabs.setCurrentIndex(0)

    def leave_demo(self):
        """Back to the workspace that was open before the demo, or to an empty Setup tab."""
        from PySide6.QtWidgets import QMessageBox
        before = QSettings().value("before_demo", "")
        self.review._save()
        if before and (Path(before) / "grading.db").exists():
            try:
                self.state.open_workspace(before)
                self.tabs.setCurrentIndex(0)
                return
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "Leave the demo", f"Could not open {before}: {e}")
        self.tabs.setCurrentIndex(0)
        QMessageBox.information(self, "Your own workspace",
                                "Use New… next to Workspace to make a workspace for your assignment, or Open… for "
                                "one you already have. The demo closes when you do.")

    def _title(self):
        self.demo_btn.setVisible(self.state.is_demo)
        ws = self.state.workspace
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}" + (f"  ·  {ws.name}" if ws else ""))
        name = "Demo, made-up students" if self.state.is_demo else ws.name if ws else ""
        self.tabs.sub.setText((f"{name}  ·  " if ws else "No workspace open  ·  ") + f"v{APP_VERSION}")
        self.tabs.sub.setToolTip(str(ws) if ws else "")

    def _tab_changed(self, i):
        page = self.pages.get(self.tabs.widget(i))
        if page is self.review:
            self.review.refresh_list()
        elif page is self.run:
            self.run.refresh()
        elif page is self.export:
            self.export.refresh()


    def _open_logs(self):
        """The workspace's log folder: what to send along with a problem report."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from ..main import _log_dir
        d = (self.state.workspace / "logs") if self.state.workspace else _log_dir()
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:  # noqa: BLE001
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))

    def _open_student(self, sid: str):
        self.tabs.setCurrentIndex(2)
        self.review.select_student(sid)

    def _auto_backup(self):
        try:
            from ..backup import changed_since_last_backup
            if self.state.workspace and changed_since_last_backup(self.state.workspace / "grading.db"):
                self.review._save()
                self.state.backup()
        except Exception:  # noqa: BLE001
            pass

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if getattr(self, "_tour", None) is not None:
            self._tour.place()

    def closeEvent(self, e):
        self.review._save()
        if getattr(self, "_asg", None) is not None and self._asg.isVisible():
            self._asg.close()                   # remembers where it was
        try:
            from ..backup import changed_since_last_backup
            if self.state.workspace and changed_since_last_backup(self.state.workspace / "grading.db"):
                self.state.backup("close")
        except Exception:  # noqa: BLE001
            pass
        if self.run.thread:
            self.run.thread.runner.stop()
            self.run.thread.wait(3000)
        if getattr(self.run, "sim_thread", None):
            self.run.sim_thread.stop()          # it runs again after the next pre-screen, or on request
            self.run.sim_thread.wait(5000)
        super().closeEvent(e)
