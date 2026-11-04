"""The viewfinder: the live render with the camera's controls floating on it."""
import math

from PySide6.QtCore import QEasingCurve, QRect, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QCursor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .controls import LineButton, LogoButton, LookBox, Orb, Shutter, StrengthBar, WindowButton
from .looks import LOOKS
from .theme import INK_950, LIME, PAPER_50, STONE

BLUR_DIVISOR = 24
EDGE = 16
RADIUS = 14
POINTER_CHECK_MS = 100
BAR_LONGEST = 300
PANEL_GAP = 12
SOLID_WINDOW = (0.32, 0.32, 0.56, 0.56)  # the logo's inner window, as shares of the mark
REVEAL_MS = 560
FLASH_MS = 260
START_TITLE = "Click the logo to select a region"
START_HINT = "Whatever is under it renders here, live."


def blurred(image: QImage, size: QSize) -> QImage:
    """A soft copy of the image: shrink it a lot, then stretch it back."""
    small = QSize(max(size.width() // BLUR_DIVISOR, 4), max(size.height() // BLUR_DIVISOR, 4))
    mode = Qt.TransformationMode.SmoothTransformation
    ignore = Qt.AspectRatioMode.IgnoreAspectRatio
    return image.scaled(small, ignore, mode).scaled(size, ignore, mode)


class LookPanel(QFrame):
    """Opens from the orb: which look to render in."""

    def __init__(self):
        super().__init__()
        self.setObjectName("panel")
        self.setFixedSize(320, 258)
        self.look_box = LookBox(LOOKS)
        local = LineButton("Local")
        local.setChecked(True)
        local.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        cloud = LineButton("Cloud")
        cloud.setEnabled(False)
        cloud.setToolTip("Cloud looks aren't built yet")
        tabs = QHBoxLayout()
        tabs.setSpacing(12)
        tabs.addWidget(local)
        tabs.addWidget(cloud)
        tabs.addStretch()
        column = QVBoxLayout(self)
        column.setContentsMargins(16, 14, 16, 12)
        column.setSpacing(10)
        column.addWidget(self.look_box)
        column.addStretch()
        column.addLayout(tabs)

    def mousePressEvent(self, event):
        event.accept()  # a click on the panel's background shouldn't count as clicking away


class Stage(QWidget):
    resized = Signal()
    minimise_clicked = Signal()
    maximise_clicked = Signal()
    close_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._image = None
        self._frame = None
        self._floating = []
        self._live = False
        self._pulse = 0.0
        self._reveal = 1.0
        self._flash = 0.0
        self._chrome = 1.0
        self._chrome_target = 1.0

        self.message = self._caption(START_TITLE, "stageTitle")
        self.hint = self._caption(START_HINT, "stageHint")

        self.logo = LogoButton()
        self.logo.set_on(False)
        self.shutter = Shutter()
        self.orb = Orb()
        self.bar = StrengthBar()
        self.minimise_button = WindowButton("minimise", "Minimise")
        self.maximise_button = WindowButton("maximise", "Maximise")
        self.close_button = WindowButton("close", "Close ViewportOverlay")
        self.minimise_button.clicked.connect(self.minimise_clicked)
        self.maximise_button.clicked.connect(self.maximise_clicked)
        self.close_button.clicked.connect(self.close_clicked)
        self.orb.clicked.connect(lambda: self.show_panel(True))
        for widget in (self.logo, self.shutter, self.orb, self.bar):
            self._float(widget)

        self.amount = QLabel(self)
        self.amount.setObjectName("amount")
        self.amount.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.amount.hide()
        self.bar.peek.connect(self._peek_amount)
        self.bar.valueChanged.connect(self._place_amount)

        self.panel = LookPanel()
        self.panel.setParent(self)
        self.panel.hide()

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

        self._pointer_timer = QTimer(self)
        self._pointer_timer.setInterval(POINTER_CHECK_MS)
        self._pointer_timer.timeout.connect(self._check_pointer)
        self._pointer_timer.start()

    def _caption(self, text: str, name: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName(name)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        return label

    def _float(self, widget):
        widget.setParent(self)
        effect = QGraphicsOpacityEffect(widget)
        effect.setEnabled(False)
        widget.setGraphicsEffect(effect)
        self._floating.append(effect)

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

    def show_image(self, image: QImage):
        first = self._image is None
        self._image = image
        self.message.hide()
        self.hint.hide()
        self._rebuild()
        self.update()
        if first:
            self._reveal_run.start()

    def set_waiting(self, text: str):
        """Says what's happening while the first frame is on its way."""
        if self._image is None:
            self.message.setText(text)
            self.hint.setText("The first render takes a few seconds.")

    def show_start(self):
        """Back to the opening words, if a region was dropped before anything rendered."""
        if self._image is None:
            self.message.setText(START_TITLE)
            self.hint.setText(START_HINT)

    def set_live(self, live: bool):
        self._live = live
        if live and not self._pulse_timer.isActive():
            self._pulse_timer.start()
        elif not live:
            self._pulse_timer.stop()
            self.update()

    def show_panel(self, shown: bool):
        self.panel.setVisible(shown)
        self.orb.setVisible(not shown)
        self._place_shutter()

    def _place_shutter(self):
        covered = self.panel.isVisibleTo(self) and self.panel.geometry().intersects(self.shutter.geometry())
        self.shutter.setVisible(not covered)

    def _peek_amount(self, shown: bool):
        self.amount.setVisible(shown)
        self._place_amount()

    def _place_amount(self):
        self.amount.setText(f"Follow my drawing  {self.bar.value()}")
        self.amount.adjustSize()
        x = self.bar.x() - self.amount.width() - 8
        self.amount.move(x, round(self.bar.y() + self.bar.dot_y() - self.amount.height() / 2))

    def set_chrome(self, value: float):
        self._chrome = value
        for effect in self._floating:
            effect.setEnabled(value < 1.0)
            effect.setOpacity(value)
            effect.parent().update()

    def _fade_to(self, value: float):
        self._fade.stop()
        self._fade.setStartValue(self._chrome)
        self._fade.setEndValue(value)
        self._fade.start()

    def _step_pulse(self):
        self._pulse = (self._pulse + 0.2) % (2 * math.pi)
        self.update()

    def _rebuild(self):
        """Compose the render once: the whole image, on a soft copy of itself."""
        size = self.size() * self.devicePixelRatioF()
        if size.isEmpty() or self._image is None:
            return
        frame = QImage(size, QImage.Format.Format_RGB32)
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

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(self.rect()), RADIUS, RADIUS)
        painter.setClipPath(shape)
        if self._frame is None or self._reveal < 1.0:
            painter.fillRect(self.rect(), QColor(STONE))
        if self._frame is not None:
            if self._reveal < 1.0:
                painter.setClipPath(self._reveal_shape().intersected(shape))
            painter.drawImage(self.rect(), self._frame)
            painter.setClipPath(shape)
        if self._flash > 0:
            wash = QColor(PAPER_50)
            wash.setAlphaF(self._flash)
            painter.fillRect(self.rect(), wash)
        if self._live:
            glow = QColor(LIME)
            glow.setAlphaF(0.16 + 0.3 * (0.5 + 0.5 * math.sin(self._pulse)))
            painter.setPen(QPen(glow, 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            inset = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
            painter.drawRoundedRect(inset, RADIUS - 1, RADIUS - 1)

    def _reveal_shape(self) -> QPainterPath:
        """The render grows out of the logo's inner window until it fills the viewfinder."""
        logo = QRectF(self.logo.geometry())
        x, y, w, h = SOLID_WINDOW
        seed = QRectF(logo.x() + x * logo.width(), logo.y() + y * logo.height(), w * logo.width(), h * logo.height())
        full = QRectF(self.rect())
        t = self._reveal
        rect = QRectF(
            seed.x() + (full.x() - seed.x()) * t,
            seed.y() + (full.y() - seed.y()) * t,
            seed.width() + (full.width() - seed.width()) * t,
            seed.height() + (full.height() - seed.height()) * t,
        )
        shape = QPainterPath()
        shape.addRoundedRect(rect, RADIUS, RADIUS)
        return shape

    def resizeEvent(self, event):
        width, height = self.width(), self.height()
        middle = height // 2
        self.message.setGeometry(0, middle - 34, width, 34)
        self.hint.setGeometry(0, middle + 4, width, 22)
        self.logo.move(EDGE, EDGE)
        self.orb.move(width - EDGE - Orb.SIZE, height - EDGE - Orb.SIZE)
        self.shutter.move((width - Shutter.SIZE) // 2, height - EDGE - Shutter.SIZE)
        self.panel.move(width - PANEL_GAP - self.panel.width(), height - PANEL_GAP - self.panel.height())
        room = self.panel.y() - PANEL_GAP - EDGE  # the bar stays clear of the panel, so it doesn't jump when that opens
        self.bar.setGeometry(width - EDGE - StrengthBar.WIDTH, EDGE, StrengthBar.WIDTH, max(min(room, BAR_LONGEST), 80))
        self._place_shutter()
        self._place_amount()
        self._rebuild()
        self.resized.emit()

    def _check_pointer(self):
        """Show the controls while the pointer is over the window, and fade them once it's gone.

        This looks at where the pointer really is. Windows doesn't always say when the
        pointer comes back, for example after a click on the render starts its drag loop.
        """
        inside = self.window().frameGeometry().contains(QCursor.pos())
        target = 1.0 if inside or self._image is None or self.panel.isVisible() else 0.0
        if target != self._chrome_target:
            self._chrome_target = target
            self._fade_to(target)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.show_panel(False)
            self.window().windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.maximise_clicked.emit()
