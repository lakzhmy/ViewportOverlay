"""End-to-end test of klein: speed, tall shapes, and how much the design moves when the input moves a little.

Arguments: output folder, then a tall input image. Nothing leaves this PC.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from viewport_overlay.engines import LocalKleinEngine, RenderParams
from viewport_overlay.looks import LOOKS
from viewport_overlay.window import MainWindow

OUT = Path(sys.argv[1])
SAMPLE = sys.argv[2]
app = QApplication([])
results = []


def check(name, passed, detail=""):
    results.append(bool(passed))
    print(("PASS " if passed else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.003)


def wait_for(condition, seconds):
    end = time.time() + seconds
    while time.time() < end and not condition():
        pump(0.05)
    return condition()


def to_array(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    width, height, line = image.width(), image.height(), image.bytesPerLine()
    return np.frombuffer(image.constBits(), np.uint8).reshape(height, line)[:, : width * 3].reshape(height, width, 3).copy()


def to_image(rgb: np.ndarray) -> QImage:
    height, width, _ = rgb.shape
    data = np.ascontiguousarray(rgb)
    return QImage(data.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()


def difference(first, second):
    return float(np.abs(first.astype(int) - second).mean())


def shifted(frame, pixels):
    """The same picture moved sideways, with the edge filled in, like nudging a CAD view."""
    moved = np.roll(frame, pixels, axis=1)
    moved[:, :pixels] = frame[:, :1]
    return moved


class Viewport(QWidget):
    """Stands in for a CAD window showing the sample."""

    def __init__(self, rect, image):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setGeometry(rect)
        self.image = image
        self.shift = 0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.white)
        painter.drawImage(self.rect().translated(self.shift, 0), self.image)


sample = QImage(SAMPLE)
frame = to_array(sample.scaledToHeight(900, Qt.TransformationMode.SmoothTransformation))
look = LOOKS[2]
params = RenderParams(style=look.style, reference=look.reference)
check("the look has its reference image", bool(look.reference), look.reference)

engine = LocalKleinEngine()
started = time.perf_counter()
engine.start()
print(f"load time: {time.perf_counter() - started:.1f} s", flush=True)
started = time.perf_counter()
first = engine.render(frame, params)
print(f"first image: {time.perf_counter() - started:.1f} s, {first.shape[1]} x {first.shape[0]}", flush=True)
times = []
for _ in range(4):
    started = time.perf_counter()
    again = engine.render(frame, params)
    times.append(time.perf_counter() - started)
print(f"next images: {min(times):.2f} s best, {max(times):.2f} s worst", flush=True)
check("the shape stays tall", first.shape[0] / first.shape[1] > 1.6, str(first.shape))
check("same input gives the same image", difference(first, again) < 1.0, f"{difference(first, again):.2f}")

strip = [first]
for pixels in (1, 2, 4, 8, 16, 32):
    result = engine.render(shifted(frame, pixels), params)
    strip.append(result)
    print(f"stability: {pixels:>2} px nudge changes the image by {difference(first, result):.1f} / 255", flush=True)
canvas = np.full((first.shape[0], sum(s.shape[1] + 8 for s in strip), 3), 255, np.uint8)
x = 0
for picture in strip:
    canvas[: picture.shape[0], x: x + picture.shape[1]] = picture
    x += picture.shape[1] + 8
to_image(canvas).save(str(OUT / "stability strip.png"))

started = time.perf_counter()
engine.render(frame, RenderParams(prompt="brushed aluminium body", style=look.style, reference=look.reference))
print(f"new description: {time.perf_counter() - started:.2f} s", flush=True)
check("it works without a reference", engine.render(frame, RenderParams(style=look.style)).shape[2] == 3)
engine.stop()

# Full app: a stand-in viewport, captured and rendered.
screen = QGuiApplication.primaryScreen().geometry()
area = QRect(screen.left() + 100, screen.top() + 100, 400, 900)
viewport = Viewport(area, sample)
viewport.show()
window = MainWindow()
window.look_box.setCurrentIndex(2)
window.move(screen.left() + 900, screen.top() + 60)
window.show()
frames = []
window._region_picked(area)
window.worker.frame_ready.connect(lambda image, fps: frames.append(image))
pump(0.3)
check("window says it is loading", "Loading" in window.status.text(), window.status.text())
check("a klein frame arrives in the app", wait_for(lambda: bool(frames), 120), f"{len(frames)} frames")
window.grab().save(str(OUT / "klein app.png"))
pump(3.0)
count = len(frames)
pump(3.0)
check("a still screen stops rendering", len(frames) - count <= 1, f"{len(frames) - count} frames in 3 s")

count = len(frames)
started = time.time()
step = 0
while time.time() - started < 10:
    step += 1
    viewport.shift = int(12 * np.sin(step / 40))
    viewport.update()
    pump(0.02)
rate = (len(frames) - count) / 10
print(f"live speed through the whole app: {rate:.2f} images a second", flush=True)
check("the app keeps up while the view moves", rate >= 0.5, f"{rate:.2f}")

process = window.worker._engine._process
window.stop()
check("stop ends the AI program", process.poll() is not None)
window.close()
viewport.close()
print("ALL PASSED" if all(results) else "SOME FAILED", flush=True)
sys.exit(0 if all(results) else 1)
