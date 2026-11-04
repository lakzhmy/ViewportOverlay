"""Windows and display helpers."""
import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication

WDA_NONE = 0x0
WDA_EXCLUDEFROMCAPTURE = 0x11
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWCP_ROUND = 2
INK_700_COLORREF = 0x00423D3A  # Windows stores colours as blue, green, red


def exclude_from_capture(widget, excluded: bool = True) -> bool:
    """Keep this window out of screenshots. Applies to this window only."""
    if sys.platform != "win32":
        return False
    set_affinity = ctypes.windll.user32.SetWindowDisplayAffinity
    set_affinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    set_affinity.restype = wintypes.BOOL
    return bool(set_affinity(int(widget.winId()), WDA_EXCLUDEFROMCAPTURE if excluded else WDA_NONE))


def style_native_window(widget) -> None:
    """Ask Windows 11 for rounded corners and a brand-coloured edge on this window."""
    if sys.platform != "win32":
        return
    set_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
    set_attribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    hwnd = int(widget.winId())
    for name, value in ((DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND), (DWMWA_BORDER_COLOR, INK_700_COLORREF)):
        data = ctypes.c_uint(value)
        set_attribute(hwnd, name, ctypes.byref(data), ctypes.sizeof(data))


def set_app_id() -> None:
    """Lets the taskbar show the app's own icon instead of Python's."""
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ViewportOverlay.App")


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
