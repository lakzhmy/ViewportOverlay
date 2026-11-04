"""The floating output window with its live controls."""
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .engines import ENGINES, RenderParams
from .region import RegionFrame, RegionPicker
from .screen import exclude_from_capture, to_physical
from .worker import RenderWorker

STYLES = ["Product render", "Clay model", "Marker sketch", "Studio photo"]

STYLE_SHEET = """
QMainWindow, QWidget#panel { background: #17181C; }
QLabel { color: #E8E8EC; font: 10pt "Segoe UI"; }
QLabel#heading { color: #9A9CA6; font: 600 8.5pt "Segoe UI"; }
QLabel#note { color: #9A9CA6; font: 9pt "Segoe UI"; }
QLabel#status { color: #9A9CA6; font: 9pt "Segoe UI"; }
QPlainTextEdit, QComboBox {
    background: #23252B; color: #E8E8EC; border: 1px solid #34363E;
    border-radius: 6px; padding: 6px; font: 10pt "Segoe UI";
}
QPlainTextEdit:focus, QComboBox:focus { border-color: #FFB020; }
QComboBox QAbstractItemView { background: #23252B; color: #E8E8EC; selection-background-color: #34363E; }
QPushButton {
    background: #2B2D34; color: #E8E8EC; border: none; border-radius: 6px;
    padding: 9px 12px; font: 600 10pt "Segoe UI";
}
QPushButton:hover { background: #363842; }
QPushButton:disabled { color: #6A6C75; background: #212227; }
QPushButton#primary { background: #FFB020; color: #1B1B1F; }
QPushButton#primary:hover { background: #FFC24D; }
QPushButton#primary:disabled { background: #4A3D22; color: #8B7A52; }
QCheckBox { color: #E8E8EC; font: 10pt "Segoe UI"; spacing: 8px; }
QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px; background: #23252B; border: 1px solid #4A4C55; }
QCheckBox::indicator:checked { background: #FFB020; border-color: #FFB020; }
QSlider::groove:horizontal { height: 4px; background: #34363E; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #FFB020; border-radius: 2px; }
QSlider::handle:horizontal { background: #E8E8EC; width: 14px; margin: -5px 0; border-radius: 7px; }
"""


class Preview(QWidget):
    """Shows the latest image scaled to fit, keeping its proportions."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(360, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._image = None
        self.message = "Select a region to get started"

    def show_image(self, image: QImage):
        self._image = image
        self.update()

    def clear(self, message: str):
        self._image = None
        self.message = message
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0E0F12"))
        if self._image is None:
            painter.setPen(QColor("#9A9CA6"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        size = self._image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRect(0, 0, size.width(), size.height())
        target.moveCenter(self.rect().center())
        painter.drawImage(target, self._image)


def heading(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("heading")
    return label


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Viewport Overlay")
        self.setStyleSheet(STYLE_SHEET)
        self.resize(QSize(980, 640))
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)

        self.worker = None
        self.region_frame = RegionFrame()
        self.region_frame.changed.connect(self._region_moved)
        self.region_frame.dismissed.connect(self.clear_region)
        self.picker = RegionPicker()
        self.picker.picked.connect(self._region_picked)
        self.picker.cancelled.connect(self._picking_ended)

        self.preview = Preview()
        panel = self._build_panel()

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.preview, 1)
        layout.addWidget(panel)
        self.setCentralWidget(root)
        self._engine_changed()

    def _build_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("panel")
        panel.setFixedWidth(300)
        column = QVBoxLayout(panel)
        column.setContentsMargins(16, 16, 16, 16)
        column.setSpacing(8)

        self.select_button = QPushButton("Select region")
        self.select_button.setObjectName("primary")
        self.select_button.clicked.connect(self.select_region)
        self.run_button = QPushButton("Start")
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self.toggle_running)
        buttons = QHBoxLayout()
        buttons.addWidget(self.select_button, 1)
        buttons.addWidget(self.run_button, 1)
        column.addLayout(buttons)
        self.clear_button = QPushButton("Clear region")
        self.clear_button.setEnabled(False)
        self.clear_button.clicked.connect(self.clear_region)
        column.addWidget(self.clear_button)
        column.addSpacing(10)

        self.engine_box = QComboBox()
        for engine in ENGINES:
            self.engine_box.addItem(engine.name, engine)
        self.engine_box.currentIndexChanged.connect(self._engine_changed)
        column.addWidget(heading("Engine"))
        column.addWidget(self.engine_box)
        column.addSpacing(10)

        self.prompt_box = QPlainTextEdit()
        self.prompt_box.setPlaceholderText("Describe the render, e.g. modern coffee machine, studio light")
        self.prompt_box.setFixedHeight(92)
        self.prompt_box.textChanged.connect(self._params_changed)
        column.addWidget(heading("Prompt"))
        column.addWidget(self.prompt_box)

        self.style_box = QComboBox()
        self.style_box.addItems(STYLES)
        self.style_box.currentIndexChanged.connect(self._params_changed)
        column.addWidget(heading("Style"))
        column.addWidget(self.style_box)

        self.engine_note = QLabel()
        self.engine_note.setObjectName("note")
        self.engine_note.setWordWrap(True)
        column.addWidget(self.engine_note)
        column.addSpacing(10)

        self.follow_value = QLabel()
        title_row = QHBoxLayout()
        title_row.addWidget(heading("Follow my drawing"))
        title_row.addStretch()
        title_row.addWidget(self.follow_value)
        self.follow_slider = QSlider(Qt.Orientation.Horizontal)
        self.follow_slider.setRange(0, 100)
        self.follow_slider.setValue(33)
        self.follow_slider.valueChanged.connect(self._params_changed)
        column.addLayout(title_row)
        column.addWidget(self.follow_slider)
        ends = QHBoxLayout()
        for text, align in (("Loose", Qt.AlignmentFlag.AlignLeft), ("Strict", Qt.AlignmentFlag.AlignRight)):
            end = QLabel(text)
            end.setObjectName("note")
            end.setAlignment(align)
            ends.addWidget(end)
        column.addLayout(ends)
        column.addSpacing(6)

        self.on_top = QCheckBox("Keep this window on top")
        self.on_top.setChecked(True)
        self.on_top.toggled.connect(self._set_on_top)
        column.addWidget(self.on_top)
        column.addStretch()

        self.status = QLabel("Ready")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        column.addWidget(self.status)
        self.follow_value.setText(f"{self.follow_slider.value()}%")
        return panel

    def showEvent(self, event):
        exclude_from_capture(self)

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
        self.status.setText("Ready")

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
        self.worker.loading.connect(self.status.setText)
        self.worker.start()
        self.run_button.setText("Stop")

    def stop(self):
        worker, self.worker = self.worker, None
        if worker:
            worker.frame_ready.disconnect(self._show_frame)
            worker.idle.disconnect(self._show_idle)
            worker.failed.disconnect(self._show_failure)
            worker.loading.disconnect(self.status.setText)
            worker.stop()
        self.run_button.setText("Start")
        self.status.setText("Stopped")

    def _show_frame(self, image: QImage, fps: float):
        self.preview.show_image(image)
        rate = f"{fps:.0f} fps  ·  " if fps else ""
        self.status.setText(f"{rate}{image.width()} × {image.height()}")

    def _show_idle(self):
        self.status.setText("Screen unchanged, waiting")

    def _show_failure(self, message: str):
        self.stop()
        self.status.setText(f"Something went wrong: {message}")

    def closeEvent(self, event):
        self.stop()
        self.region_frame.close()
        event.accept()
