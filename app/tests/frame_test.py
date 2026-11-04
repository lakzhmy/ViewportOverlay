"""Checks the custom window frame with real mouse input, and saves real screenshots.

The mouse pointer moves by itself for a few seconds while this runs.
"""
import ctypes
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mss
import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from viewport_overlay.screen import to_physical
from viewport_overlay.window import MainWindow

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
SAMPLE = sys.argv[2] if len(sys.argv) > 2 else None
app = QApplication([])
user32 = ctypes.windll.user32
results = []
MOUSE_DOWN, MOUSE_UP = 0x0002, 0x0004


def check(name, passed, detail=""):
    results.append(passed)
    print(("PASS " if passed else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def point(widget_point: QPoint) -> tuple:
    r = to_physical(QRect(widget_point, widget_point + QPoint(1, 1)))
    return r["left"], r["top"]


def real_drag(start: QPoint, end: QPoint):
    """Windows runs its own loop during a window drag, so the mouse moves from a side thread."""
    x, y = point(start)
    ex, ey = point(end)

    def move():
        user32.SetCursorPos(x, y)
        time.sleep(0.2)
        user32.mouse_event(MOUSE_DOWN, 0, 0, 0, 0)
        time.sleep(0.2)
        for step in range(1, 11):
            user32.SetCursorPos(x + (ex - x) * step // 10, y + (ey - y) * step // 10)
            time.sleep(0.03)
        user32.mouse_event(MOUSE_UP, 0, 0, 0, 0)

    thread = threading.Thread(target=move)
    thread.start()
    while thread.is_alive():
        pump(0.02)
    pump(0.3)


def shot(rect: QRect, name=None):
    with mss.MSS() as capture:
        grabbed = capture.grab(to_physical(rect))
    pixels = np.frombuffer(grabbed.bgra, np.uint8).reshape(grabbed.height, grabbed.width, 4)[:, :, 2::-1]
    if name:
        rgb = np.ascontiguousarray(pixels)
        h, w, _ = rgb.shape
        QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).save(str(OUT / name))
    return pixels


class Backdrop(QWidget):
    """A plain light surface behind the window, so its corners are easy to see."""

    def __init__(self, rect):
        super().__init__(None, Qt.WindowType.FramelessWindowHint)
        self.setGeometry(rect)

    def paintEvent(self, event):
        QPainter(self).fillRect(self.rect(), QColor("#D9DCE2"))


screen = QGuiApplication.primaryScreen().geometry()
backdrop = Backdrop(QRect(screen.left() + 40, screen.top() + 40, 1240, 1000))
backdrop.show()
window = MainWindow()
window.look_box.setCurrentIndex(4)
window.hide_capture.setChecked(False)
window.move(screen.left() + 120, screen.top() + 100)
window.show()
pump(0.5)

# Hide from capture really switches.
area = window.frameGeometry()
centre = area.adjusted(300, 100, -300, -400)
visible = shot(centre).astype(int)
window.hide_capture.setChecked(True)
pump(0.4)
hidden = shot(centre).astype(int)
window.hide_capture.setChecked(False)
pump(0.4)
check("switch off: window shows in capture", np.abs(visible - [217, 220, 226]).mean() > 20)
check("switch on: window leaves capture", np.abs(hidden - [217, 220, 226]).mean() < 5)

# Keep on top rebuilds the window, so the setting must survive it.
window.hide_capture.setChecked(True)
window.on_top.setChecked(False)
pump(0.4)
window.on_top.setChecked(True)
pump(0.4)
check("stays hidden after Keep on top changes", np.abs(shot(centre).astype(int) - [217, 220, 226]).mean() < 5)
window.hide_capture.setChecked(False)
pump(0.3)

# Real mouse: drag, resize, buttons.
before = window.pos()
stage_spot = window.mapToGlobal(QPoint(260, 200))
real_drag(stage_spot, stage_spot + QPoint(70, 40))
check("dragging the render moves the window", window.pos() == before + QPoint(70, 40), f"{before} -> {window.pos()}")

size = window.size()
corner = window.mapToGlobal(QPoint(window.width() - 3, window.height() - 3))
real_drag(corner, corner + QPoint(60, -50))
check("corner grip resizes the window", window.width() > size.width() + 40, f"{size} -> {window.size()}")
real_drag(window.mapToGlobal(QPoint(window.width() - 2, 400)), window.mapToGlobal(QPoint(window.width() - 62, 400)))
window.resize(1040, 800)
window.move(screen.left() + 120, screen.top() + 100)
pump(0.3)

# Screenshots.
window.grab().save(str(OUT / "1_empty.png"))
shot(window.frameGeometry().adjusted(-24, -24, 24, 24), "2_real_corners.png")
if SAMPLE:
    image = QImage(SAMPLE).convertToFormat(QImage.Format.Format_RGB888)
    window.region_frame.set_area(QRect(screen.left() + 1250, screen.top() + 200, 560, 420))
    window.region_frame.show()
    window.logo.set_on(True)
    window._show_frame(image, 10.0)
    window.preview.set_chrome(1.0)
    window.preview._fade.stop()
    pump(0.3)
    window.preview.set_chrome(1.0)
    window.grab().save(str(OUT / "3_live.png"))
    shot(QRect(screen.left() + 1220, screen.top() + 150, 620, 510), "4_region.png")
    window.preview._fade_to(0.0)
    pump(0.4)
    window.grab().save(str(OUT / "5_faded.png"))
    window.region_frame.clear()
    window.preview.set_live(False)

window.preview.minimise_button.click()
pump(0.4)
check("minimise button minimises", window.isMinimized())
window.showNormal()
pump(0.4)
check("window comes back", window.isVisible() and not window.isMinimized())

window.preview.close_button.click()
pump(0.2)
check("close button closes", not window.isVisible())
backdrop.close()
print("ALL PASSED" if all(results) else "SOME FAILED", flush=True)
sys.exit(0 if all(results) else 1)
