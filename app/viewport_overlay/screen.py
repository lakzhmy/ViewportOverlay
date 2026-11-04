"""Windows and display helpers."""
import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication

WDA_EXCLUDEFROMCAPTURE = 0x11


def exclude_from_capture(widget) -> bool:
    """Keep this window out of screenshots. Applies to this window only."""
    if sys.platform != "win32":
        return False
    set_affinity = ctypes.windll.user32.SetWindowDisplayAffinity
    set_affinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    set_affinity.restype = wintypes.BOOL
    return bool(set_affinity(int(widget.winId()), WDA_EXCLUDEFROMCAPTURE))


def to_physical(rect: QRect) -> dict:
    """Convert a Qt rectangle to the real screen pixels that mss captures."""
    screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
    scale = screen.devicePixelRatio()
    origin = screen.geometry().topLeft()
    return {
        "left": origin.x() + round((rect.x() - origin.x()) * scale),
        "top": origin.y() + round((rect.y() - origin.y()) * scale),
        "width": max(1, round(rect.width() * scale)),
        "height": max(1, round(rect.height() * scale)),
    }
