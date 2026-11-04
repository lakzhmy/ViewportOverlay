"""Simulates real mouse drags on the region picker and region frame."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from viewport_overlay.region import HANDLE, TAB_HEIGHT
from viewport_overlay.screen import to_physical
from viewport_overlay.window import MainWindow

app = QApplication([])
L = Qt.MouseButton.LeftButton
results = []


def check(name, passed, detail=""):
    results.append(passed)
    print(("PASS " if passed else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)


def drag(widget, start, end):
    QTest.mousePress(widget, L, pos=start)
    QTest.mouseMove(widget, end)
    app.processEvents()
    QTest.mouseRelease(widget, L, pos=end)
    app.processEvents()


window = MainWindow()
window.engine_box.setCurrentIndex(1)
window.show()
window.select_region()
QTest.qWait(200)
layers = window.picker._layers
check("one selection layer per monitor", len(layers) == len(QGuiApplication.screens()), str(len(layers)))

drag(layers[0], QPoint(200, 200), QPoint(210, 210))
check("tiny drag is ignored", not window.region_frame.area().isValid())

layer = layers[0]
origin = layer.geometry().topLeft()
drag(layer, QPoint(200, 220), QPoint(700, 620))
QTest.qWait(200)
area = window.region_frame.area()
check("drag picks region", area.topLeft() == origin + QPoint(200, 220) and area.width() == 500, str(area))
check("capture starts by itself", window.worker is not None)

frame = window.region_frame
start_size = area.size()
tab = frame._tab.center()
drag(frame, tab, tab + QPoint(60, 40))
moved = frame.area()
check("tab drag moves region", moved.topLeft() == area.topLeft() + QPoint(60, 40) and moved.size() == start_size, str(moved))

right = QPoint(frame._inner().right() + HANDLE // 2, frame._inner().center().y())
drag(frame, right, right + QPoint(50, 0))
check("edge drag resizes region", frame.area().width() == moved.width() + 50, str(frame.area()))

corner = QPoint(frame._inner().left() - 2, frame._inner().top() - 2)
drag(frame, corner, corner + QPoint(2000, 2000))
check("resize stops at minimum size", frame.area().width() >= 64 and frame.area().height() >= 64, str(frame.area()))

window.select_region()
QTest.qWait(100)
QTest.keyClick(window.picker._layers[0], Qt.Key.Key_Escape)
QTest.qWait(100)
check("Esc keeps the old region", frame.isVisible() and window.select_button.isEnabled())

# Closing the region without closing the app.
QTest.mouseClick(frame, L, pos=frame.close_button().center())
QTest.qWait(100)
check("X closes the region", not frame.isVisible() and not frame.area().isValid())
check("X stops rendering", window.worker is None)
check("app stays open", window.isVisible() and window.select_button.text() == "Select region")
check("buttons reset", not window.run_button.isEnabled() and not window.clear_button.isEnabled())
window._region_picked(QRect(300, 300, 400, 300))
QTest.qWait(200)
check("new region works after closing", frame.isVisible() and window.worker is not None)
window.clear_button.click()
QTest.qWait(100)
check("Clear region button works", not frame.isVisible() and window.worker is None)

# Second monitor and scaled-display maths.
for screen in QGuiApplication.screens():
    g = screen.geometry()
    r = QRect(g.left() + 100, g.top() + 100, 200, 100)
    print("screen", g, "scale", screen.devicePixelRatio(), "->", to_physical(r))

window.close()
print("ALL PASSED" if all(results) else "SOME FAILED")
sys.exit(0 if all(results) else 1)
