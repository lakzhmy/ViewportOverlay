"""Checks Windows snapping with real mouse input, and saves screenshots of the new look.

The mouse pointer moves by itself, and the test window snaps around the screen.
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
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import QApplication, QWidget

from viewport_overlay.screen import GWL_STYLE, SNAP_STYLES, to_physical
from viewport_overlay.window import MainWindow

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
SAMPLE = sys.argv[2] if len(sys.argv) > 2 else None
app = QApplication([])
user32 = ctypes.windll.user32
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
results = []
MOUSE_DOWN, MOUSE_UP = 0x0002, 0x0004
ESCAPE, KEY_UP = 0x1B, 0x0002


def check(name, passed, detail=""):
    results.append(passed)
    print(("PASS " if passed else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def physical(point: QPoint) -> tuple:
    r = to_physical(QRect(point, point + QPoint(1, 1)))
    return r["left"], r["top"]


def run_mouse(steps):
    """Windows runs its own loop during drags, so the mouse moves from a side thread."""
    thread = threading.Thread(target=steps)
    thread.start()
    while thread.is_alive():
        pump(0.02)
    pump(0.6)


def real_drag(start: QPoint, end: QPoint):
    x, y = physical(start)
    ex, ey = physical(end)

    def steps():
        user32.SetCursorPos(x, y)
        time.sleep(0.2)
        user32.mouse_event(MOUSE_DOWN, 0, 0, 0, 0)
        time.sleep(0.2)
        for step in range(1, 21):
            user32.SetCursorPos(x + (ex - x) * step // 20, y + (ey - y) * step // 20)
            time.sleep(0.03)
        time.sleep(0.5)
        user32.mouse_event(MOUSE_UP, 0, 0, 0, 0)

    run_mouse(steps)


def real_click(point: QPoint, times=1):
    x, y = physical(point)

    def steps():
        user32.SetCursorPos(x, y)
        time.sleep(0.25)
        for _ in range(times):
            user32.mouse_event(MOUSE_DOWN, 0, 0, 0, 0)
            user32.mouse_event(MOUSE_UP, 0, 0, 0, 0)
            time.sleep(0.06)

    run_mouse(steps)


def dismiss_snap_assist():
    user32.keybd_event(ESCAPE, 0, 0, 0)
    user32.keybd_event(ESCAPE, 0, KEY_UP, 0)
    pump(0.4)


def shot(rect: QRect, name):
    with mss.MSS() as capture:
        grabbed = capture.grab(to_physical(rect))
    pixels = np.frombuffer(grabbed.bgra, np.uint8).reshape(grabbed.height, grabbed.width, 4)[:, :, 2::-1]
    rgb = np.ascontiguousarray(pixels)
    h, w, _ = rgb.shape
    QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).save(str(OUT / name))


screen = QGuiApplication.primaryScreen()
work = screen.availableGeometry()
window = MainWindow()
window.look_box.setCurrentIndex(4)
window.hide_capture.setChecked(False)
window.move(work.left() + 300, work.top() + 200)
window.show()
pump(0.6)
hwnd = int(window.winId())

style = user32.GetWindowLongPtrW(ctypes.c_void_p(hwnd), GWL_STYLE)
check("window has the styles Windows needs to snap it", style & SNAP_STYLES == SNAP_STYLES, hex(style))
check("no title bar appeared", window.geometry() == window.frameGeometry(), str(window.frameGeometry()))
window.grab().save(str(OUT / "1_empty.png"))

# The Keep on top switch can rebuild the window, so the styles must survive it.
window.on_top.setChecked(False)
pump(0.3)
window.on_top.setChecked(True)
pump(0.3)
hwnd = int(window.winId())
style = user32.GetWindowLongPtrW(ctypes.c_void_p(hwnd), GWL_STYLE)
check("styles survive Keep on top", style & SNAP_STYLES == SNAP_STYLES)

# Drag to the left edge: Windows should tile it to the left half.
grab_point = window.mapToGlobal(QPoint(260, 120))
real_drag(grab_point, QPoint(work.left() + 1, work.center().y()))
dismiss_snap_assist()
geometry = window.frameGeometry()
half = work.width() // 2
check("dragging to the left edge tiles to half the screen",
      abs(geometry.left() - work.left()) < 12 and abs(geometry.width() - half) < 24
      and abs(geometry.height() - work.height()) < 24, str(geometry))

# Drag away: it should go back to its own size.
real_drag(window.mapToGlobal(QPoint(260, 120)), QPoint(work.left() + 700, work.top() + 300))
pump(0.3)
check("dragging away restores the size", window.width() < half, str(window.frameGeometry()))
window.resize(1040, 800)
window.move(work.left() + 300, work.top() + 120)
pump(0.3)

# The maximise button, with a real click.
button = window.preview.maximise_button
real_click(button.mapToGlobal(button.rect().center()))
check("maximise button maximises", window.isMaximized(), str(window.frameGeometry()))
inside = window.geometry()
check("maximised window fits the screen", work.contains(inside.adjusted(1, 1, -1, -1)), f"{inside} in {work}")
window.grab().save(str(OUT / "2_maximised.png"))
button = window.preview.maximise_button
real_click(button.mapToGlobal(button.rect().center()))
check("second click restores", not window.isMaximized() and window.width() == 1040, str(window.frameGeometry()))

# Double click on the render area.
real_click(window.mapToGlobal(QPoint(260, 120)), times=2)
check("double click maximises", window.isMaximized())
real_click(window.mapToGlobal(QPoint(260, 120)), times=2)
check("double click restores", not window.isMaximized())

# A one-third tile on this screen.
window.resize(work.width() // 3, work.height())
pump(0.3)
check("fits a one-third tile", window.width() <= work.width() // 3 + 1, str(window.size()))
window.grab().save(str(OUT / "3_narrow.png"))
window.resize(1040, 800)
window.move(work.left() + 120, work.top() + 100)
pump(0.3)

# Hovering the maximise button: look for the Windows snap layouts menu.
button = window.preview.maximise_button
target = physical(button.mapToGlobal(button.rect().center()))
run_mouse(lambda: (user32.SetCursorPos(*target), time.sleep(1.4)))
shot(window.frameGeometry().adjusted(500, -10, 300, -300), "4_snap_menu.png")
check("button lights up on hover", button._hot)
user32.SetCursorPos(*physical(window.mapToGlobal(QPoint(300, 300))))
pump(0.6)
check("hover clears after leaving", not button._hot)

if SAMPLE:
    image = QImage(SAMPLE).convertToFormat(QImage.Format.Format_RGB888)
    window.region_frame.set_area(QRect(work.left() + 1240, work.top() + 200, 560, 420))
    window.region_frame.show()
    window.logo.set_on(True)
    window._show_frame(image, 10.0)
    pump(0.26)
    window.grab().save(str(OUT / "5_reveal_midway.png"))
    pump(0.6)
    window.preview.set_chrome(1.0)
    window.preview._fade.stop()
    pump(0.2)
    window.preview.set_chrome(1.0)
    window.grab().save(str(OUT / "6_live.png"))
    shot(QRect(work.left() + 1200, work.top() + 140, 640, 520), "7_region.png")
    window.region_frame.clear()
    window.preview.set_live(False)

# The rounded frame must still let clicks through, and still be easy to grab.
class Target(QWidget):
    clicks = 0

    def mousePressEvent(self, event):
        Target.clicks += 1


area = QRect(work.left() + 1240, work.top() + 200, 560, 420)
target = Target(None, Qt.WindowType.FramelessWindowHint)  # a normal window, like Rhino
target.setGeometry(area.adjusted(-60, -60, 60, 60))
target.show()
window.region_frame.set_area(area)
window.region_frame.show()
window.region_frame.raise_()
pump(0.4)
real_click(area.center())
check("clicks inside the region reach the app underneath", Target.clicks == 1, str(Target.clicks))
Target.clicks = 0
edge = QPoint(area.right() + 8, area.center().y())
real_drag(edge, edge + QPoint(40, 0))
check("the band beside the line can be grabbed", window.region_frame.area().width() == area.width() + 40 and Target.clicks == 0,
      str(window.region_frame.area()))
tab = window.region_frame.mapToGlobal(window.region_frame._tab.center() - QPoint(20, 0))
before = window.region_frame.area().topLeft()
real_drag(tab, tab + QPoint(30, 30))
check("the pill moves the region", window.region_frame.area().topLeft() == before + QPoint(30, 30))
window.region_frame.clear()
target.close()

window.preview.close_button.click()
pump(0.2)
print("ALL PASSED" if all(results) else "SOME FAILED", flush=True)
sys.exit(0 if all(results) else 1)
