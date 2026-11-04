"""Small building blocks for the window: switches, swatches, the scale and resize grips."""
from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QCheckBox,
    QHBoxLayout,
    QPushButton,
    QSlider,
    QWidget,
)

from .theme import (
    FONT,
    GRAY_300,
    GRAY_400,
    GRAY_500,
    INK_700,
    INK_800,
    INK_900,
    INK_950,
    ORANGE,
    PAPER_100,
    PAPER_50,
)


class Segmented(QWidget):
    """A row of buttons where exactly one is selected."""

    currentIndexChanged = Signal(int)

    def __init__(self, name: str, items: list, spacing: int = 0, margin: int = 0, make=None):
        super().__init__()
        self.setObjectName(name)
        self._data = [data for _, data in items]
        self._labels = [text for text, _ in items]
        self._group = QButtonGroup(self)
        row = QHBoxLayout(self)
        row.setContentsMargins(margin, margin, margin, margin)
        row.setSpacing(spacing)
        for index, text in enumerate(self._labels):
            button = make(text, index) if make else QPushButton(text)
            button.setCheckable(True)
            button.setChecked(index == 0)
            self._group.addButton(button, index)
            row.addWidget(button)
        self._group.idToggled.connect(self._toggled)

    def _toggled(self, index: int, checked: bool):
        if checked:
            self.currentIndexChanged.emit(index)

    def setCurrentIndex(self, index: int):
        self._group.button(index).setChecked(True)

    def currentIndex(self) -> int:
        return self._group.checkedId()

    def currentData(self):
        return self._data[self.currentIndex()]

    def currentText(self) -> str:
        return self._labels[self.currentIndex()]


class WindowButton(QAbstractButton):
    """A round window button that sits on the render."""

    SIZE = 28

    def __init__(self, kind: str, tip: str):
        super().__init__()
        self._kind = kind
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setToolTip(tip)
        self._hot = False

    def set_hot(self, hot: bool):
        """Windows owns the maximise button's mouse events, so it reports hover this way."""
        if hot != self._hot:
            self._hot = hot
            self.update()

    def set_kind(self, kind: str):
        self._kind = kind
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill = QColor(PAPER_50)
        fill.setAlphaF(1.0 if self.underMouse() or self._hot else 0.82)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawEllipse(QRectF(self.rect()))
        pen = QPen(QColor(INK_900), 1.75)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        middle = self.SIZE / 2
        if self._kind == "close":
            painter.drawLine(QPointF(middle - 4.5, middle - 4.5), QPointF(middle + 4.5, middle + 4.5))
            painter.drawLine(QPointF(middle + 4.5, middle - 4.5), QPointF(middle - 4.5, middle + 4.5))
        elif self._kind == "maximise":
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(middle - 5, middle - 5, 10, 10), 2.5, 2.5)
        elif self._kind == "restore":
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(middle - 5.5, middle - 2.5, 8, 8), 2, 2)
            painter.drawArc(QRectF(middle - 2.5, middle - 5.5, 8, 8), 0, 90 * 16)
        else:
            painter.drawLine(QPointF(middle - 5, middle), QPointF(middle + 5, middle))


class Dot(QWidget):
    """The 8 px status light."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(8, 8)
        self._color = QColor(GRAY_500)

    def set_color(self, color: str):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(self.rect())


class Swatch(QAbstractButton):
    """A small material sample. The drawings are stand-ins until real sample renders exist."""

    WIDTH = 68
    TILE = 64

    def __init__(self, text: str, index: int):
        super().__init__()
        self.setText(text)
        self._index = index
        self.setFixedSize(self.WIDTH, self.TILE + 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def _sphere(self, painter, tile, light, dark, shine):
        centre = QPointF(tile.center())
        glow = QRadialGradient(centre + QPointF(-7, -8), 28)
        glow.setColorAt(0.0, QColor(light))
        glow.setColorAt(1.0, QColor(dark))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(centre, 19, 19)
        if shine:
            painter.setBrush(QColor(PAPER_50))
            painter.drawEllipse(centre + QPointF(-7, -8), 3.5, 2.5)

    def _marker(self, painter, tile):
        pen = QPen(QColor(INK_900), 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        left, top = tile.left(), tile.top()
        for lift in (0, 11):
            stroke = QPainterPath(QPointF(left + 13, top + 44 - lift))
            stroke.cubicTo(left + 24, top + 8 - lift, left + 38, top + 58 - lift, left + 51, top + 22 - lift)
            painter.drawPath(stroke)

    def _studio(self, painter, tile):
        left, top = tile.left(), tile.top()
        cone = QPainterPath(QPointF(left + 32, top))
        cone.lineTo(left + 58, top + 64)
        cone.lineTo(left + 6, top + 64)
        cone.closeSubpath()
        painter.fillPath(cone, QColor(INK_700))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PAPER_100))
        painter.drawEllipse(QPointF(left + 32, top + 44), 11, 11)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tile = QRect((self.WIDTH - self.TILE) // 2, 2, self.TILE, self.TILE)
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(tile), 12, 12)
        marker = self._index == 2
        base = PAPER_100 if marker else (INK_950 if self._index == 3 else INK_800)
        painter.fillPath(shape, QColor(base))
        painter.save()
        painter.setClipPath(shape)
        if self._index == 0:
            self._sphere(painter, tile, PAPER_50, INK_950, True)
        elif self._index == 1:
            self._sphere(painter, tile, PAPER_100, GRAY_500, False)
        elif marker:
            self._marker(painter, tile)
        else:
            self._studio(painter, tile)
        painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.isChecked():
            painter.setPen(QPen(QColor(ORANGE), 2))
            painter.drawRoundedRect(QRectF(tile).adjusted(-1, -1, 1, 1), 13, 13)
        elif self.underMouse():
            painter.setPen(QPen(QColor(GRAY_500), 1))
            painter.drawPath(shape)
        font = QFont(FONT)
        font.setPixelSize(13)
        painter.setFont(font)
        painter.setPen(QColor(PAPER_50 if self.isChecked() else GRAY_400))
        painter.drawText(QRect(0, self.TILE + 6, self.WIDTH, 18), Qt.AlignmentFlag.AlignCenter, self.text())


class Scale(QSlider):
    """A ruled scale, read like a measuring tool. Clicking jumps straight to that mark."""

    INSET = 8

    def __init__(self):
        super().__init__(Qt.Orientation.Horizontal)
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _x(self, value: int) -> float:
        span = self.width() - 2 * self.INSET
        return self.INSET + span * (value - self.minimum()) / (self.maximum() - self.minimum())

    def _follow(self, event):
        span = self.width() - 2 * self.INSET
        share = (event.position().x() - self.INSET) / span
        self.setValue(round(self.minimum() + share * (self.maximum() - self.minimum())))

    def mousePressEvent(self, event):
        self._follow(event)

    def mouseMoveEvent(self, event):
        self._follow(event)

    def mouseReleaseEvent(self, event):
        pass

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(GRAY_500), 1.25))
        for value in range(self.minimum(), self.maximum() + 1, 5):
            tall = value % 25 == 0
            x = self._x(value)
            painter.drawLine(QPointF(x, 4 if tall else 9), QPointF(x, 17))
        track = 27
        line = QPen(QColor(INK_700), 3)
        line.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(line)
        painter.drawLine(QPointF(self.INSET, track), QPointF(self.width() - self.INSET, track))
        line.setColor(QColor(ORANGE))
        painter.setPen(line)
        x = self._x(self.value())
        painter.drawLine(QPointF(self.INSET, track), QPointF(x, track))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PAPER_50))
        painter.drawRoundedRect(QRectF(x - 6, track - 10, 12, 20), 4, 4)


class Toggle(QCheckBox):
    """An on/off switch with its label beside it."""

    TRACK = QSize(30, 18)

    def sizeHint(self) -> QSize:
        width = self.fontMetrics().horizontalAdvance(self.text())
        return QSize(self.TRACK.width() + 8 + width + 2, 22)

    def hitButton(self, point) -> bool:
        return self.rect().contains(point)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        top = (self.height() - self.TRACK.height()) / 2
        track = QRectF(0, top, self.TRACK.width(), self.TRACK.height())
        on = self.isChecked()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PAPER_50 if on else INK_800))
        painter.drawRoundedRect(track, 9, 9)
        painter.setBrush(QColor(INK_900 if on else GRAY_400))
        painter.drawEllipse(QPointF(track.right() - 9 if on else track.left() + 9, track.center().y()), 6, 6)
        painter.setPen(QColor(GRAY_300))
        area = self.rect().adjusted(self.TRACK.width() + 8, 0, 0, 0)
        painter.drawText(area, Qt.AlignmentFlag.AlignVCenter, self.text())


class FolderButton(QPushButton):
    """Shows the chosen folder's name. A long name shortens with "…" instead of pushing other controls."""

    PADDING = 10
    LONGEST = 220
    SHORTEST = 70

    def __init__(self):
        super().__init__()
        self.setObjectName("folder")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._name = ""

    def set_name(self, name: str):
        self._name = name
        self.updateGeometry()
        self._fit()

    def _fit(self):
        self.ensurePolished()
        room = self.width() - self.PADDING
        self.setText(self.fontMetrics().elidedText(self._name, Qt.TextElideMode.ElideMiddle, room))

    def sizeHint(self) -> QSize:
        self.ensurePolished()
        width = self.fontMetrics().horizontalAdvance(self._name) + self.PADDING + 2
        return QSize(min(width, self.LONGEST), 22)

    def minimumSizeHint(self) -> QSize:
        return QSize(self.SHORTEST, 22)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()


class Grip(QWidget):
    """An invisible strip along a window edge. Dragging it resizes the window."""

    def __init__(self, parent, edges: Qt.Edge, cursor: Qt.CursorShape):
        super().__init__(parent)
        self._edges = edges
        self.setCursor(cursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.window().windowHandle().startSystemResize(self._edges)
