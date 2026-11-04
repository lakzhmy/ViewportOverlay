"""The top half of the window: the live render with glass controls floating on it."""
import math

from PySide6.QtCore import QRect, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .controls import Dot, WindowButton
from .theme import ASSETS, GRAY_500, INK_850, INK_950, LIME, PAPER_50

BLUR_DIVISOR = 24
EDGE = 16
DARK_GLASS = QColor(17, 18, 20, 125)
LIGHT_GLASS = QColor(243, 242, 238, 205)


def blurred(image: QImage, size: QSize) -> QImage:
    """A soft copy of the image: shrink it a lot, then stretch it back."""
    small = QSize(max(size.width() // BLUR_DIVISOR, 4), max(size.height() // BLUR_DIVISOR, 4))
    mode = Qt.TransformationMode.SmoothTransformation
    ignore = Qt.AspectRatioMode.IgnoreAspectRatio
    return image.scaled(small, ignore, mode).scaled(size, ignore, mode)


class Logo(QWidget):
    """The brand lockup. It sits on dark glass so it reads on any render."""

    def __init__(self):
        super().__init__()
        self._renderer = QSvgRenderer(str(ASSETS / "lockup-on-dark.svg"))
        box = self._renderer.defaultSize()
        self._art = QSize(144, round(144 * box.height() / box.width()))
        self.setFixedSize(self._art.width() + 24, self._art.height() + 16)

    def paintEvent(self, event):
        painter = QPainter(self)
        self._renderer.render(painter, QRectF(QRect(12, 8, self._art.width(), self._art.height())))


class LiveCard(QWidget):
    """Shows whether frames are streaming, how fast, and at what size."""

    def __init__(self):
        super().__init__()
        self.dot = Dot()
        self.state = QLabel("Stopped")
        self.state.setObjectName("liveState")
        self.rate = QLabel("–")
        self.rate.setObjectName("liveRate")
        self.size_label = QLabel("")
        self.size_label.setObjectName("liveSize")
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.dot)
        top.addWidget(self.state)
        top.addStretch()
        column = QVBoxLayout(self)
        column.setContentsMargins(14, 10, 14, 10)
        column.setSpacing(2)
        column.addLayout(top)
        column.addWidget(self.rate)
        column.addWidget(self.size_label)
        self.setFixedSize(136, 88)

    def show_state(self, text: str, color: str = GRAY_500):
        self.state.setText(text)
        self.dot.set_color(color)


class Stage(QWidget):
    resized = Signal()
    minimise_clicked = Signal()
    close_clicked = Signal()

    def __init__(self, engine_switch: QWidget):
        super().__init__()
        self.setMinimumHeight(300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._image = None
        self._frame = None
        self._blur = None
        self._glass = []
        self._floating = []
        self._chrome = 1.0
        self._live = False
        self._pulse = 0.0

        self.message = QLabel("Select a region to get started", self)
        self.message.setObjectName("stageMessage")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.logo = Logo()
        self.engine_switch = engine_switch
        self.live_card = LiveCard()
        self.minimise_button = WindowButton("minimise", "Minimise")
        self.close_button = WindowButton("close", "Close ViewportOverlay")
        self.minimise_button.clicked.connect(self.minimise_clicked)
        self.close_button.clicked.connect(self.close_clicked)

        self._float(self.logo, DARK_GLASS, 12)
        self._float(self.engine_switch, LIGHT_GLASS, 16)
        self._float(self.live_card, DARK_GLASS, 14)
        self._float(self.minimise_button)
        self._float(self.close_button)
        self.live_card.hide()

        self._fade = QVariantAnimation(self)
        self._fade.setDuration(180)
        self._fade.valueChanged.connect(self.set_chrome)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(50)
        self._pulse_timer.timeout.connect(self._step_pulse)

    def _float(self, widget, tint=None, radius=0):
        widget.setParent(self)
        effect = QGraphicsOpacityEffect(widget)
        effect.setEnabled(False)
        widget.setGraphicsEffect(effect)
        self._floating.append(effect)
        if tint is not None:
            self._glass.append((widget, tint, radius))

    def show_image(self, image: QImage):
        first = self._image is None
        self._image = image
        self.message.hide()
        self._rebuild()
        self.update()
        if first and not self.underMouse():
            self._fade_to(0.0)

    def clear(self, message: str):
        self._image = None
        self.message.setText(message)
        self.message.show()
        self.set_live(False)
        self._fade_to(1.0)
        self._rebuild()
        self.update()

    def set_live(self, live: bool):
        self._live = live
        if live and not self._pulse_timer.isActive():
            self._pulse_timer.start()
        elif not live:
            self._pulse_timer.stop()
            self.update()

    def set_chrome(self, value: float):
        self._chrome = value
        for effect in self._floating:
            effect.setEnabled(value < 1.0)
            effect.setOpacity(value)
        self.update()

    def _fade_to(self, value: float):
        self._fade.stop()
        self._fade.setStartValue(self._chrome)
        self._fade.setEndValue(value)
        self._fade.start()

    def _step_pulse(self):
        self._pulse = (self._pulse + 0.2) % (2 * math.pi)
        self.update()

    def _rebuild(self):
        """Compose the render once, and keep a blurred copy for the glass to show."""
        size = self.size() * self.devicePixelRatioF()
        if size.isEmpty():
            return
        frame = QImage(size, QImage.Format.Format_RGB32)
        if self._image is None:
            frame.fill(QColor(INK_850))
        else:
            painter = QPainter(frame)
            cover = self._image.size().scaled(size, Qt.AspectRatioMode.KeepAspectRatioByExpanding)
            backdrop = QRect(0, 0, cover.width(), cover.height())
            backdrop.moveCenter(frame.rect().center())
            painter.drawImage(backdrop, blurred(self._image, cover))
            shade = QColor(INK_950)
            shade.setAlpha(120)
            painter.fillRect(frame.rect(), shade)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            fit = self._image.size().scaled(size, Qt.AspectRatioMode.KeepAspectRatio)
            target = QRect(0, 0, fit.width(), fit.height())
            target.moveCenter(frame.rect().center())
            painter.drawImage(target, self._image)
            painter.end()
        self._frame = frame
        self._blur = blurred(frame, size)

    def paintEvent(self, event):
        if self._frame is None:
            self._rebuild()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(self.rect(), self._frame)
        if self._chrome > 0:
            for widget, tint, radius in self._glass:
                if widget.isVisible():
                    self._paint_glass(painter, QRectF(widget.geometry()), tint, radius)
        if self._live:
            glow = QColor(LIME)
            glow.setAlphaF(0.16 + 0.3 * (0.5 + 0.5 * math.sin(self._pulse)))
            painter.setPen(QPen(glow, 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5))

    def _paint_glass(self, painter, rect, tint, radius):
        shape = QPainterPath()
        shape.addRoundedRect(rect, radius, radius)
        painter.save()
        painter.setOpacity(self._chrome)
        painter.setClipPath(shape)
        painter.drawImage(self.rect(), self._blur)
        painter.fillPath(shape, tint)
        shine = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        shine.setColorAt(0.0, QColor(255, 255, 255, 46))
        shine.setColorAt(0.55, QColor(255, 255, 255, 0))
        painter.fillPath(shape, shine)
        painter.setClipping(False)
        edge = QColor(PAPER_50)
        edge.setAlpha(80)
        painter.setPen(QPen(edge, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(shape)
        painter.restore()

    def resizeEvent(self, event):
        width, height = self.width(), self.height()
        self.message.setGeometry(self.rect())
        self.logo.move(EDGE, 14)
        self.engine_switch.adjustSize()
        self.engine_switch.move((width - self.engine_switch.width()) // 2, 14)
        self.close_button.move(width - EDGE - WindowButton.SIZE, 16)
        self.minimise_button.move(self.close_button.x() - WindowButton.SIZE - 8, 16)
        self.live_card.move(width - EDGE - self.live_card.width(), height - self.live_card.height() - 34)
        self._rebuild()
        self.resized.emit()

    def enterEvent(self, event):
        self._fade_to(1.0)

    def leaveEvent(self, event):
        if self._image is not None:
            self._fade_to(0.0)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.window().windowHandle().startSystemMove()
