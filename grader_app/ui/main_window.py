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
        help_btn = QPushButton("Help")
        help_btn.setObjectName("appbarbtn")
        help_btn.setCursor(Qt.PointingHandCursor)
        help_btn.setToolTip("User guide, what's new and version")
        menu = QMenu(help_btn)
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

        last = QSettings().value("last_workspace", "")
        if last and Path(last).exists() and (Path(last) / "grading.db").exists():
            try:
                self.state.open_workspace(last)
            except Exception:  # noqa: BLE001
                pass  # the Setup tab lets the user open it again and shows the reason

    def _help(self, kind: str):
        dlg = HelpDialog(self, kind)
        dlg.show()
        self._help_dialogs = [d for d in getattr(self, "_help_dialogs", []) if d.isVisible()] + [dlg]

    def _title(self):
        ws = self.state.workspace
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}" + (f"  ·  {ws.name}" if ws else ""))
        self.tabs.sub.setText((f"{ws.name}  ·  " if ws else "No workspace open  ·  ") + f"v{APP_VERSION}")
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

    def closeEvent(self, e):
        self.review._save()
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
