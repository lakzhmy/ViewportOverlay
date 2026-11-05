"""Runs the real app windows briefly and checks capture, hiding and live updates."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mss
import numpy as np
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from viewport_overlay.engines import RenderParams, StandInEngine
from viewport_overlay.screen import exclude_from_capture, to_physical
from viewport_overlay.window import MainWindow

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
app = QApplication([])
results = []


def check(name, passed, detail=""):
    results.append(passed)
    print(("PASS " if passed else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def solid_window(color, rect):
    w = QWidget(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
    palette = w.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(color))
    w.setPalette(palette)
    w.setAutoFillBackground(True)
    w.setGeometry(rect)
    w.show()
    return w


def grab(rect):
    with mss.MSS() as capture:
        shot = capture.grab(to_physical(rect))
    return np.frombuffer(shot.bgra, np.uint8).reshape(shot.height, shot.width, 4)[:, :, 2::-1]


screen = QGuiApplication.primaryScreen()
print("screen", screen.geometry(), "scale", screen.devicePixelRatio(), "screens", len(QGuiApplication.screens()))
area = QRect(screen.geometry().left() + 120, screen.geometry().top() + 140, 420, 300)

# Capture lines up with the requested rectangle.
green = solid_window("#00FF00", area)
pump(0.5)
pixels = grab(area).astype(int)
is_green = (pixels[..., 1] > 200) & (pixels[..., 0] < 80) & (pixels[..., 2] < 80)
check("capture lines up with region", is_green.mean() > 0.98, f"{is_green.mean():.3f} green")

# A hidden window on top must not appear in the capture.
magenta = solid_window("#FF00FF", area.adjusted(40, 40, -40, -40))
hidden = exclude_from_capture(magenta)
pump(0.5)
pixels = grab(area).astype(int)
is_magenta = (pixels[..., 0] > 200) & (pixels[..., 1] < 80) & (pixels[..., 2] > 200)
check("hide-from-capture call accepted", hidden)
check("hidden window stays out of capture", is_magenta.mean() < 0.01, f"{is_magenta.mean():.3f} magenta")
magenta.close()

# The real app: pick a region, run, change settings, move, stop.
window = MainWindow()
window.look_box.setCurrentIndex(4)
window.move(screen.geometry().left() + 620, screen.geometry().top() + 100)
window.show()
frames = []
window.picker.picked.connect(lambda _: None)
window._region_picked(area)
window.worker.frame_ready.connect(lambda image, fps: frames.append((image, fps)))
pump(1.0)
check("first frame arrives", len(frames) >= 1, f"{len(frames)} frames")
check("region frame visible in window", window.region_frame.isVisible())
check("status shows no failure", "wrong" not in window.status.text(), window.status.text())

pump(1.5)
count = len(frames)
pump(1.0)
check("still screen skips rendering", len(frames) - count <= 3, f"{len(frames) - count} frames in 1s")

count = len(frames)
window.prompt_box.setPlainText("steel")
pump(0.4)
check("a change of settings renders while running", len(frames) > count)

count = len(frames)
green.setGeometry(area.adjusted(30, 0, 0, 0))
window.region_frame.set_area(area.translated(40, 20))
window._region_moved(window.region_frame.area())
pump(0.5)
check("moving region updates capture", len(frames) > count)

window.preview.grab().save(str(OUT / "preview.png"))
window.grab().save(str(OUT / "window.png"))

# Clicks inside the frame must pass through: the mask has a hole.
inner = window.region_frame.mask()
centre = window.region_frame.rect().center()
check("frame interior is click-through", not inner.contains(centre))

window.clear_region()
check("clearing stops rendering", window.worker is None)
check("the last render stays on screen", window.preview.current_image() is not None)
window.close()
green.close()
pump(0.2)

# Stand-in engine on its own, on an odd-sized large image.
frame = (np.random.default_rng(1).random((1081, 1923, 3)) * 255).astype(np.uint8)
started = time.perf_counter()
loose = StandInEngine().render(frame, RenderParams(follow=0.0))
strict = StandInEngine().render(frame, RenderParams(follow=1.0))
speed = (time.perf_counter() - started) / 2
check("engine keeps size and type", loose.shape == strict.shape and loose.dtype == np.uint8, str(loose.shape))
check("how closely it follows changes the result", not np.array_equal(loose, strict))
print(f"stand-in render time at 1080p: {speed * 1000:.0f} ms")

print("ALL PASSED" if all(results) else "SOME FAILED", flush=True)
sys.exit(0 if all(results) else 1)
