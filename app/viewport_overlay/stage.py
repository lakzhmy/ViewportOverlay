"""The top half of the window: the live render with glass controls floating on it."""
import math

from PySide6.QtCore import QEasingCurve, QPointF, QRect, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QCursor, QImage, QLinearGradient, QPainter, QPainterPath, QPen
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
from .theme import ASSETS, GRAY_500, INK_700, INK_850, INK_950, LIME, PAPER_50

BLUR_DIVISOR = 24
EDGE = 16
MARK = 148
GRID = 28
SOLID_WINDOW = (0.32, 0.32, 0.56, 0.56)  # the logo's orange window, as shares of the mark
REVEAL_MS = 560
FLASH_MS = 260
START_TITLE = "Point it at your model"
START_HINT = "Select a region over any app, and the render appears here live."
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
    maximise_clicked = Signal()
    close_clicked = Signal()

    def __init__(self, engine_switch: QWidget):
        super().__init__()
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._image = None
        self._frame = None
        self._blur = None
        self._glass = []
        self._floating = []
        self._chrome = 1.0
        self._live = False
        self._pulse = 0.0
        self._empty = None
        self._reveal = 1.0
        self._flash = 0.0
        self._mark = QSvgRenderer(str(ASSETS / "mark-color-on-dark.svg"))

        self.message = self._caption(START_TITLE, "stageTitle")
        self.hint = self._caption(START_HINT, "stageHint")

        self.logo = Logo()
        self.engine_switch = engine_switch
        self.live_card = LiveCard()
        self.minimise_button = WindowButton("minimise", "Minimise")
        self.maximise_button = WindowButton("maximise", "Maximise")
        self.close_button = WindowButton("close", "Close ViewportOverlay")
        self.minimise_button.clicked.connect(self.minimise_clicked)
        self.maximise_button.clicked.connect(self.maximise_clicked)
        self.close_button.clicked.connect(self.close_clicked)

        self._float(self.logo, DARK_GLASS, 12)
        self._float(self.engine_switch, LIGHT_GLASS, 16)
        self._float(self.live_card, DARK_GLASS, 14)
        self._float(self.minimise_button)
        self._float(self.maximise_button)
        self._float(self.close_button)
        self.live_card.hide()

        self._fade = QVariantAnimation(self)
        self._fade.setDuration(180)
        self._fade.valueChanged.connect(self.set_chrome)

        self._reveal_run = QVariantAnimation(self)
        self._reveal_run.setDuration(REVEAL_MS)
        self._reveal_run.setStartValue(0.0)
        self._reveal_run.setEndValue(1.0)
        self._reveal_run.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._reveal_run.valueChanged.connect(self._set_reveal)

        self._flash_run = QVariantAnimation(self)
        self._flash_run.setDuration(FLASH_MS)
        self._flash_run.setStartValue(0.5)
        self._flash_run.setEndValue(0.0)
        self._flash_run.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._flash_run.valueChanged.connect(self._set_flash)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(50)
        self._pulse_timer.timeout.connect(self._step_pulse)

    def _caption(self, text: str, name: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName(name)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        return label

    def _set_reveal(self, value: float):
        self._reveal = value
        self.update()

    def _set_flash(self, value: float):
        self._flash = value
        self.update()

    def flash(self):
        """A quick pale wash, like a camera, to show a capture happened."""
        self._flash_run.stop()
        self._flash_run.start()

    def current_image(self) -> QImage | None:
        return self._image

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
        self.hint.hide()
        self._rebuild()
        self.update()
        if first:
            self._reveal_run.start()
            if not self.underMouse():
                self._fade_to(0.0)

    def set_waiting(self, text: str):
        """Says what's happening while the first frame is on its way."""
        if self._image is None:
            self.message.setText(text)
            self.hint.setText("The first render takes a few seconds.")

    def clear(self):
        self._image = None
        self._reveal_run.stop()
        self._reveal = 1.0
        self.message.setText(START_TITLE)
        self.hint.setText(START_HINT)
        self.message.show()
        self.hint.show()
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

    def _mark_rect(self) -> QRectF:
        """Where the logo sits on the empty stage, in widget units."""
        top = max((self.height() - MARK - 90) / 2, 58)
        return QRectF((self.width() - MARK) / 2, top, MARK, MARK)

    def _paint_empty(self, size: QSize) -> QImage:
        """A faint drafting grid with the logo on it. Its orange window is where the render grows from."""
        image = QImage(size, QImage.Format.Format_RGB32)
        image.fill(QColor(INK_850))
        scale = self.devicePixelRatioF()
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(INK_700))
        step = GRID * scale
        for row in range(int(size.height() / step) + 2):
            for column in range(int(size.width() / step) + 2):
                painter.drawEllipse(QPointF(column * step, row * step), scale, scale)
        mark = self._mark_rect()
        self._mark.render(painter, QRectF(mark.topLeft() * scale, mark.size() * scale))
        painter.end()
        return image

    def _rebuild(self):
        """Compose the render once, and keep a blurred copy for the glass to show."""
        size = self.size() * self.devicePixelRatioF()
        if size.isEmpty():
            return
        if self._empty is None or self._empty.size() != size:
            self._empty = self._paint_empty(size)
        frame = QImage(size, QImage.Format.Format_RGB32)
        if self._image is None:
            frame = self._empty
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
        if self._reveal < 1.0:
            painter.drawImage(self.rect(), self._empty)
            painter.save()
            painter.setClipPath(self._reveal_shape())
            painter.drawImage(self.rect(), self._frame)
            painter.restore()
        else:
            painter.drawImage(self.rect(), self._frame)
        if self._flash > 0:
            wash = QColor(PAPER_50)
            wash.setAlphaF(self._flash)
            painter.fillRect(self.rect(), wash)
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

    def _reveal_shape(self) -> QPainterPath:
        """The render grows out of the logo's orange window until it fills the stage."""
        mark = self._mark_rect()
        x, y, w, h = SOLID_WINDOW
        seed = QRectF(mark.x() + x * MARK, mark.y() + y * MARK, w * MARK, h * MARK)
        full = QRectF(self.rect())
        t = self._reveal
        rect = QRectF(
            seed.x() + (full.x() - seed.x()) * t,
            seed.y() + (full.y() - seed.y()) * t,
            seed.width() + (full.width() - seed.width()) * t,
            seed.height() + (full.height() - seed.height()) * t,
        )
        radius = 12 * (1 - t)
        shape = QPainterPath()
        shape.addRoundedRect(rect, radius, radius)
        return shape

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
        mark = self._mark_rect()
        self.message.setGeometry(0, round(mark.bottom()) + 14, width, 34)
        self.hint.setGeometry(0, round(mark.bottom()) + 50, width, 22)
        self.logo.move(EDGE, 14)
        self.engine_switch.adjustSize()
        self.engine_switch.move((width - self.engine_switch.width()) // 2, 14)
        self.close_button.move(width - EDGE - WindowButton.SIZE, 16)
        self.maximise_button.move(self.close_button.x() - WindowButton.SIZE - 8, 16)
        self.minimise_button.move(self.maximise_button.x() - WindowButton.SIZE - 8, 16)
        self.live_card.move(width - EDGE - self.live_card.width(), height - self.live_card.height() - 34)
        self._rebuild()
        self.resized.emit()

    def enterEvent(self, event):
        self._fade_to(1.0)

    def leaveEvent(self, event):
        self.check_pointer()

    def check_pointer(self):
        """Fade the controls once the pointer has really gone.

        Over the maximise button Windows takes the mouse, which looks like leaving.
        """
        inside = self.rect().contains(self.mapFromGlobal(QCursor.pos()))
        if self._image is not None and not inside:
            self._fade_to(0.0)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.window().windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.maximise_clicked.emit()
