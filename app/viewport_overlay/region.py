"""Drawing the capture region, and the frame that shows, moves and resizes it."""
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QBitmap, QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .screen import exclude_from_capture
from .theme import FONT, INK_900, ORANGE

ACCENT = QColor(ORANGE)
INK = QColor(INK_900)
DIM = QColor(10, 11, 12, 115)
LINE = 2
DASH = 6
GAP = 4
HANDLE = 8
TAB_HEIGHT = 26
TAB_WIDTH = 220
TAB_INSET = 12
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
        painter.fillRect(self.rect(), DIM)
        if self._start is None:
            painter.setPen(QColor("white"))
            font = QFont(FONT)
            font.setPixelSize(20)
            painter.setFont(font)
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
        pen = QPen(ACCENT, LINE)
        pen.setDashPattern([DASH / LINE, GAP / LINE])
        painter.setPen(pen)
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
    """A dashed outline around the region. Clicks inside reach the app underneath."""

    changed = Signal(QRect)
    dismissed = Signal()

    def __init__(self):
        super().__init__(None, TOP_MOST)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self._area = QRect()
        self._tab = QRect()
        self._drag = None
        self._shape = None
        self._capture_hidden = True

    def showEvent(self, event):
        exclude_from_capture(self, self._capture_hidden)

    def set_capture_hidden(self, hidden: bool):
        self._capture_hidden = hidden
        exclude_from_capture(self, hidden)

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
        self.hide()

    def close_button(self) -> QRect:
        return QRect(self._tab.right() - CLOSE_WIDTH + 1, self._tab.top(), CLOSE_WIDTH, TAB_HEIGHT)

    def _inner(self) -> QRect:
        return QRect(QPoint(HANDLE, HANDLE + TAB_HEIGHT), self._area.size())

    def _handles(self) -> list:
        """Eight squares just outside the region, so they never land in the capture."""
        inner = self._inner()
        left, top = inner.left() - HANDLE, inner.top() - HANDLE
        right, bottom = inner.right() + 1, inner.bottom() + 1
        middle_x = inner.center().x() - HANDLE // 2
        middle_y = inner.center().y() - HANDLE // 2
        spots = [
            (left, top), (right, top), (left, bottom), (right, bottom),
            (middle_x, top), (middle_x, bottom), (left, middle_y), (right, middle_y),
        ]
        squares = [QRect(x, y, HANDLE, HANDLE) for x, y in spots]
        return [square for square in squares if not square.intersects(self._tab)]

    def _dashes(self) -> list:
        inner = self._inner()
        left, top = inner.left() - LINE, inner.top() - LINE
        right, bottom = inner.right() + 1, inner.bottom() + 1
        dashes = []
        for x in range(left, right + LINE, DASH + GAP):
            length = min(DASH, right + LINE - x)
            dashes += [QRect(x, top, length, LINE), QRect(x, bottom, length, LINE)]
        for y in range(top, bottom + LINE, DASH + GAP):
            length = min(DASH, bottom + LINE - y)
            dashes += [QRect(left, y, LINE, length), QRect(right, y, LINE, length)]
        return dashes

    def _update_shape(self):
        inner = self._inner()
        screen = QGuiApplication.screenAt(self._area.center()) or QGuiApplication.primaryScreen()
        room_above = self._area.top() - LINE - TAB_HEIGHT >= screen.geometry().top()
        tab_y = inner.top() - LINE - TAB_HEIGHT if room_above else inner.bottom() + 1 + LINE
        tab_width = max(min(TAB_WIDTH, inner.width() - 2 * TAB_INSET), CLOSE_WIDTH)
        self._tab = QRect(inner.left() + TAB_INSET, tab_y, tab_width, TAB_HEIGHT)

        shape = (self._area.size(), room_above)
        if shape == self._shape:  # moving keeps the same outline, so skip the redraw
            return
        self._shape = shape
        bitmap = QBitmap(self.size())
        bitmap.fill(Qt.GlobalColor.color0)
        painter = QPainter(bitmap)
        for part in self._dashes() + self._handles() + [self._tab]:
            painter.fillRect(part, Qt.GlobalColor.color1)
        painter.end()
        self.setMask(bitmap)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), ACCENT)
        painter.setPen(INK)
        font = QFont(FONT)
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        size = self._area.size()
        painter.drawText(
            self._tab.adjusted(10, 0, -CLOSE_WIDTH, 0),
            Qt.AlignmentFlag.AlignVCenter,
            f"Drag to move  ·  {size.width()} × {size.height()}",
        )
        button = self.close_button()
        painter.fillRect(button, INK)
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
