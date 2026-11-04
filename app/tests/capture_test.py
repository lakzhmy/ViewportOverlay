"""Checks the Capture button with real mouse clicks, using throwaway folders.

The mouse pointer moves by itself. Your own settings and clipboard text are not kept:
the clipboard is overwritten, and settings go to a temporary file.
"""
import ctypes
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import QApplication

from viewport_overlay import capture as capture_module
from viewport_overlay import window as window_module
from viewport_overlay.screen import to_physical

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else None
app = QApplication([])
user32 = ctypes.windll.user32
MOUSE_DOWN, MOUSE_UP = 0x0002, 0x0004
results = []

real_settings = capture_module.SETTINGS_FILE
settings_before = real_settings.read_bytes() if real_settings.exists() else None
scratch = Path(tempfile.mkdtemp(prefix="capture_test_"))
capture_module.SETTINGS_FILE = scratch / "settings.json"
renders = scratch / "Renders 2026"
renders.mkdir()


class Picker:
    """Stands in for the Windows folder picker, which a test can't click through."""
    answer = str(renders)
    asked = 0

    @classmethod
    def getExistingDirectory(cls, *args):
        cls.asked += 1
        return cls.answer


window_module.QFileDialog = Picker


def check(name, passed, detail=""):
    results.append(bool(passed))
    print(("PASS " if passed else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def render(seed: int) -> QImage:
    """A picture that is different for each seed, so a mix-up can't pass."""
    noise = np.random.default_rng(seed).integers(0, 255, (320, 480, 3), dtype=np.uint8)
    return QImage(noise.data, 480, 320, 3 * 480, QImage.Format.Format_RGB888).copy()


def same(first: QImage, second: QImage) -> bool:
    return first.convertToFormat(QImage.Format.Format_RGB888) == second.convertToFormat(QImage.Format.Format_RGB888)


def click_capture(window):
    middle = window.capture_button.mapToGlobal(window.capture_button.rect().center())
    spot = to_physical(QRect(middle, middle + QPoint(1, 1)))
    user32.SetCursorPos(spot["left"], spot["top"])
    pump(0.25)
    user32.mouse_event(MOUSE_DOWN, 0, 0, 0, 0)
    pump(0.06)
    user32.mouse_event(MOUSE_UP, 0, 0, 0, 0)
    pump(0.1)


def files():
    return sorted(renders.glob("*.png"))


def clipboard_mark():
    QGuiApplication.clipboard().setText("untouched")
    pump(0.05)


def clipboard_untouched():
    return QGuiApplication.clipboard().text() == "untouched"


window = window_module.MainWindow()
window.hide_capture.setChecked(False)
window.resize(1040, 800)
window.move(300, 60)
window.show()
pump(0.5)

check("Capture is unavailable before there is a render", not window.capture_button.isEnabled())
check("both switches start on", window.to_folder.isChecked() and window.to_clipboard.isChecked())
check("the folder row invites a choice", "Choose folder" in window.folder_button.text(), window.folder_button.text())

first = render(1)
window.preview.live_card.show()
window._show_frame(first, 10.0)
pump(0.8)
window._place_seam()
check("Capture becomes available with a render", window.capture_button.isEnabled())

click_capture(window)
check("the first save asks for a folder", Picker.asked == 1, str(Picker.asked))
check("the render flashes", window.preview._flash_run.state() == window.preview._flash_run.State.Running)
saved = files()
check("one file is saved", len(saved) == 1, str(saved))
check("the file name has the date and time", saved and saved[0].name.startswith("ViewportOverlay_20"), saved[0].name)
check("the saved file is the exact render", same(QImage(str(saved[0])), first))
check("the clipboard holds the exact render", same(QGuiApplication.clipboard().image(), first))
check("status reports both", window.status.text() == "Saved and copied", window.status.text())
window._show_frame(render(2), 10.0)
pump(0.1)
check("the message survives the next frames", window.status.text() == "Saved and copied", window.status.text())
check("the folder name is shown", "Renders 2026" in window.folder_button.text(), window.folder_button.text())
pump(3.1)
check("the status goes back to normal afterwards", window.status.text() == "Rendering", window.status.text())

before = saved[0].read_bytes()
second = render(3)
window._show_frame(second, 10.0)
click_capture(window)
click_capture(window)
saved = files()
check("it never asks for the folder again", Picker.asked == 1, str(Picker.asked))
check("quick captures each get their own file", len(saved) == 3, str(len(saved)))
check("older files are left alone", saved[0].read_bytes() == before)
check("the capture is the frame on screen", same(QImage(str(saved[-1])), second))

window.to_clipboard.setChecked(False)
clipboard_mark()
click_capture(window)
check("Folder only saves a file", len(files()) == 4)
check("Folder only leaves the clipboard alone", clipboard_untouched())
check("Folder only says where it went", window.status.text() == "Saved to Renders 2026", window.status.text())

window.to_clipboard.setChecked(True)
window.to_folder.setChecked(False)
check("the folder name dims with its switch", not window.folder_button.isEnabled())
third = render(4)
window._show_frame(third, 10.0)
click_capture(window)
check("Clipboard only saves no file", len(files()) == 4)
check("Clipboard only copies", same(QGuiApplication.clipboard().image(), third))
check("Clipboard only says so", window.status.text() == "Copied to clipboard", window.status.text())

window.to_clipboard.setChecked(False)
check("with both off, Capture greys out", not window.capture_button.isEnabled())
window.to_clipboard.setChecked(True)
window.to_folder.setChecked(True)
check("turning one on brings it back", window.capture_button.isEnabled())

# Stopped or paused: the last render stays on screen and can still be kept.
window.stop()
window._notice_timer.stop()
click_capture(window)
check("works while stopped", len(files()) == 5)

# Cancelling the folder picker keeps the copy, and says the file wasn't saved.
window.capture_settings["folder"] = ""
Picker.answer = ""
click_capture(window)
check("cancelling the picker saves nothing", len(files()) == 5)
check("cancelling says so", window.status.text() == "Copied, but not saved: no folder chosen", window.status.text())

# A folder that can't be written: a file stands where the folder should be.
blocker = scratch / "not a folder"
blocker.write_text("x")
window.capture_settings["folder"] = str(blocker)
click_capture(window)
check("a bad folder is reported", window.status.text() == "Copied, but not saved: can't write to that folder", window.status.text())

# Choosing another folder from the row.
other = scratch / "A very long folder name that keeps going and going for quite a while indeed, more than fits"
other.mkdir()
Picker.answer = str(other)
window.folder_button.click()
pump(0.1)
check("the folder name opens the picker and changes the folder", window.capture_settings["folder"] == str(other))

# Tight window: a one-third tile at its smallest.
window.resize(640, 600)
pump(0.5)
window._place_seam()
check("the window still reaches its smallest size", window.width() == 640 and window.height() == 600, str(window.size()))
check("the render keeps its minimum height", window.preview.height() >= 240, str(window.preview.height()))
check("a long folder name shortens", "…" in window.folder_button.text(), window.folder_button.text())
inside = window.to_clipboard.mapTo(window, window.to_clipboard.rect().bottomRight())
check("the swatch labels are not cut off", window.style_box.height() >= window.style_box.sizeHint().height(), str(window.style_box.height()))
check("the capture row fits", inside.x() < window.width() - 20, str(inside))
check("the button group fits", window.seam.x() > 0 and window.seam.geometry().right() < window.width(), str(window.seam.geometry()))
if OUT:
    window.grab().save(str(OUT / "capture_narrow.png"))
window.resize(1040, 800)
pump(0.4)
window._place_seam()
if OUT:
    window.preview.set_chrome(1.0)
    window.grab().save(str(OUT / "capture_wide.png"))

# Clear removes the render, so there's nothing left to capture.
window.clear_region()
check("Clear makes Capture unavailable", not window.capture_button.isEnabled())

# Everything is remembered next time.
window.to_clipboard.setChecked(False)
window.close()
pump(0.2)
again = window_module.MainWindow()
check("switches are remembered", again.to_folder.isChecked() and not again.to_clipboard.isChecked())
check("the folder is remembered", again.capture_settings["folder"] == str(other))
again.close()

capture_module.SETTINGS_FILE.write_text("this is not valid")
check("a damaged settings file is survived", capture_module.load_settings() == capture_module.DEFAULTS)

now = real_settings.read_bytes() if real_settings.exists() else None
check("your real settings were not touched", now == settings_before)
shutil.rmtree(scratch, ignore_errors=True)
print("ALL PASSED" if all(results) else "SOME FAILED", flush=True)
sys.exit(0 if all(results) else 1)
