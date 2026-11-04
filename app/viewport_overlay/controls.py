"""The camera's parts: logo, shutter, orb, strength bar, text switches and resize grips."""
from PySide6.QtCore import QByteArray, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QRadialGradient
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton, QButtonGroup, QGridLayout, QSlider, QWidget

from .theme import ASSETS, FONT, GRAY_400, GRAY_500, INK_700, INK_900, ORANGE, PAPER_50


def paint_orb(painter: QPainter, area: QRectF, colors: tuple):
    """A soft glossy ball in the look's colours."""
    highlight, body, edge = colors
    radius = area.width() / 2
    glow = QRadialGradient(area.center(), radius * 1.1, area.center() + QPointF(radius * 0.3, -radius * 0.25))
    glow.setColorAt(0.0, QColor(highlight))
    glow.setColorAt(0.5, QColor(body))
    glow.setColorAt(1.0, QColor(edge))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(glow)
    painter.drawEllipse(area)


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


class LogoButton(QAbstractButton):
    """The logo is the region button. Its inner window turns orange while a region is selected."""

    SIZE = 56

    def __init__(self):
        super().__init__()
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        art = (ASSETS / "mark-color-on-dark.svg").read_text(encoding="utf-8")
        self._on_art = QSvgRenderer(QByteArray(art.encode()), self)
        self._off_art = QSvgRenderer(QByteArray(art.replace(ORANGE, PAPER_50).encode()), self)
        self.on = False

    def set_on(self, on: bool):
        self.on = on
        self.setToolTip("Clear the region" if on else "Select a region")
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(self.rect())
        shade = QRadialGradient(area.center(), area.width() / 2)  # keeps the white logo readable on pale renders
        shade.setColorAt(0.0, QColor(10, 11, 12, 120 if self.underMouse() else 80))
        shade.setColorAt(0.7, QColor(10, 11, 12, 50))
        shade.setColorAt(1.0, QColor(10, 11, 12, 0))
        painter.fillRect(area, shade)
        (self._on_art if self.on else self._off_art).render(painter, area)


class Shutter(QAbstractButton):
    """A hollow ring, like a phone camera's shutter button."""

    SIZE = 62

    def __init__(self):
        super().__init__()
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def hitButton(self, point) -> bool:
        offset = QPointF(point) - QRectF(self.rect()).center()
        return offset.x() ** 2 + offset.y() ** 2 <= (self.SIZE / 2) ** 2

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(1.0 if self.isEnabled() else 0.4)
        area = QRectF(self.rect())
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(10, 11, 12, 70), 6))  # a dark casing so the ring reads on pale renders
        painter.drawEllipse(area.adjusted(4, 4, -4, -4))
        painter.setPen(QPen(QColor(PAPER_50), 4))
        painter.drawEllipse(area.adjusted(4, 4, -4, -4))
        if self.isEnabled() and (self.isDown() or self.underMouse()):
            fill = QColor(PAPER_50)
            fill.setAlphaF(0.95 if self.isDown() else 0.4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawEllipse(area.adjusted(11, 11, -11, -11))


class Orb(QAbstractButton):
    """Shows the current look. Clicking it opens the look panel."""

    SIZE = 62

    def __init__(self):
        super().__init__()
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Change the look")
        self._colors = None

    def set_colors(self, colors: tuple):
        self._colors = colors
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        paint_orb(painter, area, self._colors)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(10, 11, 12, 60), 1))
        painter.drawEllipse(area)


class LookButton(QAbstractButton):
    """One look in the panel: a small orb and its name."""

    def __init__(self, look):
        super().__init__()
        self.setText(look.label)
        self._colors = look.colors
        self.setCheckable(True)
        self.setFixedSize(138, 44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.isChecked():
            painter.setPen(QPen(QColor(GRAY_500), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(area, 12, 12)
        paint_orb(painter, QRectF(7, 5, 34, 34), self._colors)
        font = QFont(FONT)
        font.setPixelSize(14)
        painter.setFont(font)
        painter.setPen(QColor(INK_900 if self.isChecked() or self.underMouse() else GRAY_500))
        painter.drawText(self.rect().adjusted(50, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, self.text())


class LookBox(QWidget):
    """The looks, filling one column before starting the next. Exactly one is selected."""

    currentIndexChanged = Signal(int)

    def __init__(self, looks: list, rows: int = 4):
        super().__init__()
        self._looks = looks
        self._group = QButtonGroup(self)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        for index, look in enumerate(looks):
            button = LookButton(look)
            button.setChecked(index == 0)
            self._group.addButton(button, index)
            grid.addWidget(button, index % rows, index // rows)
        self._group.idToggled.connect(self._toggled)

    def _toggled(self, index: int, checked: bool):
        if checked:
            self.currentIndexChanged.emit(index)

    def setCurrentIndex(self, index: int):
        self._group.button(index).setChecked(True)

    def currentIndex(self) -> int:
        return self._group.checkedId()

    def currentData(self):
        return self._looks[self.currentIndex()]


class StrengthBar(QSlider):
    """How closely the render follows your drawing. Strict is at the top."""

    WIDTH = 26
    peek = Signal(bool)  # True while the number should show

    def __init__(self):
        super().__init__(Qt.Orientation.Vertical)
        self.setFixedWidth(self.WIDTH)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setToolTip("Follow my drawing: Strict at the top, Loose at the bottom")
        self._dragging = False

    def dot_y(self) -> float:
        radius = self.WIDTH / 2
        share = (self.value() - self.minimum()) / (self.maximum() - self.minimum())
        return radius + (self.height() - self.WIDTH) * (1 - share)

    def _follow(self, event):
        radius = self.WIDTH / 2
        share = 1 - (event.position().y() - radius) / (self.height() - self.WIDTH)
        self.setValue(round(self.minimum() + share * (self.maximum() - self.minimum())))

    def enterEvent(self, event):
        self.peek.emit(True)

    def leaveEvent(self, event):
        if not self._dragging:
            self.peek.emit(False)

    def mousePressEvent(self, event):
        self._dragging = True
        self._follow(event)

    def mouseMoveEvent(self, event):
        self._follow(event)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self.peek.emit(self.rect().contains(event.position().toPoint()))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = self.WIDTH / 2
        track = QColor(PAPER_50)
        track.setAlphaF(0.9)
        painter.setPen(QPen(QColor(10, 11, 12, 50), 1))
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(ORANGE))
        painter.drawEllipse(QPointF(radius, self.dot_y()), radius, radius)


class LineButton(QAbstractButton):
    """Text in the bottom line. Underlined means on. A long text shortens from the left."""

    LONGEST = 200

    def __init__(self, text: str = "", switch: bool = True, shortest: int = 0):
        super().__init__()
        self.setText(text)
        self.setCheckable(switch)
        self._shortest = shortest
        self._font = QFont(FONT)
        self._font.setPixelSize(13)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def set_text(self, text: str):
        self.setText(text)
        self.updateGeometry()
        self.update()

    def shown_text(self) -> str:
        return QFontMetrics(self._font).elidedText(self.text(), Qt.TextElideMode.ElideLeft, self.width())

    def sizeHint(self) -> QSize:
        return QSize(min(QFontMetrics(self._font).horizontalAdvance(self.text()) + 2, self.LONGEST), 22)

    def minimumSizeHint(self) -> QSize:
        return QSize(self._shortest, 22) if self._shortest else self.sizeHint()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self._font)
        on = self.isEnabled() and (self.isChecked() or not self.isCheckable())
        color = QColor(GRAY_400 if not self.isEnabled() else INK_900 if self.underMouse() else INK_700 if on else GRAY_500)
        painter.setPen(color)
        painter.drawText(QRect(0, 0, self.width(), 19), Qt.AlignmentFlag.AlignVCenter, self.shown_text())
        if on:
            painter.setPen(QPen(color, 1))
            painter.drawLine(QPointF(0, 20.5), QPointF(self.width(), 20.5))


class Grip(QWidget):
    """An invisible strip along a window edge. Dragging it resizes the window."""

    def __init__(self, parent, edges: Qt.Edge, cursor: Qt.CursorShape):
        super().__init__(parent)
        self._edges = edges
        self.setCursor(cursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.window().windowHandle().startSystemResize(self._edges)
