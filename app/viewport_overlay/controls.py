"""Small building blocks for the window: pill switches, buttons and resize grips."""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QButtonGroup, QHBoxLayout, QPushButton, QWidget

from .theme import GRAY_500, INK_900, PAPER_50


class Segmented(QWidget):
    """A row of buttons where exactly one is selected."""

    currentIndexChanged = Signal(int)

    def __init__(self, name: str, items: list, spacing: int = 0, margin: int = 0):
        super().__init__()
        self.setObjectName(name)
        self._data = [data for _, data in items]
        self._labels = [text for text, _ in items]
        self._group = QButtonGroup(self)
        row = QHBoxLayout(self)
        row.setContentsMargins(margin, margin, margin, margin)
        row.setSpacing(spacing)
        for index, text in enumerate(self._labels):
            button = QPushButton(text)
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
    """A round minimise or close button that sits on the render."""

    SIZE = 28

    def __init__(self, kind: str, tip: str):
        super().__init__()
        self._kind = kind
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setToolTip(tip)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill = QColor(PAPER_50)
        fill.setAlphaF(1.0 if self.underMouse() else 0.82)
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


class Grip(QWidget):
    """An invisible strip along a window edge. Dragging it resizes the window."""

    def __init__(self, parent, edges: Qt.Edge, cursor: Qt.CursorShape):
        super().__init__(parent)
        self._edges = edges
        self.setCursor(cursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.window().windowHandle().startSystemResize(self._edges)
