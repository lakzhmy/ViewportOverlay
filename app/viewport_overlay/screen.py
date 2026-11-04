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
GWL_STYLE = -16
SNAP_STYLES = 0x00C00000 | 0x00040000 | 0x00080000 | 0x00020000 | 0x00010000  # caption, resize, menu, min, max
SWP_REFRESH_FRAME = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020  # keep size, place and order; redo the frame
SM_CXSIZEFRAME = 32
SM_CXPADDEDBORDER = 92
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_NCLBUTTONDOWN = 0x00A1
WM_NCLBUTTONUP = 0x00A2
HTMAXBUTTON = 9


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


def enable_native_frame(widget) -> None:
    """Give a frameless window the frame styles Windows needs before it will snap it.

    The window keeps its look because it answers WM_NCCALCSIZE by claiming the whole
    frame as its own drawing area, which hides the title bar.
    """
    if sys.platform != "win32":
        return
    user32 = ctypes.windll.user32
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [wintypes.UINT]
    hwnd = int(widget.winId())
    style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
    if style & SNAP_STYLES != SNAP_STYLES:
        user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style | SNAP_STYLES)
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_REFRESH_FRAME)


def maximised_inset(hwnd: int) -> int:
    """How far a maximised window hangs off the screen, in real pixels."""
    user32 = ctypes.windll.user32
    user32.GetDpiForWindow.argtypes = [wintypes.HWND]
    dpi = user32.GetDpiForWindow(hwnd)
    return user32.GetSystemMetricsForDpi(SM_CXSIZEFRAME, dpi) + user32.GetSystemMetricsForDpi(SM_CXPADDEDBORDER, dpi)


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
