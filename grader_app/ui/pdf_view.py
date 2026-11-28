"""Lightweight PDF viewer: lazy page rendering, zoom, jump to page with
highlighted evidence excerpts."""
from __future__ import annotations

import html

import pymupdf
from PySide6.QtCore import QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QLabel, QPushButton, QRubberBand, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from .theme import WrapLabel
from .widgets import flow


class PageLabel(QLabel):
    """One rendered page. Dragging a box on it selects that area (to check whether it holds real text)."""
    selected = Signal(int, QRect)

    def __init__(self, index: int):
        super().__init__()
        self.index = index
        self._origin = None
        self._band = QRubberBand(QRubberBand.Rectangle, self)
        self.setCursor(Qt.IBeamCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._origin = e.position().toPoint()
            self._band.setGeometry(QRect(self._origin, QSize()))
            self._band.show()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._origin is not None:
            self._band.setGeometry(QRect(self._origin, e.position().toPoint()).normalized())
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._origin is not None and e.button() == Qt.LeftButton:
            rect = QRect(self._origin, e.position().toPoint()).normalized()
            self._origin = None
            self._band.hide()
            if rect.width() > 4 and rect.height() > 4:
                self.selected.emit(self.index, rect)
        super().mouseReleaseEvent(e)


class PdfView(QWidget):
    def __init__(self):
        super().__init__()
        self.doc: pymupdf.Document | None = None
        self.zoom = 1.25
        self.labels: list[QLabel] = []
        self.rendered: dict[int, float] = {}
        self.highlights: dict[int, list] = {}
        self.selection: dict[int, list] = {}
        self.show_text = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.prev_btn = QPushButton("◀")
        self.prev_btn.setToolTip("Previous page")
        self.prev_btn.clicked.connect(lambda: self.goto(self.current_page() - 1))
        self.next_btn = QPushButton("▶")
        self.next_btn.setToolTip("Next page")
        self.next_btn.clicked.connect(lambda: self.goto(self.current_page() + 1))
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMinimumWidth(64)
        self.page_spin.editingFinished.connect(lambda: self.goto(self.page_spin.value()))
        self.page_total = QLabel("")
        self.page_total.setObjectName("muted")
        zo = QPushButton("−")
        zo.setToolTip("Zoom out")
        zo.clicked.connect(lambda: self.set_zoom(self.zoom / 1.15))
        zi = QPushButton("+")
        zi.setToolTip("Zoom in")
        zi.clicked.connect(lambda: self.set_zoom(self.zoom * 1.15))
        fit = QPushButton("Fit width")
        fit.clicked.connect(self.fit_width)
        self.text_btn = QPushButton("Show text")
        self.text_btn.setCheckable(True)
        self.text_btn.setToolTip("Tint every word that is real, selectable text. Screenshots and other images "
                                 "stay untinted. Drag a box on a page to read the text in that area.")
        self.text_btn.toggled.connect(self._toggle_text)
        lay.addWidget(flow(self.prev_btn, self.next_btn, QLabel("Page"), self.page_spin, self.page_total,
                           zo, zi, fit, self.text_btn))
        self.sel_info = WrapLabel("")
        self.sel_info.setTextFormat(Qt.RichText)
        self.sel_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.sel_info.setVisible(False)
        self.sel_info.setMaximumHeight(60)
        lay.addWidget(self.sel_info)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { background: #e4e8ef; border-radius: 10px; }")
        self.inner = QWidget()
        self.inner.setStyleSheet("background: #e4e8ef;")
        self.vbox = QVBoxLayout(self.inner)
        self.vbox.setSpacing(10)
        self.vbox.setContentsMargins(10, 10, 10, 10)
        self.vbox.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.scroll.setWidget(self.inner)
        lay.addWidget(self.scroll, 1)
        self.scroll.verticalScrollBar().valueChanged.connect(self._schedule)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._render_visible)

    # ------------------------------------------------------------------
    def load(self, path: str | None):
        if self.doc:
            self.doc.close()
            self.doc = None
        for lb in self.labels:
            self.vbox.removeWidget(lb)
            lb.hide()
            lb.setParent(None)
            lb.deleteLater()
        self.labels, self.rendered, self.highlights, self.selection = [], {}, {}, {}
        self.sel_info.setVisible(False)
        if not path:
            self.page_total.setText("")
            return
        try:
            from pathlib import Path as _P
            self.doc = pymupdf.open(stream=_P(path).read_bytes(), filetype="pdf")
        except Exception as e:  # noqa: BLE001
            lb = QLabel(f"Could not open PDF: {e}")
            self.vbox.addWidget(lb)
            self.labels.append(lb)
            return
        self.page_spin.setMaximum(max(1, len(self.doc)))
        self.page_total.setText(f"of {len(self.doc)}")
        for i in range(len(self.doc)):
            lb = PageLabel(i)
            lb.selected.connect(self._selected)
            lb.setStyleSheet("background: white;")
            lb.setAlignment(Qt.AlignCenter)
            self.vbox.addWidget(lb)
            self.labels.append(lb)
        self._resize_labels()
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(0))
        self._schedule()

    def _resize_labels(self):
        if not self.doc:
            return
        for i, lb in enumerate(self.labels):
            r = self.doc[i].rect
            lb.setFixedSize(int(r.width * self.zoom), int(r.height * self.zoom))
        self.rendered.clear()

    def set_zoom(self, z):
        page = self.current_page()
        self.zoom = max(0.4, min(4.0, z))
        self._resize_labels()
        QTimer.singleShot(0, lambda: self.goto(page))

    def fit_width(self):
        if not self.doc:
            return
        avail = self.scroll.viewport().width() - 30
        self.set_zoom(avail / self.doc[0].rect.width)

    def current_page(self) -> int:
        y = self.scroll.verticalScrollBar().value() + 20
        for i, lb in enumerate(self.labels):
            if lb.y() + lb.height() > y:
                return i + 1
        return max(1, len(self.labels))

    def goto(self, page: int, excerpt: str | None = None):
        if not self.doc or not self.labels:
            return
        page = max(1, min(len(self.labels), int(page)))
        if excerpt:
            self.clear_selection()
            self._set_highlight(page, excerpt)
        lb = self.labels[page - 1]
        y = lb.y() - 10
        rects = self.highlights.get(page)
        if rects:
            y += int(rects[0].y0 * self.zoom) - 120
        self.scroll.verticalScrollBar().setValue(max(0, y))
        self.page_spin.setValue(page)
        self._schedule()

    def show_rects(self, rects_by_page: dict, page: int):
        """Highlight the given areas ({page: [(x0, y0, x1, y1), ...]}) and turn to a page."""
        if not self.doc:
            return
        self.clear_selection()
        self.highlights = {int(p): [pymupdf.Rect(r) for r in rs] for p, rs in rects_by_page.items()}
        self.rendered.clear()
        self._goto_when_ready(page, 8)

    def _goto_when_ready(self, page: int, tries: int):
        """Turn to a page, trying again briefly while a just-opened document is still being laid out."""
        self.goto(page)
        if tries > 0 and abs(self.current_page() - page) > 1:
            QTimer.singleShot(60, lambda: self._goto_when_ready(page, tries - 1))

    def _set_highlight(self, page: int, excerpt: str):
        p = self.doc[page - 1]
        ex = " ".join(excerpt.split())
        rects = []
        for length in (len(ex), 60, 35, 20):
            needle = ex[:length].strip()
            if len(needle) < 6:
                break
            rects = p.search_for(needle)
            if rects:
                break
        self.highlights = {page: rects} if rects else {}
        self.rendered.pop(page - 1, None)

    def _schedule(self):
        self._timer.start(30)

    def _render_visible(self):
        if not self.doc:
            return
        vp_top = self.scroll.verticalScrollBar().value()
        vp_bot = vp_top + self.scroll.viewport().height()
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(self.current_page())
        self.page_spin.blockSignals(False)
        for i, lb in enumerate(self.labels):
            visible = lb.y() + lb.height() >= vp_top - 800 and lb.y() <= vp_bot + 800
            if visible and self.rendered.get(i) != self.zoom:
                self._render(i)
            elif not visible and i in self.rendered:
                lb.clear()
                del self.rendered[i]

    def _render(self, i: int):
        page = self.doc[i]
        dpr = self.devicePixelRatioF() or 1.0
        pix = page.get_pixmap(matrix=pymupdf.Matrix(self.zoom * dpr, self.zoom * dpr), alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
        qp = QPixmap.fromImage(img)
        qp.setDevicePixelRatio(dpr)
        layers = []
        if self.show_text:
            try:
                words = [pymupdf.Rect(w[:4]) for w in page.get_text("words")]
            except Exception:  # noqa: BLE001
                words = []
            layers.append((words, QColor(46, 160, 90, 55), 0))
        layers.append((self.selection.get(i + 1, []), QColor(51, 85, 209, 70), 1))
        layers.append((self.highlights.get(i + 1, []), QColor(255, 210, 0, 90), 2))
        if any(rects for rects, _, _ in layers):
            painter = QPainter(qp)
            painter.setPen(Qt.NoPen)
            for rects, colour, pad in layers:
                painter.setBrush(colour)
                for r in rects:
                    painter.drawRect(QRectF(r.x0 * self.zoom - pad, r.y0 * self.zoom - pad,
                                            r.width * self.zoom + 2 * pad, r.height * self.zoom + 2 * pad))
            painter.end()
        self.labels[i].setPixmap(qp)
        self.rendered[i] = self.zoom

    # text checks -----------------------------------------------------------
    def _toggle_text(self, on: bool):
        self.show_text = on
        self.rendered.clear()
        self._schedule()

    def _selected(self, i: int, rect: QRect):
        """Read the real text inside the dragged box and copy it, so a grader can see at once whether a part
        of the PDF is selectable text or only a picture of text."""
        if not self.doc:
            return
        page = self.doc[i]
        z = self.zoom
        clip = pymupdf.Rect(rect.left() / z, rect.top() / z, rect.right() / z, rect.bottom() / z) & page.rect
        try:
            words = page.get_text("words", clip=clip)
        except Exception:  # noqa: BLE001
            words = []
        words = [w for w in words if pymupdf.Rect(w[:4]).intersects(clip)]
        old = set(self.selection)
        self.selection = {i + 1: [pymupdf.Rect(w[:4]) for w in words]} if words else {}
        for p in old | set(self.selection):
            self.rendered.pop(p - 1, None)
        self._schedule()
        if words:
            try:
                text = page.get_text("text", clip=clip, sort=True).strip()
            except Exception:  # noqa: BLE001
                text = ""
            text = text or " ".join(w[4] for w in words)
            QGuiApplication.clipboard().setText(text)
            flat = " ".join(text.split())
            preview = html.escape(flat[:140]) + ("…" if len(flat) > 140 else "")
            self.sel_info.setText(
                f"<span style='color:#2e7d4f'><b>Selectable text</b></span> on page {i + 1}, "
                f"{len(words)} words, copied: <span style='color:#475569'>“{preview}”</span>")
        else:
            has_image = False
            try:
                has_image = any(pymupdf.Rect(b["bbox"]).intersects(clip) for b in page.get_image_info())
            except Exception:  # noqa: BLE001
                pass
            self.sel_info.setText(
                f"<span style='color:#c0392b'><b>No selectable text</b></span> in that area of page {i + 1}."
                + (" It is an image, for example a screenshot." if has_image else
                   " It may be a drawing, an image or empty space."))
        self.sel_info.setVisible(True)

    def clear_selection(self):
        for p in self.selection:
            self.rendered.pop(p - 1, None)
        self.selection = {}
        self.sel_info.setVisible(False)
