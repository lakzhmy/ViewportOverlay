"""End-to-end test: a real on-screen drawing, captured and rendered by SD-Turbo."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPolygon
from PySide6.QtWidgets import QApplication, QWidget

from viewport_overlay.engines import LocalTurboEngine, RenderParams
from viewport_overlay.window import MainWindow

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
PROMPT = "modern coffee machine, brushed metal body, glass panel, soft edge lighting"
app = QApplication([])
results = []


def check(name, passed, detail=""):
    results.append(passed)
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


class Drawing(QWidget):
    """A stand-in for a Rhino viewport, with a shape that can move."""

    def __init__(self, rect):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setGeometry(rect)
        self.shift = 0

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(225, 225, 228))
        p.setPen(Qt.PenStyle.NoPen)
        x = self.width() // 2 - 100 + self.shift
        p.setBrush(QColor(150, 150, 156))
        p.drawRoundedRect(x + 10, 30, 180, 60, 18, 18)
        p.setBrush(QColor(95, 96, 104))
        p.drawRoundedRect(x, 94, 200, 226, 14, 14)
        p.setBrush(QColor(35, 38, 48))
        p.drawRoundedRect(x + 20, 112, 160, 188, 8, 8)
        p.setBrush(QColor(120, 121, 128))
        p.drawPolygon(QPolygon([QPoint(x - 10, 324), QPoint(x + 210, 324), QPoint(x + 230, 376), QPoint(x - 30, 376)]))
        p.setBrush(QColor(80, 81, 88))
        p.drawRect(x - 6, 380, 212, 100)


# Engine on its own: repeatability and small-change stability.
frame = np.full((400, 700, 3), 225, np.uint8)
frame[100:300, 280:420] = 90
engine = LocalTurboEngine()
started = time.perf_counter()
engine.start()
print(f"load time: {time.perf_counter() - started:.1f} s", flush=True)
params = RenderParams(prompt=PROMPT, style="Product render")
first = engine.render(frame, params)
second = engine.render(frame, params)
check("non-square region keeps its shape", first.shape[1] / first.shape[0] > 1.7, str(first.shape))
check("same input gives same output", float(np.abs(first.astype(int) - second).mean()) < 1.0)

nudged = np.roll(frame, 2, axis=1)
small = float(np.abs(engine.render(nudged, params).astype(int) - first).mean())
print(f"flicker measure: {small:.1f} / 255 average change for a 2 pixel nudge", flush=True)

started = time.perf_counter()
engine.render(frame, RenderParams(prompt="red sports car", style="Product render"))
print(f"prompt change frame: {(time.perf_counter() - started) * 1000:.0f} ms", flush=True)
started = time.perf_counter()
changed = engine.render(frame, RenderParams(prompt="red sports car", style="Product render", follow=0.9))
print(f"slider change frame: {(time.perf_counter() - started) * 1000:.0f} ms", flush=True)
check("slider change gives a valid image", changed.shape == first.shape)
engine.stop()

# Full app: draw, capture, render.
screen = QGuiApplication.primaryScreen().geometry()
area = QRect(screen.left() + 120, screen.top() + 140, 512, 512)
drawing = Drawing(area)
drawing.show()
window = MainWindow()
window.look_box.setCurrentIndex(3)  # the Fast look runs SD-Turbo
window.move(screen.left() + 700, screen.top() + 100)
window.prompt_box.setPlainText(PROMPT)
window.show()
frames = []
window._region_picked(area)
window.worker.frame_ready.connect(lambda image, fps: frames.append(image))
pump(0.3)
check("window says it is loading", "Loading" in window.status.text(), window.status.text())
check("AI frame arrives in the app", wait_for(lambda: bool(frames), 90), f"{len(frames)} frames")
frames[-1].save(str(OUT / "app_frame.png"))

pump(1.0)
count = len(frames)
pump(1.0)
check("still screen stops rendering", len(frames) - count <= 2, f"{len(frames) - count} frames in 1s")

# Move the drawing continuously, like working in a viewport.
count = len(frames)
started = time.time()
step = 0
while time.time() - started < 5:
    step += 1
    drawing.shift = int(30 * np.sin(step / 6))
    drawing.update()
    pump(0.02)
fps = (len(frames) - count) / 5
print(f"live speed through the whole app: {fps:.1f} fps", flush=True)
check("live speed is usable", fps >= 6, f"{fps:.1f} fps")
window.grab().save(str(OUT / "app_window.png"))

process = window.worker._engine._process
window.stop()
check("stop ends the AI program", process.poll() is not None)

# Stopping during loading must not hang or leave anything running.
window.start()
pump(0.5)
process = window.worker._engine._process
started = time.time()
window.stop()
check("stop during load is quick", time.time() - started < 5, f"{time.time() - started:.1f} s")
check("stop during load ends the AI program", process is None or process.poll() is not None)

window.close()
drawing.close()
print("ALL PASSED" if all(results) else "SOME FAILED", flush=True)
sys.exit(0 if all(results) else 1)
