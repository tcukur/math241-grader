"""Colors and stylesheet shared by the interface."""
from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QAbstractScrollArea, QAbstractSpinBox, QApplication, QComboBox, QLabel

STATUS = {
    "green": ("#3f8f5a", "#e9f4ec", "Nothing flagged"),
    "yellow": ("#b7791f", "#fdf3dc", "Check this"),
    "red": ("#c0392b", "#fbe7e5", "Likely problem"),
    "gray": ("#6b7280", "#f0f1f3", "Not assessed"),
}

ACCENT = "#3355d1"
ACCENT_DARK = "#2743b0"
ACCENT_SOFT = "#eef2fd"
BG = "#f3f5f9"
LINE = "#e3e7ee"
TEXT = "#0f172a"
MUTED = "#64748b"

STYLE = f"""
QWidget {{ font-size: 13px; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QToolTip {{ background: {TEXT}; color: white; border: none; border-radius: 6px; padding: 5px 8px; }}

QTabWidget::pane {{ border: none; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{ padding: 7px 16px; margin: 6px 2px 4px 2px; border: none; border-radius: 8px;
               color: {MUTED}; font-weight: 500; background: transparent; }}
QTabBar::tab:first {{ margin-left: 10px; }}
QTabBar::tab:hover {{ color: {TEXT}; background: #e8ecf3; }}
QTabBar::tab:selected {{ color: {ACCENT}; background: {ACCENT_SOFT}; font-weight: 600; }}

QPushButton {{ padding: 6px 13px; border: 1px solid #d5dbe5; border-radius: 8px; background: #ffffff;
               color: {TEXT}; }}
QPushButton:hover {{ background: #f5f7fb; border-color: #c3cbd8; }}
QPushButton:pressed {{ background: #e9edf4; }}
QPushButton:disabled {{ color: #a3abb8; background: #f7f8fa; border-color: {LINE}; }}
QPushButton:focus {{ outline: none; }}
QPushButton:checked {{ background: {ACCENT_SOFT}; border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton#primary {{ background: {ACCENT}; color: white; border: 1px solid {ACCENT}; font-weight: 600; }}
QPushButton#primary:hover {{ background: {ACCENT_DARK}; border-color: {ACCENT_DARK}; }}
QPushButton#primary:pressed {{ background: #1f3790; }}
QPushButton#primary:disabled {{ background: #aebce9; border-color: #aebce9; color: #f3f5fb; }}
QPushButton#level {{ padding: 5px 0px; min-width: 56px; }}
QPushButton#level:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton#level:checked {{ background: {ACCENT}; color: white; border-color: {ACCENT}; font-weight: 600; }}
QPushButton#link {{ border: none; background: transparent; color: {ACCENT}; text-align: left; padding: 1px 0px; }}
QPushButton#link:hover {{ text-decoration: underline; }}

QLineEdit, QPlainTextEdit, QComboBox {{ padding: 4px 7px; border: 1px solid #d5dbe5; border-radius: 8px;
                                        background: white; selection-background-color: {ACCENT}; }}
QLineEdit:hover, QPlainTextEdit:hover, QComboBox:hover {{ border-color: #c3cbd8; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QLineEdit:read-only {{ background: #f8f9fb; color: #334155; }}
QLineEdit:disabled, QComboBox:disabled {{ background: #f3f4f7; color: #a3abb8; }}
QComboBox QAbstractItemView {{ border: 1px solid {LINE}; border-radius: 6px; background: white;
                               selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT}; outline: none; }}

QLabel#muted {{ color: {MUTED}; }}
QLabel#h1 {{ font-size: 20px; font-weight: 700; }}
QLabel#h2 {{ font-size: 14px; font-weight: 600; padding-top: 4px; }}
QLabel#stepbadge {{ background: {ACCENT}; color: white; border-radius: 12px; font-weight: 700; font-size: 12px; }}
QLabel#sectiontitle {{ font-size: 15px; font-weight: 700; }}
QLabel#chip {{ background: #eef1f5; color: #475569; border-radius: 10px; padding: 2px 9px; font-weight: 600; }}
QLabel#grouplabel {{ color: {MUTED}; font-size: 11px; font-weight: 700; padding: 6px 0px 0px 2px; }}
QFrame#card {{ background: white; border: 1px solid {LINE}; border-bottom-color: #d3d9e3; border-radius: 12px; }}

QListWidget {{ border: 1px solid {LINE}; border-radius: 10px; background: white; padding: 4px; outline: none; }}
QListWidget::item {{ padding: 7px 6px; border-radius: 7px; margin: 1px 0px; }}
QListWidget::item:hover {{ background: #f5f7fb; }}
QListWidget::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}

QTableWidget, QTableView {{ border: 1px solid {LINE}; border-radius: 10px; background: white;
                            gridline-color: #eef1f5; alternate-background-color: #fafbfd;
                            selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT}; outline: none; }}
QHeaderView::section {{ background: #f7f8fb; color: {MUTED}; font-weight: 500; border: none;
                        border-bottom: 1px solid {LINE}; border-right: 1px solid #eef1f5; padding: 6px 4px; }}
QTableCornerButton::section {{ background: #f7f8fb; border: none; }}

QProgressBar {{ border: none; border-radius: 6px; text-align: center; height: 14px; background: #e6eaf1;
                color: {TEXT}; font-size: 11px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 6px; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #cdd3dd; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #aab3c1; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #cdd3dd; border-radius: 3px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: #aab3c1; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0px; height: 0px; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: #dbe1ea; }}
QMessageBox QLabel {{ min-width: 280px; }}

/* app bar: dark header with the app name, the steps and Help */
QFrame#appbar {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3d4452, stop:1 #4d5566);
                 border: none; border-bottom: 1px solid #353b47; }}
QLabel#logo {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #5b7cfa, stop:1 #3355d1);
               color: white; font-weight: 700; font-size: 13px; border-radius: 9px; }}
QLabel#brand {{ color: white; font-size: 15px; font-weight: 700; background: transparent; }}
QLabel#brandsub {{ color: #c2c8d3; font-size: 12px; background: transparent; }}
QTabBar#nav {{ background: transparent; }}
QTabBar#nav::tab {{ color: #e1e5ec; background: transparent; padding: 7px 14px; margin: 0px 2px;
                    border: none; border-radius: 8px; font-weight: 600; }}
QTabBar#nav::tab:first {{ margin-left: 0px; }}
QTabBar#nav::tab:hover {{ color: white; background: rgba(255, 255, 255, 0.12); }}
QTabBar#nav::tab:selected {{ color: {ACCENT_DARK}; background: white; }}
QTabBar#nav QToolButton {{ background: #4d5566; border: none; color: white; }}
QPushButton#appbarbtn {{ color: white; background: rgba(255, 255, 255, 0.10);
                         border: 1px solid rgba(255, 255, 255, 0.25); border-radius: 8px; padding: 5px 14px; }}
QPushButton#appbarbtn:hover {{ background: rgba(255, 255, 255, 0.18); }}
QPushButton#appbarbtn::menu-indicator {{ image: none; width: 0px; }}
QToolButton#linkbtn {{ color: {ACCENT}; background: transparent; border: none; padding: 0px 2px;
                       font-size: 12px; }}
QToolButton#linkbtn:hover {{ text-decoration: underline; }}
QToolButton#bankbtn {{ color: {ACCENT_DARK}; background: {ACCENT_SOFT}; border: 1px solid #d6defa;
                       border-radius: 7px; padding: 4px 10px; }}
QToolButton#bankbtn:hover {{ background: #e2e9fc; }}
QToolButton#bankbtn::menu-indicator {{ image: none; width: 0px; }}
QMenu {{ background: white; border: 1px solid {LINE}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 6px; color: {TEXT}; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT_DARK}; }}
QMenu::separator {{ height: 1px; background: {LINE}; margin: 4px 6px; }}
QStackedWidget#pages {{ background: {BG}; }}
"""


def load_fonts(app: QApplication) -> str:
    """Use the bundled Inter font so the app looks the same on Mac and Windows. If anything goes wrong,
    the system font stays in use."""
    try:
        from pathlib import Path
        from PySide6.QtGui import QFont, QFontDatabase
        folder = Path(__file__).resolve().parents[1] / "fonts"
        families = set()
        for f in sorted(folder.glob("Inter-*.ttf")):
            fid = QFontDatabase.addApplicationFont(str(f))
            if fid >= 0:
                families.update(QFontDatabase.applicationFontFamilies(fid))
        if "Inter" in families:
            font = QFont("Inter")
            font.setPixelSize(13)
            font.setHintingPreference(QFont.PreferNoHinting)
            app.setFont(font)
            return "Inter"
    except Exception:  # noqa: BLE001
        pass
    return ""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    load_fonts(app)
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(BG))
    pal.setColor(QPalette.Base, QColor("#ffffff"))
    pal.setColor(QPalette.AlternateBase, QColor("#fafbfd"))
    pal.setColor(QPalette.Text, QColor(TEXT))
    pal.setColor(QPalette.WindowText, QColor(TEXT))
    pal.setColor(QPalette.Button, QColor("#ffffff"))
    pal.setColor(QPalette.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)
    from .widgets import JUMP_STYLE
    app.setStyleSheet(STYLE + JUMP_STYLE)
    app._wheel_guard = WheelGuard(app)
    app.installEventFilter(app._wheel_guard)


class WrapLabel(QLabel):
    """Word-wrapped label whose height always follows its current width.

    Qt does not pass height-for-width through nested layouts reliably, so the label reports the height it
    needs for its present width as its minimum size hint and asks the layout to re-query on every resize.
    Nothing is stored, so the height shrinks again as the window gets wider."""

    def __init__(self, text: str = "", obj: str | None = None):
        super().__init__(text)
        self.setWordWrap(True)
        self._last_w = -1
        if obj:
            self.setObjectName(obj)

    def _need(self) -> int:
        if not self.text():
            return 0
        w = self.width() if self.width() > 40 else 400
        return self.heightForWidth(w) + 4

    def minimumSizeHint(self):
        return QSize(0, self._need())

    def sizeHint(self):
        hint = super().sizeHint()
        return QSize(hint.width(), self._need())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.width() != self._last_w:
            self._last_w = self.width()
            self.updateGeometry()

    def setText(self, text: str):
        super().setText(text)
        self.updateGeometry()


class WheelGuard(QObject):
    """Mouse-wheel scrolling over a drop-down or number box scrolls the page instead of changing the value,
    unless the box was clicked first. Prevents silent changes while scrolling through long panels."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and isinstance(obj, (QComboBox, QAbstractSpinBox)) and not obj.hasFocus():
            parent = obj.parentWidget()
            while parent is not None and not isinstance(parent, QAbstractScrollArea):
                parent = parent.parentWidget()
            if parent is not None:
                QApplication.sendEvent(parent.viewport(), event)
            return True
        if event.type() == QEvent.Polish and isinstance(obj, (QComboBox, QAbstractSpinBox)):
            obj.setFocusPolicy(Qt.StrongFocus)
        return False
