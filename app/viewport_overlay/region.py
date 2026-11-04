"""Drawing the capture region, and the frame that shows, moves and resizes it.

The frame is the outlined window from the logo: a rounded line, with a gap where
the glass pill sits. Everything drawn stays outside the area being captured.
"""
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRegion,
)
from PySide6.QtWidgets import QWidget

from .screen import exclude_from_capture
from .theme import FONT, GRAY_300, GRAY_500, INK_900, LIME, MONO, ORANGE, PAPER_50

DIM = QColor(10, 11, 12, 115)
CASING = QColor(10, 11, 12, 120)  # keeps the pale line readable on white slides
GLASS = QColor(17, 18, 20, 214)
GRAB_FILL = QColor(0, 0, 0, 1)  # looks empty, but still catches the mouse
LINE = 3
OFFSET = 5  # from the capture edge to the middle of the line
RADIUS = 14
ARM = 12
GAP = 6
HANDLE = 12  # width of the band around the region that can be grabbed
TAB_HEIGHT = 26
TAB_WIDTH = 124
TAB_INSET = 34
CLOSE_WIDTH = 28
MIN_SIZE = 64

TOP_MOST = (
    Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.Tool
)


def line_rect(area: QRect) -> QRectF:
    return QRectF(area).adjusted(-OFFSET, -OFFSET, OFFSET, OFFSET)


def corner_arcs(rect: QRectF) -> QPainterPath:
    """The four orange corners, which show where to grab."""
    left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()
    r, across = RADIUS, 2 * RADIUS
    path = QPainterPath()
    path.moveTo(left, top + r + ARM)
    path.lineTo(left, top + r)
    path.arcTo(QRectF(left, top, across, across), 180, -90)
    path.lineTo(left + r + ARM, top)
    path.moveTo(right - r - ARM, top)
    path.lineTo(right - r, top)
    path.arcTo(QRectF(right - across, top, across, across), 90, -90)
    path.lineTo(right, top + r + ARM)
    path.moveTo(right, bottom - r - ARM)
    path.lineTo(right, bottom - r)
    path.arcTo(QRectF(right - across, bottom - across, across, across), 0, -90)
    path.lineTo(right - r - ARM, bottom)
    path.moveTo(left + r + ARM, bottom)
    path.lineTo(left + r, bottom)
    path.arcTo(QRectF(left, bottom - across, across, across), 270, -90)
    path.lineTo(left, bottom - r - ARM)
    return path


def paint_outline(painter: QPainter, area: QRect, canvas: QRect, gap: QRect = None):
    rect = line_rect(area)
    shape = QPainterPath()
    shape.addRoundedRect(rect, RADIUS, RADIUS)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if gap is not None:
        painter.setClipRegion(QRegion(canvas) - QRegion(gap.adjusted(-GAP, 0, GAP, 0)))
    painter.setPen(QPen(CASING, LINE + 2))
    painter.drawPath(shape)
    painter.setPen(QPen(QColor(PAPER_50), LINE))
    painter.drawPath(shape)
    pen = QPen(QColor(ORANGE), LINE + 1)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawPath(corner_arcs(rect))
    painter.restore()


def paint_pill(painter: QPainter, rect: QRect):
    """Smoky glass. The app behind shows through, but it can't be blurred from here."""
    area = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
    radius = area.height() / 2
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    shine = QLinearGradient(area.topLeft(), area.bottomLeft())
    shine.setColorAt(0.0, QColor(255, 255, 255, 44))
    shine.setColorAt(0.6, QColor(255, 255, 255, 0))
    edge = QColor(PAPER_50)
    edge.setAlpha(80)
    painter.setPen(QPen(edge, 1))
    painter.setBrush(GLASS)
    painter.drawRoundedRect(area, radius, radius)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(shine)
    painter.drawRoundedRect(area, radius, radius)
    painter.restore()


def readout_font() -> QFont:
    font = QFont(MONO)
    font.setPixelSize(12)
    return font


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

    def _paint_hint(self, painter):
        font = QFont(FONT)
        font.setPixelSize(16)
        painter.setFont(font)
        text = "Drag over what you want to render. Esc to cancel."
        pill = QRect(0, 0, painter.fontMetrics().horizontalAdvance(text) + 48, 48)
        pill.moveCenter(self.rect().center())
        paint_pill(painter, pill)
        painter.setPen(QColor(PAPER_50))
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), DIM)
        if self._start is None:
            self._paint_hint(painter)
            return
        area = self._selection()
        hole = QPainterPath()
        hole.addRoundedRect(line_rect(area), RADIUS, RADIUS)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillPath(hole, Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        paint_outline(painter, area, self.rect())
        if area.width() >= MIN_SIZE and area.height() >= MIN_SIZE:
            pill = QRect(area.center().x() - 50, area.center().y() - 13, 100, TAB_HEIGHT)
            paint_pill(painter, pill)
            painter.setFont(readout_font())
            painter.setPen(QColor(PAPER_50))
            painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, f"{area.width()} × {area.height()}")

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
    """A rounded outline around the region. Clicks inside reach the app underneath."""

    changed = Signal(QRect)
    dismissed = Signal()

    def __init__(self):
        super().__init__(None, TOP_MOST)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self._area = QRect()
        self._tab = QRect()
        self._drag = None
        self._shape = None
        self._live = False
        self._capture_hidden = True

    def showEvent(self, event):
        exclude_from_capture(self, self._capture_hidden)

    def set_capture_hidden(self, hidden: bool):
        self._capture_hidden = hidden
        exclude_from_capture(self, hidden)

    def set_live(self, live: bool):
        if live != self._live:
            self._live = live
            self.update()

    def area(self) -> QRect:
        return QRect(self._area)

    def set_area(self, area: QRect):
        self._area = QRect(area)
        margin = HANDLE + TAB_HEIGHT
        self.setGeometry(area.adjusted(-HANDLE, -margin, HANDLE, margin))
        self._update_shape()
        self.update()

    def clear(self):
        self._area = QRect()
        self._drag = None
        self._shape = None
        self._live = False
        self.hide()

    def close_button(self) -> QRect:
        return QRect(self._tab.right() - CLOSE_WIDTH + 1, self._tab.top(), CLOSE_WIDTH, TAB_HEIGHT)

    def _inner(self) -> QRect:
        return QRect(QPoint(HANDLE, HANDLE + TAB_HEIGHT), self._area.size())

    def _update_shape(self):
        inner = self._inner()
        screen = QGuiApplication.screenAt(self._area.center()) or QGuiApplication.primaryScreen()
        room_above = self._area.top() - TAB_HEIGHT >= screen.geometry().top()
        tab_y = inner.top() - TAB_HEIGHT if room_above else inner.bottom() + 1
        tab_width = max(min(TAB_WIDTH, inner.width() - 2 * TAB_INSET), CLOSE_WIDTH)
        self._tab = QRect(inner.left() + min(TAB_INSET, inner.width() // 4), tab_y, tab_width, TAB_HEIGHT)

        shape = (self._area.size(), room_above)
        if shape == self._shape:  # moving keeps the same outline, so skip the rebuild
            return
        self._shape = shape
        band = QRegion(inner.adjusted(-HANDLE, -HANDLE, HANDLE, HANDLE)) - QRegion(inner)
        self.setMask(band + QRegion(self._tab))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), GRAB_FILL)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        paint_outline(painter, self._inner(), self.rect(), self._tab)
        paint_pill(painter, self._tab)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(LIME if self._live else GRAY_500))
        middle = self._tab.center().y() + 0.5
        if self._tab.width() >= TAB_WIDTH:
            painter.drawEllipse(QPointF(self._tab.left() + 14, middle), 4, 4)
            painter.setFont(readout_font())
            painter.setPen(QColor(PAPER_50))
            size = self._area.size()
            painter.drawText(
                self._tab.adjusted(24, 0, -CLOSE_WIDTH, 0),
                Qt.AlignmentFlag.AlignVCenter,
                f"{size.width()} × {size.height()}",
            )
        pen = QPen(QColor(GRAY_300), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        centre = QRectF(self.close_button()).center()
        painter.drawLine(centre + QPointF(-4, -4), centre + QPointF(4, 4))
        painter.drawLine(centre + QPointF(4, -4), centre + QPointF(-4, 4))

    def _edges(self, point: QPoint) -> str:
        if self.close_button().contains(point):
            return "close"
        if self._tab.contains(point):
            return "move"
        inner = self._inner()
        edges = ""
        if point.y() < inner.top():
            edges += "n"
        if point.y() > inner.bottom():
            edges += "s"
        if point.x() < inner.left():
            edges += "w"
        if point.x() > inner.right():
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
