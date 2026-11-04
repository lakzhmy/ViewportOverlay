"""The main window: live render on top, dark settings underneath."""
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QIcon, QImage
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .controls import Grip, Segmented
from .engines import ENGINES, RenderParams
from .region import RegionFrame, RegionPicker
from .screen import exclude_from_capture, style_native_window, to_physical
from .stage import Stage
from .theme import ASSETS, GRAY_500, LIME, ORANGE, STYLE_SHEET, load_fonts
from .worker import RenderWorker

STYLES = ["Product render", "Clay model", "Marker sketch", "Studio photo"]
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
        self.setMinimumSize(QSize(920, 640))
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
        column.setContentsMargins(16, 38, 16, 12)
        column.setSpacing(10)

        self.prompt_box = QPlainTextEdit()
        self.prompt_box.setPlaceholderText("Describe the render, e.g. modern coffee machine, studio light")
        self.prompt_box.setFixedHeight(92)
        self.prompt_box.textChanged.connect(self._params_changed)
        self.engine_note = label("", "note")
        self.engine_note.setWordWrap(True)
        prompt_card = QFrame()
        prompt_card.setObjectName("card")
        prompt_column = QVBoxLayout(prompt_card)
        prompt_column.setContentsMargins(14, 12, 14, 12)
        prompt_column.setSpacing(8)
        prompt_column.addWidget(label("Prompt", "heading"))
        prompt_column.addWidget(self.prompt_box)
        prompt_column.addWidget(self.engine_note)
        prompt_column.addStretch()

        self.style_box = Segmented("style", [(style, style) for style in STYLES], spacing=6)
        self.style_box.currentIndexChanged.connect(self._params_changed)
        self.follow_value = label("", "value")
        self.follow_slider = QSlider(Qt.Orientation.Horizontal)
        self.follow_slider.setRange(0, 100)
        self.follow_slider.setValue(33)
        self.follow_slider.valueChanged.connect(self._params_changed)
        follow_title = QHBoxLayout()
        follow_title.addWidget(label("Follow my drawing", "heading"))
        follow_title.addStretch()
        follow_title.addWidget(self.follow_value)
        ends = QHBoxLayout()
        ends.addWidget(label("Loose", "note"))
        ends.addStretch()
        ends.addWidget(label("Strict", "note"))
        controls_card = QFrame()
        controls_card.setObjectName("card")
        controls_column = QVBoxLayout(controls_card)
        controls_column.setContentsMargins(14, 12, 14, 12)
        controls_column.setSpacing(8)
        controls_column.addWidget(label("Style", "heading"))
        controls_column.addWidget(self.style_box)
        controls_column.addSpacing(6)
        controls_column.addLayout(follow_title)
        controls_column.addWidget(self.follow_slider)
        controls_column.addLayout(ends)
        controls_column.addStretch()

        cards = QHBoxLayout()
        cards.setSpacing(12)
        cards.addWidget(prompt_card, 1)
        cards.addWidget(controls_card, 1)
        column.addLayout(cards)

        self.on_top = QCheckBox("Keep on top")
        self.on_top.setChecked(True)
        self.on_top.toggled.connect(self._set_on_top)
        self.hide_capture = QCheckBox("Hide from capture")
        self.hide_capture.setChecked(True)
        self.hide_capture.setToolTip(
            "On: this window stays out of renders, screenshots, recordings and screen sharing.\n"
            "Off: it can be shared, but keep it clear of the region or it will render itself."
        )
        self.hide_capture.toggled.connect(self._set_capture_hidden)
        self.status = label("Ready", "status")
        self.status.setWordWrap(True)
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        footer = QHBoxLayout()
        footer.setSpacing(18)
        footer.addWidget(self.on_top)
        footer.addWidget(self.hide_capture)
        footer.addWidget(self.status, 1)
        column.addLayout(footer)
        self.follow_value.setText(f"{self.follow_slider.value()}%")
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
        style_native_window(self)
        exclude_from_capture(self, self.hide_capture.isChecked())

    def params(self) -> RenderParams:
        return RenderParams(
            prompt=self.prompt_box.toPlainText().strip(),
            style=self.style_box.currentText(),
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
        self.preview.clear("Select a region to get started")
        self.preview.live_card.hide()
        self.status.setText("Ready")
        self._place_seam()

    def _region_moved(self, area: QRect):
        if self.worker:
            self.worker.set_region(to_physical(area))

    def _params_changed(self):
        self.follow_value.setText(f"{self.follow_slider.value()}%")
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
        self.preview.live_card.show_state("Stopped")
        self.preview.live_card.rate.setText("–")

    def _show_loading(self, message: str):
        self.status.setText(message)
        self.preview.live_card.show_state("Loading", ORANGE)

    def _show_frame(self, image: QImage, fps: float):
        card = self.preview.live_card
        self.preview.show_image(image)
        self.preview.set_live(True)
        card.show_state("Live", LIME)
        if fps:
            card.rate.setText(f"{fps:.0f} fps")
        card.size_label.setText(f"{image.width()} × {image.height()}")
        self.status.setText("Rendering")

    def _show_idle(self):
        self.preview.set_live(False)
        self.preview.live_card.show_state("Paused", GRAY_500)
        self.status.setText("Screen unchanged, waiting")

    def _show_failure(self, message: str):
        self.stop()
        self.status.setText(f"Something went wrong: {message}")

    def closeEvent(self, event):
        self.stop()
        self.region_frame.close()
        event.accept()
