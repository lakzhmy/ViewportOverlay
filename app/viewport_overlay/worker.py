"""Background loop: capture the region, send it to the engine, return the image."""
import threading
import time

import mss
import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from .engines import Engine, RenderParams

TARGET_FPS = 30
SETTLE_CHECKS_PER_SECOND = 10
CHANGE_THRESHOLD = 0.4  # average brightness change, out of 255


def to_qimage(rgb: np.ndarray) -> QImage:
    height, width, _ = rgb.shape
    return QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()


def has_changed(previous, current) -> bool:
    if previous is None or previous.shape != current.shape:
        return True
    a = previous[::6, ::6].astype(np.int16)
    b = current[::6, ::6].astype(np.int16)
    return float(np.abs(a - b).mean()) > CHANGE_THRESHOLD


class RenderWorker(QThread):
    frame_ready = Signal(QImage, float)
    idle = Signal()
    failed = Signal(str)
    loading = Signal(str)
    waiting = Signal()

    def __init__(self, engine: Engine, region: dict, params: RenderParams):
        super().__init__()
        self._engine = engine
        self._region = region
        self._params = params
        self._dirty = True
        self._lock = threading.Lock()
        self._running = True
        self._paused = False

    def keeps_loaded(self) -> bool:
        return self._engine.slow_to_load

    def set_paused(self, paused: bool) -> None:
        """Holds rendering with the model still loaded, so going back to live is instant."""
        with self._lock:
            self._paused = paused
            self._dirty = True

    def set_region(self, region: dict) -> None:
        with self._lock:
            self._region = region
            self._dirty = True

    def set_params(self, params: RenderParams) -> None:
        with self._lock:
            self._params = params
            self._dirty = True

    def stop(self) -> None:
        self._running = False
        self._engine.abort()
        self.wait()

    def run(self) -> None:
        previous = None
        seen = None
        pending = False
        last_moved = 0.0
        last_done = None
        was_idle = False
        was_waiting = False
        settle = self._engine.settle_seconds
        interval = 1.0 / (SETTLE_CHECKS_PER_SECOND if settle else TARGET_FPS)
        try:
            self.loading.emit(f"Loading {self._engine.name}…")
            self._engine.start()
            with mss.MSS() as capture:
                while self._running:
                    started = time.perf_counter()
                    with self._lock:
                        paused = self._paused
                        region, params, dirty = self._region, self._params, self._dirty
                        if not paused:
                            self._dirty = False

                    if paused:
                        time.sleep(1.0 / TARGET_FPS)
                        continue

                    shot = capture.grab(region)
                    bgra = np.frombuffer(shot.bgra, np.uint8).reshape(shot.height, shot.width, 4)
                    frame = np.ascontiguousarray(bgra[:, :, 2::-1])

                    if dirty or has_changed(seen, frame):
                        last_moved = time.perf_counter()
                    seen = frame
                    pending = pending or dirty or has_changed(previous, frame)

                    if pending and time.perf_counter() - last_moved >= settle:
                        pending = False
                        was_waiting = False
                        previous = frame
                        image = to_qimage(self._engine.render(frame, params))
                        now = time.perf_counter()
                        fps = 1.0 / (now - last_done) if last_done and not was_idle else 0.0
                        last_done = now
                        was_idle = False
                        self.frame_ready.emit(image, fps)
                    elif pending:
                        if not was_waiting:
                            was_waiting = True
                            self.waiting.emit()
                    elif not was_idle:
                        was_idle = True
                        self.idle.emit()

                    spare = interval - (time.perf_counter() - started)
                    if spare > 0:
                        time.sleep(spare)
        except Exception as error:  # shown in the window, so a failure is never silent
            if self._running:
                self.failed.emit(str(error) or type(error).__name__)
        finally:
            self._engine.stop()
