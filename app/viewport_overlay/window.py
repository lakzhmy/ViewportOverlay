"""The main window: a simple camera. Viewfinder on top, then the description and one line of options."""
import time
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QEvent, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QCursor, QIcon, QImage
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from .capture import copy_image, load_settings, save_image, save_settings
from .cloud import FinalRender, estimate_price, forget_key, grab_region, load_key, save_key
from .controls import Grip, LineButton
from .engines import RenderParams
from .region import RegionFrame, RegionPicker
from .screen import (
    CAPTURE_KEY_ID,
    CAPTURE_KEY_NAME,
    HTMAXBUTTON,
    WM_HOTKEY,
    WM_NCCALCSIZE,
    WM_NCHITTEST,
    WM_NCLBUTTONDOWN,
    WM_NCLBUTTONUP,
    claim_capture_key,
    enable_native_frame,
    exclude_from_capture,
    maximised_inset,
    release_capture_key,
    set_always_on_top,
    style_native_window,
    to_physical,
)
from .looks import LOOKS
from .stage import Stage
from .theme import ASSETS, STYLE_SHEET, load_fonts
from .worker import RenderWorker

GRIP = 6
CORNER = 14
NOTICE_MS = 3000
PROBLEM_MS = 8000
KEEP_LOADED_MS = 10 * 60 * 1000  # how long an AI model waits for a new region
WAIT_FOREVER_MS = 600000  # until the final arrives, fails or is cancelled
MARGIN = 18
STRIP = 30
FOOTER = 44
NO_FOLDER = "choose folder"
FILTER_NOTE = "The Filter look doesn't use a description."
CLOUD_NOTICE = (
    "Render final sends what's inside your region and your description to fal.ai, and on to OpenAI, "
    "to make the image. Each image costs money on your fal account.\n\n"
    "Only send work you're allowed to share with them. Send this one?"
)


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
        self.setMinimumSize(QSize(640, 600))  # narrow enough for a one-third snap tile
        self.resize(QSize(860, 950))

        self.worker = None
        self._key_window = 0
        self.capture_settings = load_settings()
        self._state_text = "Nothing selected yet"
        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.setInterval(NOTICE_MS)
        self._notice_timer.timeout.connect(lambda: self.status.setText(self._state_text))
        self.region_frame = RegionFrame()
        self.region_frame.changed.connect(self._region_moved)
        self.region_frame.dismissed.connect(self.clear_region)
        self.picker = RegionPicker()
        self.picker.picked.connect(self._region_picked)
        self.picker.cancelled.connect(self._picking_ended)

        self.preview = Stage()
        self.preview.minimise_clicked.connect(self.showMinimized)
        self.preview.maximise_clicked.connect(self._toggle_maximised)
        self.preview.close_clicked.connect(self.close)
        self.logo = self.preview.logo
        self.logo.clicked.connect(self._logo_clicked)
        self.capture_button = self.preview.shutter
        self.capture_button.setEnabled(False)
        self.capture_button.setToolTip(f"Capture this render ({CAPTURE_KEY_NAME})")
        self.capture_button.clicked.connect(self.capture)
        self.follow_slider = self.preview.bar
        self.follow_slider.setRange(0, 100)
        self.follow_slider.setValue(33)
        self.follow_slider.valueChanged.connect(self._params_changed)
        self.look_box = self.preview.panel.look_box
        self.look_box.currentIndexChanged.connect(self._look_changed)
        self._final = None
        self._final_started = 0
        self._holding = False
        self._parked = False  # no region, with the model kept loaded for the next one
        self._unload_timer = QTimer(self)
        self._unload_timer.setSingleShot(True)
        self._unload_timer.setInterval(KEEP_LOADED_MS)
        self._unload_timer.timeout.connect(self._unload)
        self._fal_key = load_key()
        self._final_clock = QTimer(self)
        self._final_clock.setInterval(1000)
        self._final_clock.timeout.connect(self._refresh_final)
        panel = self.preview.panel
        self.preview.final_pill.clicked.connect(self._final_clicked)
        panel.key_button.clicked.connect(self._key_clicked)
        panel.key_box.returnPressed.connect(self._key_clicked)
        panel.set_key_saved(bool(self._fal_key))
        panel.quality_buttons[self.capture_settings["quality"]].setChecked(True)
        for name, button in panel.quality_buttons.items():
            button.clicked.connect(lambda checked=False, name=name: self._quality_chosen(name))

        root = QWidget()
        root.setObjectName("root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(MARGIN, 0, MARGIN, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_strip())
        layout.addWidget(self.preview, 1)
        layout.addWidget(self._build_prompt())
        layout.addWidget(self._build_footer())
        self.setCentralWidget(root)
        self._grips = self._build_grips(root)
        self._engine = None
        self._rate = ""
        self._look_changed()
        self._hover_check = QTimer(self)
        self._hover_check.setInterval(80)
        self._hover_check.timeout.connect(self._check_maximise_hover)

    def _build_strip(self) -> QFrame:
        strip = QFrame()
        strip.setFixedHeight(STRIP)
        row = QHBoxLayout(strip)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        row.addStretch()
        row.addWidget(self.preview.minimise_button)
        row.addWidget(self.preview.maximise_button)
        row.addWidget(self.preview.close_button)
        return strip

    def _build_prompt(self) -> QFrame:
        self.prompt_box = QPlainTextEdit()
        self.prompt_box.setPlaceholderText("modern coffee machine, studio light")
        self.prompt_box.document().setDocumentMargin(0)
        self.prompt_box.setFixedHeight(62)
        self.prompt_box.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.prompt_box.textChanged.connect(self._params_changed)
        area = QFrame()
        column = QVBoxLayout(area)
        column.setContentsMargins(2, 14, 2, 0)
        column.setSpacing(6)
        column.addWidget(label("Describe it", "heading"))
        column.addWidget(self.prompt_box)
        return area

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setFixedHeight(FOOTER)
        self.on_top = LineButton("Keep on top")
        self.on_top.setChecked(True)
        self.on_top.toggled.connect(self._set_on_top)
        self.hide_capture = LineButton("Hide from capture")
        self.hide_capture.setChecked(True)
        self.hide_capture.setToolTip(
            "On: this window stays out of renders, screenshots, recordings and screen sharing.\n"
            "Off: it can be shared, but keep it clear of the region or it will render itself."
        )
        self.hide_capture.toggled.connect(self._set_capture_hidden)
        self.pause_button = LineButton("Pause")
        self.pause_button.setEnabled(False)
        self.pause_button.setToolTip("Hold this image and stop rendering. The model stays loaded, so it carries on at once.")
        self.pause_button.toggled.connect(self._pause_toggled)

        self.to_clipboard = LineButton("clipboard")
        self.to_clipboard.setChecked(self.capture_settings["to_clipboard"])
        self.to_clipboard.toggled.connect(self._capture_choice_changed)
        self.to_folder = LineButton("folder")
        self.to_folder.setChecked(self.capture_settings["to_folder"])
        self.to_folder.toggled.connect(self._capture_choice_changed)
        self.folder_button = LineButton(switch=False, shortest=70)
        self.folder_button.setEnabled(self.to_folder.isChecked())
        self.folder_button.clicked.connect(self._choose_folder)
        self._show_folder()
        save = QHBoxLayout()
        save.setSpacing(5)
        save.addWidget(QLabel("Save to:"))
        save.addWidget(self.to_clipboard)
        save.addWidget(QLabel(","))
        save.addWidget(self.to_folder)
        save.addWidget(self.folder_button)

        self.status = QLabel("Nothing selected yet")
        self.status.setWordWrap(True)
        self.status.setMinimumWidth(120)
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row = QHBoxLayout(footer)
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(16)
        row.addWidget(self.pause_button)
        row.addWidget(self.on_top)
        row.addWidget(self.hide_capture)
        row.addLayout(save)
        row.addWidget(self.status, 1)
        return footer

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
        set_always_on_top(self, self.on_top.isChecked())
        self._claim_capture_key()

    def _claim_capture_key(self):
        """Windows ties the shortcut to one window, so it has to follow if that window is ever rebuilt."""
        window = int(self.winId())
        if window == self._key_window:
            return
        if self._key_window:
            release_capture_key(self._key_window)
        claimed = claim_capture_key(window)
        self._key_window = window if claimed else 0
        if not claimed:
            self._notice(f"{CAPTURE_KEY_NAME} is taken by another app")

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
        if msg.message == WM_HOTKEY and msg.wParam == CAPTURE_KEY_ID:
            QTimer.singleShot(0, self.capture)  # it may open the folder picker, which can't happen in here
            return True, 0
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

    def _toggle_maximised(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def params(self) -> RenderParams:
        return RenderParams(
            prompt=self.prompt_box.toPlainText().strip(),
            style=self.look_box.currentData().style,
            follow=self.follow_slider.value() / 100.0,
            reference=self.look_box.currentData().reference,
        )

    def _say(self, text: str):
        """Sets the ongoing status. A capture notice stays up until its time is over."""
        self._state_text = text
        if not self._notice_timer.isActive():
            self.status.setText(text)

    def _notice(self, text: str, time_ms: int = NOTICE_MS):
        self.status.setText(text)
        self._notice_timer.start(time_ms)

    def _key_clicked(self):
        panel = self.preview.panel
        if self._fal_key:
            forget_key()
            self._fal_key = ""
        else:
            key = panel.key_box.text().strip()
            if not key:
                return
            try:
                save_key(key)
            except OSError:
                self._notice("Couldn't save the key", PROBLEM_MS)
                return
            self._fal_key = key
        panel.set_key_saved(bool(self._fal_key))
        self._refresh_final()

    def _quality_chosen(self, name: str):
        self.capture_settings["quality"] = name
        save_settings(self.capture_settings)
        self._refresh_final()

    def _refresh_final(self):
        area = self.region_frame.area()
        if self._final:
            text = f"Cancel · {round(time.monotonic() - self._final_started)} s"
        elif self._holding:
            text = "Back to live"
        elif area.isValid():
            region = to_physical(area)
            price = estimate_price(region["width"], region["height"], self.capture_settings["quality"])
            text = f"Render final · ~${price:.2f}"
        else:
            text = ""
        ready = bool(self._fal_key) and area.isValid()
        self.preview.set_final(text, bool(self._final) or self._holding or ready)

    def _final_clicked(self):
        if self._final:
            self._cancel_final()
        elif self._holding:
            self._leave_final()
        else:
            self.render_final()

    def _agreed_to_cloud(self) -> bool:
        if self.capture_settings["cloud_agreed"]:
            return True
        buttons = QMessageBox.StandardButton
        answer = QMessageBox.question(self, "Render final", CLOUD_NOTICE, buttons.Yes | buttons.Cancel, buttons.Cancel)
        if answer != buttons.Yes:
            return False
        self.capture_settings["cloud_agreed"] = True
        save_settings(self.capture_settings)
        return True

    def render_final(self):
        area = self.region_frame.area()
        if self._final or not self._fal_key or not area.isValid() or not self._agreed_to_cloud():
            return
        look = self.look_box.currentData()
        style = look.style if look.folder else LOOKS[0].style
        params = RenderParams(prompt=self.prompt_box.toPlainText().strip(), style=style)
        self._final = FinalRender(self._fal_key, grab_region(to_physical(area)), params, self.capture_settings["quality"])
        self._final.finished.connect(self._final_done)
        self._final.failed.connect(self._final_failed)
        self._final_started = time.monotonic()
        self._final_clock.start()
        self._final.start()
        self._notice("Rendering final…", WAIT_FOREVER_MS)
        self._refresh_final()

    def _end_final(self):
        job, self._final = self._final, None
        self._final_clock.stop()
        self._notice_timer.stop()
        job.finished.disconnect(self._final_done)
        job.failed.disconnect(self._final_failed)
        return job

    def _cancel_final(self):
        self._end_final().cancel()
        self._notice("Cancelled. It may still be charged if it had started", PROBLEM_MS)
        self._refresh_final()

    def _final_failed(self, message: str):
        self._end_final()
        self._notice(message, PROBLEM_MS)
        self._refresh_final()

    def _final_done(self, image: QImage):
        """Shows the final and holds it there. It paid for itself, so it's saved straight away."""
        self._end_final()
        self._holding = self.region_frame.area().isValid()
        self._apply_pause()
        self.preview.show_image(image)
        self.preview.set_live(False)
        self.region_frame.set_live(False)
        self._refresh_capture()
        self._refresh_final()
        self._say(f"Final · {image.width()} × {image.height()}")
        if self.capture_button.isEnabled():
            self.capture()

    def _leave_final(self):
        self._holding = False
        if self.worker:
            self._apply_pause()
        elif self.region_frame.area().isValid():
            self.start()
        self._refresh_final()

    def _quiet(self) -> bool:
        return self._holding or self._parked or self.pause_button.isChecked()

    def _apply_pause(self):
        if self.worker:
            self.worker.set_paused(self._quiet())

    def _pause_toggled(self, paused: bool):
        self._apply_pause()
        if paused:
            self.preview.set_live(False)
            self.region_frame.set_live(False)
            self._say("Paused")
        elif not self._holding and self.region_frame.area().isValid():
            self._say("Carrying on")

    def _unload(self):
        self.stop()
        self._say("Nothing selected yet")

    def _show_folder(self):
        folder = self.capture_settings["folder"]
        self.folder_button.set_text(folder or NO_FOLDER)
        self.folder_button.setToolTip(folder or "Pick where captures are saved")

    def _capture_choice_changed(self):
        self.capture_settings["to_folder"] = self.to_folder.isChecked()
        self.capture_settings["to_clipboard"] = self.to_clipboard.isChecked()
        self.folder_button.setEnabled(self.to_folder.isChecked())
        save_settings(self.capture_settings)
        self._refresh_capture()

    def _refresh_capture(self):
        wanted = self.to_folder.isChecked() or self.to_clipboard.isChecked()
        self.capture_button.setEnabled(wanted and self.preview.current_image() is not None)

    def _choose_folder(self) -> bool:
        folder = QFileDialog.getExistingDirectory(self, "Choose where captures are saved", self.capture_settings["folder"])
        if folder:
            self.capture_settings["folder"] = str(Path(folder))
            save_settings(self.capture_settings)
            self._show_folder()
        return bool(folder)

    def capture(self):
        image = self.preview.current_image()  # taken first, so this is the frame that was on screen at the click
        if not self.capture_button.isEnabled():  # the shortcut can arrive at any moment
            self._notice("Nothing to capture yet" if image is None else "Turn on clipboard or folder first")
            return
        wants_file = self.to_folder.isChecked()
        has_folder = wants_file and (bool(self.capture_settings["folder"]) or self._choose_folder())
        saved = save_image(image, Path(self.capture_settings["folder"])) if has_folder else None
        copied = self.to_clipboard.isChecked()
        if copied:
            copy_image(image)
        if saved or copied:
            self.preview.flash()
        if saved and copied:
            self._notice("Saved and copied")
        elif saved:
            self._notice(f"Saved to {saved.parent.name or saved.parent}")
        elif not wants_file:
            self._notice("Copied to clipboard")
        else:
            reason = "can't write to that folder" if has_folder else "no folder chosen"
            self._notice(f"{'Copied, but not saved' if copied else 'Not saved'}: {reason}")

    def mousePressEvent(self, event):
        """The paper frame and the bottom line drag the window, like the render does."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.preview.show_panel(False)
            self.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximised()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.preview.show_panel(False)
        else:
            super().keyPressEvent(event)

    def _logo_clicked(self):
        if self.region_frame.area().isValid():
            self.clear_region()
        else:
            self.select_region()

    def select_region(self):
        self.preview.show_panel(False)
        self.region_frame.hide()
        self.logo.setEnabled(False)
        self.picker.begin()

    def _picking_ended(self):
        self.logo.setEnabled(True)
        if self.region_frame.area().isValid():
            self.region_frame.show()

    def _region_picked(self, area: QRect):
        self.region_frame.set_area(area)
        self._picking_ended()
        self.logo.set_on(True)
        self._parked = False
        self._unload_timer.stop()
        self.pause_button.setEnabled(True)
        self.pause_button.setChecked(False)
        if self.worker:
            self.worker.set_region(to_physical(area))
        else:
            self.start()
        self._leave_final()

    def clear_region(self):
        """Drops the region. The last render stays up, so it can still be captured.

        A slow AI model stays loaded for a while, so selecting a new region starts at once.
        """
        self._holding = False
        self.pause_button.setChecked(False)
        self.pause_button.setEnabled(False)
        if self.worker and self.worker.keeps_loaded():
            self._parked = True
            self._apply_pause()
            self._unload_timer.start()
            self.preview.set_live(False)
            self.region_frame.set_live(False)
        else:
            self.stop()
        self.region_frame.clear()
        self.logo.set_on(False)
        self.preview.show_start()
        self._say("Nothing selected yet")
        self._holding = False
        self._refresh_final()

    def _region_moved(self, area: QRect):
        if self.worker:
            self.worker.set_region(to_physical(area))
        self._refresh_final()

    def _params_changed(self):
        if self.worker:
            self.worker.set_params(self.params())

    def _look_changed(self):
        look = self.look_box.currentData()
        self.preview.orb.set_colors(look.colors)
        self.prompt_box.setEnabled(look.engine.uses_prompt)
        self.prompt_box.setToolTip("" if look.engine.uses_prompt else FILTER_NOTE)
        if look.engine is self._engine:
            self._params_changed()
            return
        self._engine = look.engine
        if self.region_frame.area().isValid():
            self.stop()
            self.start()
        elif self._parked:
            self._unload()  # the waiting model no longer matches the look

    def _set_on_top(self, on_top: bool):
        set_always_on_top(self, on_top)

    def _set_capture_hidden(self, hidden: bool):
        exclude_from_capture(self, hidden)
        self.region_frame.set_capture_hidden(hidden)

    def start(self):
        area = self.region_frame.area()
        if not area.isValid():
            return
        self.worker = RenderWorker(self._engine(), to_physical(area), self.params())
        self.worker.frame_ready.connect(self._show_frame)
        self.worker.idle.connect(self._show_idle)
        self.worker.failed.connect(self._show_failure)
        self.worker.loading.connect(self._show_loading)
        self.worker.waiting.connect(self._show_waiting)
        self._apply_pause()
        self.worker.start()

    def stop(self):
        self._parked = False
        self._unload_timer.stop()
        worker, self.worker = self.worker, None
        if worker:
            worker.frame_ready.disconnect(self._show_frame)
            worker.idle.disconnect(self._show_idle)
            worker.failed.disconnect(self._show_failure)
            worker.loading.disconnect(self._show_loading)
            worker.waiting.disconnect(self._show_waiting)
            worker.stop()
        self._say("Stopped")
        self.preview.set_live(False)
        self.region_frame.set_live(False)

    def _show_loading(self, message: str):
        if self._parked:
            return
        self._say(message)
        self.preview.set_waiting(message)

    def _show_frame(self, image: QImage, fps: float):
        if self._quiet():  # a frame that was already on its way
            return
        self.preview.show_image(image)
        self._refresh_capture()
        self.preview.set_live(True)
        self.region_frame.set_live(True)
        if fps:
            self._rate = f"{fps:.0f} fps · "
        self._say(f"Live · {self._rate}{image.width()} × {image.height()}")

    def _show_waiting(self):
        if not self._quiet():
            self._say("Renders when you stop moving")

    def _show_idle(self):
        if self._quiet():
            return
        self.preview.set_live(False)
        self.region_frame.set_live(False)
        self._say("Paused until your screen changes")

    def _show_failure(self, message: str):
        self.stop()
        self._notice_timer.stop()
        self._say(f"Something went wrong: {message}")

    def closeEvent(self, event):
        if self._final:
            self._end_final().cancel()
        self.stop()
        self.region_frame.close()
        if self._key_window:
            release_capture_key(self._key_window)
            self._key_window = 0
        event.accept()
