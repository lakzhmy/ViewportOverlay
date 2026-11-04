"""The main window: live render on top, dark settings underneath."""
from ctypes import wintypes

from PySide6.QtCore import QEvent, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QCursor, QIcon, QImage
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .controls import Grip, Scale, Segmented, Swatch, Toggle
from .engines import ENGINES, RenderParams
from .region import RegionFrame, RegionPicker
from .screen import (
    HTMAXBUTTON,
    WM_NCCALCSIZE,
    WM_NCHITTEST,
    WM_NCLBUTTONDOWN,
    WM_NCLBUTTONUP,
    enable_native_frame,
    exclude_from_capture,
    maximised_inset,
    style_native_window,
    to_physical,
)
from .stage import Stage
from .theme import ASSETS, GRAY_500, LIME, ORANGE, STYLE_SHEET, load_fonts
from .worker import RenderWorker

STYLES = [("Product", "Product render"), ("Clay", "Clay model"), ("Marker", "Marker sketch"), ("Studio", "Studio photo")]
GRIP = 6
CORNER = 14


def label(text: str, name: str) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(name)
    return widget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        load_fonts()
        self.setWindowTitle("ViewportOverlay")
        self.setWindowIcon(QIcon(str(ASSETS / "app-icon.ico")))
        self.setStyleSheet(STYLE_SHEET)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumSize(QSize(640, 560))  # small enough for a one-third snap tile
        self.resize(QSize(1040, 800))

        self.worker = None
        self.region_frame = RegionFrame()
        self.region_frame.changed.connect(self._region_moved)
        self.region_frame.dismissed.connect(self.clear_region)
        self.picker = RegionPicker()
        self.picker.picked.connect(self._region_picked)
        self.picker.cancelled.connect(self._picking_ended)

        self.engine_box = Segmented("engine", [(engine.label, engine) for engine in ENGINES], margin=3)
        self.engine_box.currentIndexChanged.connect(self._engine_changed)
        self.preview = Stage(self.engine_box)
        self.preview.minimise_clicked.connect(self.showMinimized)
        self.preview.maximise_clicked.connect(self._toggle_maximised)
        self.preview.close_clicked.connect(self.close)
        self.preview.resized.connect(self._place_seam)

        root = QWidget()
        root.setObjectName("root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.preview, 1)
        layout.addWidget(self._build_settings())
        self.setCentralWidget(root)
        self.seam = self._build_seam(root)
        self._grips = self._build_grips(root)
        self._engine_changed()
        self._hover_check = QTimer(self)
        self._hover_check.setInterval(80)
        self._hover_check.timeout.connect(self._check_maximise_hover)

    def _build_seam(self, parent) -> QFrame:
        seam = QFrame(parent)
        seam.setObjectName("seam")
        row = QHBoxLayout(seam)
        row.setContentsMargins(5, 5, 5, 5)
        row.setSpacing(2)
        self.select_button = QPushButton("Select region")
        self.select_button.setObjectName("primary")
        self.select_button.clicked.connect(self.select_region)
        self.run_button = QPushButton("Start")
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self.toggle_running)
        self.clear_button = QPushButton("Clear")
        self.clear_button.setEnabled(False)
        self.clear_button.clicked.connect(self.clear_region)
        for button in (self.select_button, self.run_button, self.clear_button):
            row.addWidget(button)
        return seam

    def _build_settings(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("settings")
        column = QVBoxLayout(panel)
        column.setContentsMargins(24, 40, 24, 14)
        column.setSpacing(14)

        self.prompt_box = QPlainTextEdit()
        self.prompt_box.setPlaceholderText("modern coffee machine, studio light")
        self.prompt_box.document().setDocumentMargin(0)
        self.prompt_box.textChanged.connect(self._params_changed)
        self.engine_note = label("", "note")
        self.engine_note.setWordWrap(True)
        describe = QVBoxLayout()
        describe.setSpacing(8)
        describe.addWidget(label("Describe it", "heading"))
        describe.addWidget(self.prompt_box, 1)
        describe.addWidget(self.engine_note)

        self.style_box = Segmented("style", STYLES, spacing=8, make=Swatch)
        self.style_box.currentIndexChanged.connect(self._params_changed)
        self.follow_value = label("", "value")
        self.follow_slider = Scale()
        self.follow_slider.setRange(0, 100)
        self.follow_slider.setValue(33)
        self.follow_slider.valueChanged.connect(self._params_changed)
        follow_title = QHBoxLayout()
        follow_title.addWidget(label("Follow my drawing", "heading"), 0, Qt.AlignmentFlag.AlignBottom)
        follow_title.addStretch()
        follow_title.addWidget(self.follow_value)
        ends = QHBoxLayout()
        ends.addWidget(label("Loose", "note"))
        ends.addStretch()
        ends.addWidget(label("Strict", "note"))
        tune = QVBoxLayout()
        tune.setSpacing(6)
        tune.addWidget(self.style_box, 0, Qt.AlignmentFlag.AlignLeft)
        tune.addSpacing(4)
        tune.addLayout(follow_title)
        tune.addWidget(self.follow_slider)
        tune.addLayout(ends)
        tune.addStretch()

        rule = QFrame()
        rule.setObjectName("rule")
        rule.setFixedWidth(1)
        columns = QHBoxLayout()
        columns.setSpacing(24)
        columns.addLayout(describe, 1)
        columns.addWidget(rule)
        columns.addLayout(tune)
        column.addLayout(columns)

        self.on_top = Toggle("Keep on top")
        self.on_top.setChecked(True)
        self.on_top.toggled.connect(self._set_on_top)
        self.hide_capture = Toggle("Hide from capture")
        self.hide_capture.setChecked(True)
        self.hide_capture.setToolTip(
            "On: this window stays out of renders, screenshots, recordings and screen sharing.\n"
            "Off: it can be shared, but keep it clear of the region or it will render itself."
        )
        self.hide_capture.toggled.connect(self._set_capture_hidden)
        self.status = label("Nothing selected yet", "status")
        self.status.setWordWrap(True)
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        footer = QHBoxLayout()
        footer.setSpacing(18)
        footer.addWidget(self.on_top)
        footer.addWidget(self.hide_capture)
        footer.addWidget(self.status, 1)
        column.addLayout(footer)
        self.follow_value.setText(str(self.follow_slider.value()))
        return panel

    def _build_grips(self, parent) -> dict:
        edge = Qt.Edge
        cursor = Qt.CursorShape
        return {
            "n": Grip(parent, edge.TopEdge, cursor.SizeVerCursor),
            "s": Grip(parent, edge.BottomEdge, cursor.SizeVerCursor),
            "w": Grip(parent, edge.LeftEdge, cursor.SizeHorCursor),
            "e": Grip(parent, edge.RightEdge, cursor.SizeHorCursor),
            "nw": Grip(parent, edge.TopEdge | edge.LeftEdge, cursor.SizeFDiagCursor),
            "se": Grip(parent, edge.BottomEdge | edge.RightEdge, cursor.SizeFDiagCursor),
            "ne": Grip(parent, edge.TopEdge | edge.RightEdge, cursor.SizeBDiagCursor),
            "sw": Grip(parent, edge.BottomEdge | edge.LeftEdge, cursor.SizeBDiagCursor),
        }

    def _place_seam(self):
        self.seam.adjustSize()
        x = (self.width() - self.seam.width()) // 2
        self.seam.move(x, self.preview.height() - self.seam.height() // 2)
        self.seam.raise_()

    def resizeEvent(self, event):
        w, h = self.width(), self.height()
        places = {
            "n": (CORNER, 0, w - 2 * CORNER, GRIP),
            "s": (CORNER, h - GRIP, w - 2 * CORNER, GRIP),
            "w": (0, CORNER, GRIP, h - 2 * CORNER),
            "e": (w - GRIP, CORNER, GRIP, h - 2 * CORNER),
            "nw": (0, 0, CORNER, CORNER),
            "ne": (w - CORNER, 0, CORNER, CORNER),
            "sw": (0, h - CORNER, CORNER, CORNER),
            "se": (w - CORNER, h - CORNER, CORNER, CORNER),
        }
        for name, grip in self._grips.items():
            grip.setGeometry(*places[name])
            grip.raise_()

    def showEvent(self, event):
        enable_native_frame(self)
        style_native_window(self)
        exclude_from_capture(self, self.hide_capture.isChecked())

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            maximised = self.isMaximized()
            self.preview.maximise_button.set_kind("restore" if maximised else "maximise")
            self.preview.maximise_button.setToolTip("Restore" if maximised else "Maximise")
            for grip in self._grips.values():
                grip.setVisible(not maximised)
        super().changeEvent(event)

    def nativeEvent(self, event_type, message):
        if bytes(event_type) != b"windows_generic_MSG":
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_NCCALCSIZE:
            # Claim the whole frame for drawing, which hides the title bar. A maximised
            # window hangs off the screen edges, so pull it back in.
            if self.isMaximized():
                inset = maximised_inset(int(msg.hWnd))
                rect = wintypes.RECT.from_address(msg.lParam)
                rect.left += inset
                rect.top += inset
                rect.right -= inset
                rect.bottom -= inset
            return True, 0
        if msg.message == WM_NCHITTEST and self._over_maximise():
            # Windows shows its snap layouts menu for whatever answers as the maximise button.
            self.preview.maximise_button.set_hot(True)
            self._hover_check.start()
            return True, HTMAXBUTTON
        if msg.message == WM_NCLBUTTONDOWN and msg.wParam == HTMAXBUTTON:
            return True, 0
        if msg.message == WM_NCLBUTTONUP and msg.wParam == HTMAXBUTTON:
            self._toggle_maximised()
            return True, 0
        return False, 0

    def _over_maximise(self) -> bool:
        button = self.preview.maximise_button
        return button.isVisible() and button.rect().contains(button.mapFromGlobal(QCursor.pos()))

    def _check_maximise_hover(self):
        if not self._over_maximise():
            self._hover_check.stop()
            self.preview.maximise_button.set_hot(False)
            self.preview.check_pointer()

    def _toggle_maximised(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def params(self) -> RenderParams:
        return RenderParams(
            prompt=self.prompt_box.toPlainText().strip(),
            style=self.style_box.currentData(),
            follow=self.follow_slider.value() / 100.0,
        )

    def select_region(self):
        self.region_frame.hide()
        self.select_button.setEnabled(False)
        self.picker.begin()

    def _picking_ended(self):
        self.select_button.setEnabled(True)
        if self.region_frame.area().isValid():
            self.region_frame.show()

    def _region_picked(self, area: QRect):
        self.select_button.setText("Reselect region")
        self.region_frame.set_area(area)
        self._picking_ended()
        self.run_button.setEnabled(True)
        self.clear_button.setEnabled(True)
        self._place_seam()
        if self.worker:
            self.worker.set_region(to_physical(area))
        else:
            self.start()

    def clear_region(self):
        self.stop()
        self.region_frame.clear()
        self.select_button.setText("Select region")
        self.run_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self.preview.clear()
        self.preview.live_card.hide()
        self.status.setText("Nothing selected yet")
        self._place_seam()

    def _region_moved(self, area: QRect):
        if self.worker:
            self.worker.set_region(to_physical(area))

    def _params_changed(self):
        self.follow_value.setText(str(self.follow_slider.value()))
        if self.worker:
            self.worker.set_params(self.params())

    def _engine_changed(self):
        engine = self.engine_box.currentData()
        self.engine_note.setVisible(not engine.uses_prompt)
        self.engine_note.setText("This stand-in ignores prompt and style. They'll work with an AI engine.")
        if self.worker:
            self.stop()
            self.start()

    def _set_on_top(self, on_top: bool):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on_top)
        self.show()

    def _set_capture_hidden(self, hidden: bool):
        exclude_from_capture(self, hidden)
        self.region_frame.set_capture_hidden(hidden)

    def toggle_running(self):
        if self.worker:
            self.stop()
        else:
            self.start()

    def start(self):
        area = self.region_frame.area()
        if not area.isValid():
            return
        engine = self.engine_box.currentData()()
        self.worker = RenderWorker(engine, to_physical(area), self.params())
        self.worker.frame_ready.connect(self._show_frame)
        self.worker.idle.connect(self._show_idle)
        self.worker.failed.connect(self._show_failure)
        self.worker.loading.connect(self._show_loading)
        self.worker.start()
        self.run_button.setText("Stop")
        self.preview.live_card.show()

    def stop(self):
        worker, self.worker = self.worker, None
        if worker:
            worker.frame_ready.disconnect(self._show_frame)
            worker.idle.disconnect(self._show_idle)
            worker.failed.disconnect(self._show_failure)
            worker.loading.disconnect(self._show_loading)
            worker.stop()
        self.run_button.setText("Start")
        self.status.setText("Stopped")
        self.preview.set_live(False)
        self.region_frame.set_live(False)
        self.preview.live_card.show_state("Stopped")
        self.preview.live_card.rate.setText("–")

    def _show_loading(self, message: str):
        self.status.setText(message)
        self.preview.set_waiting(message)
        self.preview.live_card.show_state("Loading", ORANGE)

    def _show_frame(self, image: QImage, fps: float):
        card = self.preview.live_card
        self.preview.show_image(image)
        self.preview.set_live(True)
        self.region_frame.set_live(True)
        card.show_state("Live", LIME)
        if fps:
            card.rate.setText(f"{fps:.0f} fps")
        card.size_label.setText(f"{image.width()} × {image.height()}")
        self.status.setText("Rendering")

    def _show_idle(self):
        self.preview.set_live(False)
        self.region_frame.set_live(False)
        self.preview.live_card.show_state("Paused", GRAY_500)
        self.status.setText("Paused until your screen changes")

    def _show_failure(self, message: str):
        self.stop()
        self.status.setText(f"Something went wrong: {message}")

    def closeEvent(self, event):
        self.stop()
        self.region_frame.close()
        event.accept()
