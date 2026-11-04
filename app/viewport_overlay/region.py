"""Drawing the capture region, and the frame that shows, moves and resizes it."""
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen, QRegion
from PySide6.QtWidgets import QWidget

from .screen import exclude_from_capture

ACCENT = QColor("#FFB020")
BORDER = 6
TAB_HEIGHT = 26
TAB_WIDTH = 220
CLOSE_WIDTH = 28
MIN_SIZE = 64

TOP_MOST = (
    Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.Tool
)


class SelectionLayer(QWidget):
    """A dimmed layer over one monitor, for dragging out a rectangle."""

    picked = Signal(QRect)
    cancelled = Signal()

    def __init__(self, screen):
        super().__init__(None, TOP_MOST)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(screen.geometry())
        self._start = None
        self._end = None

    def _selection(self) -> QRect:
        left, right = sorted((self._start.x(), self._end.x()))
        top, bottom = sorted((self._start.y(), self._end.y()))
        return QRect(left, top, right - left, bottom - top)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))
        if self._start is None:
            painter.setPen(QColor("white"))
            painter.setFont(QFont("Segoe UI", 16))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Drag over the area you want to render. Press Esc to cancel.",
            )
            return
        area = self._selection()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(area, Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(QPen(ACCENT, 2))
        painter.drawRect(area)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()

    def mousePressEvent(self, event):
        self._start = self._end = event.position().toPoint()
        self.update()

    def mouseMoveEvent(self, event):
        if self._start is not None:
            self._end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if self._start is None:
            return
        area = self._selection()
        self._start = None
        if area.width() >= MIN_SIZE and area.height() >= MIN_SIZE:
            self.picked.emit(area.translated(self.geometry().topLeft()))
        else:
            self.update()


class RegionPicker(QWidget):
    """Shows one selection layer per monitor and reports the result."""

    picked = Signal(QRect)
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self._layers = []

    def begin(self):
        for screen in QGuiApplication.screens():
            layer = SelectionLayer(screen)
            layer.picked.connect(self._finish_picked)
            layer.cancelled.connect(self._finish_cancelled)
            layer.show()
            layer.activateWindow()
            self._layers.append(layer)

    def _close_layers(self):
        for layer in self._layers:
            layer.close()
            layer.deleteLater()
        self._layers = []

    def _finish_picked(self, area: QRect):
        self._close_layers()
        self.picked.emit(area)

    def _finish_cancelled(self):
        self._close_layers()
        self.cancelled.emit()


class RegionFrame(QWidget):
    """A hollow border around the region. Clicks inside reach the app underneath."""

    changed = Signal(QRect)
    dismissed = Signal()

    def __init__(self):
        super().__init__(None, TOP_MOST)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self._area = QRect()
        self._tab = QRect()
        self._drag = None

    def showEvent(self, event):
        exclude_from_capture(self)

    def area(self) -> QRect:
        return QRect(self._area)

    def set_area(self, area: QRect):
        self._area = QRect(area)
        margin = BORDER + TAB_HEIGHT
        self.setGeometry(area.adjusted(-BORDER, -margin, BORDER, margin))
        self._update_shape()
        self.update()

    def clear(self):
        self._area = QRect()
        self._drag = None
        self.hide()

    def close_button(self) -> QRect:
        return QRect(self._tab.right() - CLOSE_WIDTH + 1, self._tab.top(), CLOSE_WIDTH, TAB_HEIGHT)

    def _inner(self) -> QRect:
        return QRect(QPoint(BORDER, BORDER + TAB_HEIGHT), self._area.size())

    def _update_shape(self):
        inner = self._inner()
        outer = inner.adjusted(-BORDER, -BORDER, BORDER, BORDER)
        screen = QGuiApplication.screenAt(self._area.center()) or QGuiApplication.primaryScreen()
        room_above = self._area.top() - BORDER - TAB_HEIGHT >= screen.geometry().top()
        tab_y = outer.top() - TAB_HEIGHT if room_above else outer.bottom() + 1
        self._tab = QRect(outer.left(), tab_y, min(TAB_WIDTH, outer.width()), TAB_HEIGHT)
        self.setMask(QRegion(outer).subtracted(QRegion(inner)).united(QRegion(self._tab)))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), ACCENT)
        painter.setPen(QColor("#1B1B1F"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        size = self._area.size()
        painter.drawText(
            self._tab.adjusted(10, 0, -CLOSE_WIDTH, 0),
            Qt.AlignmentFlag.AlignVCenter,
            f"Drag to move  ·  {size.width()} × {size.height()}",
        )
        button = self.close_button()
        painter.fillRect(button, QColor("#1B1B1F"))
        painter.setPen(QPen(ACCENT, 2))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cross = button.adjusted(9, 8, -9, -8)
        painter.drawLine(cross.topLeft(), cross.bottomRight())
        painter.drawLine(cross.topRight(), cross.bottomLeft())

    def _edges(self, point: QPoint) -> str:
        if self.close_button().contains(point):
            return "close"
        if self._tab.contains(point):
            return "move"
        inner = self._inner()
        grip = 14
        edges = ""
        if point.y() < inner.top() + grip:
            edges += "n"
        if point.y() > inner.bottom() - grip:
            edges += "s"
        if point.x() < inner.left() + grip:
            edges += "w"
        if point.x() > inner.right() - grip:
            edges += "e"
        return edges

    def mouseMoveEvent(self, event):
        if self._drag is None:
            self.setCursor(CURSORS.get(self._edges(event.position().toPoint()), Qt.CursorShape.ArrowCursor))
            return
        edges, start, area = self._drag
        delta = event.globalPosition().toPoint() - start
        moved = QRect(area)
        if edges == "move":
            moved.translate(delta)
        else:
            if "n" in edges:
                moved.setTop(min(area.top() + delta.y(), area.bottom() - MIN_SIZE))
            if "s" in edges:
                moved.setBottom(max(area.bottom() + delta.y(), area.top() + MIN_SIZE))
            if "w" in edges:
                moved.setLeft(min(area.left() + delta.x(), area.right() - MIN_SIZE))
            if "e" in edges:
                moved.setRight(max(area.right() + delta.x(), area.left() + MIN_SIZE))
        self.set_area(moved)
        self.changed.emit(moved)

    def mousePressEvent(self, event):
        edges = self._edges(event.position().toPoint())
        if edges == "close":
            self.dismissed.emit()
        elif edges:
            self._drag = (edges, event.globalPosition().toPoint(), QRect(self._area))

    def mouseReleaseEvent(self, event):
        self._drag = None

    def sizeHint(self) -> QSize:
        return self._area.size()


CURSORS = {
    "close": Qt.CursorShape.PointingHandCursor,
    "move": Qt.CursorShape.SizeAllCursor,
    "n": Qt.CursorShape.SizeVerCursor,
    "s": Qt.CursorShape.SizeVerCursor,
    "w": Qt.CursorShape.SizeHorCursor,
    "e": Qt.CursorShape.SizeHorCursor,
    "nw": Qt.CursorShape.SizeFDiagCursor,
    "se": Qt.CursorShape.SizeFDiagCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor,
    "sw": Qt.CursorShape.SizeBDiagCursor,
}
