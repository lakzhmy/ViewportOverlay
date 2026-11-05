"""Checks the camera controls with real mouse clicks, and saves screenshots of the design.

The mouse pointer moves by itself. Arguments: output folder, and a sample image (optional).
"""
import ctypes
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from viewport_overlay import capture as capture_module
from viewport_overlay import looks as looks_module
from viewport_overlay import window as window_module
from viewport_overlay.engines import LocalKleinEngine, LocalTurboEngine, StandInEngine
from viewport_overlay.screen import to_physical
from viewport_overlay.window import MainWindow

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else None
SAMPLE = sys.argv[2] if len(sys.argv) > 2 else None
app = QApplication([])
user32 = ctypes.windll.user32
MOUSE_DOWN, MOUSE_UP = 0x0002, 0x0004
results = []
capture_module.SETTINGS_FILE = Path(tempfile.mkdtemp(prefix="camera_test_")) / "settings.json"
looks_module.LOOKS_FOLDER = Path(tempfile.mkdtemp(prefix="camera_looks_"))
opened = []
window_module.open_folder = opened.append


def check(name, passed, detail=""):
    results.append(bool(passed))
    print(("PASS " if passed else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def point_to(point: QPoint):
    spot = to_physical(QRect(point, point + QPoint(1, 1)))
    user32.SetCursorPos(spot["left"], spot["top"])
    pump(0.25)


def click(point: QPoint):
    """Windows runs its own loop while a window is dragged, so the mouse works from a side thread."""
    point_to(point)

    def steps():
        user32.mouse_event(MOUSE_DOWN, 0, 0, 0, 0)
        time.sleep(0.06)
        user32.mouse_event(MOUSE_UP, 0, 0, 0, 0)

    thread = threading.Thread(target=steps)
    thread.start()
    while thread.is_alive():
        pump(0.02)
    pump(0.25)


def click_widget(widget):
    click(widget.mapToGlobal(widget.rect().center()))


def snap(name):
    if OUT:
        window.grab().save(str(OUT / name))


window = MainWindow()
window.hide_capture.setChecked(False)
window.move(300, 60)
window.show()
pump(0.6)
stage = window.preview
snap("cam_1_empty.png")

check("no Start or Stop button is left", not hasattr(window, "run_button"))
check("the description is always on show", window.prompt_box.isVisible() and not stage.panel.isVisible())
check("the window buttons sit above the render", stage.close_button.mapTo(window, QPoint(0, 0)).y() < stage.mapTo(window, QPoint(0, 0)).y())
check("the logo starts white", not window.logo.on)
check("the shutter waits for a render", not window.capture_button.isEnabled())

# The logo selects a region.
click_widget(window.logo)
pump(0.2)
check("clicking the logo starts selecting", not window.logo.isEnabled() and window.picker._layers)
QTest.keyClick(window.picker._layers[0], Qt.Key.Key_Escape)
pump(0.2)
check("Esc cancels selecting", window.logo.isEnabled() and not window.logo.on)

# The orb opens the panel.
window.look_box.setCurrentIndex(4)
click_widget(stage.orb)
check("the orb opens the panel", stage.panel.isVisible())
check("the orb steps aside for the panel", not stage.orb.isVisible())
check("the Filter look turns the prompt off", not window.prompt_box.isEnabled())
button = window.look_box._group.button(0)
click_widget(button)
check("clicking a look selects it", window.look_box.currentIndex() == 0)
check("the panel stays open to try looks", stage.panel.isVisible())
check("AI looks use the prompt", window.prompt_box.isEnabled())
check("the look picks its engine", window._engine is LocalKleinEngine)
click(stage.panel.mapToGlobal(QPoint(stage.panel.width() - 12, 100)))
check("a click on the panel's background keeps it open", stage.panel.isVisible())
window.prompt_box.setPlainText("a red kettle")
check("the prompt reaches the renderer", window.params().prompt == "a red kettle")
snap("cam_2_panel_empty.png")
click(stage.mapToGlobal(QPoint(300, 300)))
check("clicking away closes the panel", not stage.panel.isVisible() and stage.orb.isVisible())
click_widget(stage.orb)
window.setFocus()
QTest.keyClick(window, Qt.Key.Key_Escape)
pump(0.1)
check("Esc closes the panel", not stage.panel.isVisible())

# Each look's wording and reference live in its own folder.
check("the Follow bar is gone", not hasattr(stage, "bar") and not hasattr(window, "follow_slider"))
look = looks_module.LOOKS[0]
wording = look.path / looks_module.WORDING_FILE
check("each look gets a wording file", wording.read_text(encoding="utf-8").strip() == look.first_wording)
wording.write_text("\ufeffOn a yacht.", encoding="utf-8")
check("edited wording reaches the renderer", window.params().style == "On a yacht.", window.params().style)
wording.write_text("", encoding="utf-8")
check("an emptied file falls back to the first wording", look.style == look.first_wording)
(look.path / "reference.jpg").write_bytes(b"x")
check("a jpg works as a reference", window.params().reference.endswith("reference.jpg"), window.params().reference)
sent = []
window.worker = type("Listener", (), {"set_params": lambda self, params: sent.append(params), "set_paused": lambda self, paused: None})()
wording.write_text("In a museum.", encoding="utf-8")
pump(1.3)
check("a saved edit is noticed while running", sent and sent[-1].style == "In a museum.", str(sent[-1:]))
window.worker = None
click_widget(stage.orb)
click_widget(stage.panel.edit_button)
check("Edit look opens the look's folder", opened == [look.path], str(opened))
window.look_box.setCurrentIndex(3)
check("looks with no folder have nothing to edit", not stage.panel.edit_button.isEnabled())
click_widget(stage.panel.cloud_tab)
check("Edit look stays with the Local tab", not stage.panel.edit_button.isVisible())
click_widget(stage.panel.local_tab)
stage.show_panel(False)

# The seed.
window.look_box.setCurrentIndex(0)
check("the seed box is on for klein", window.seed_box.isEnabled())
check("Try another waits for a region", not window.another_button.isEnabled())
window.seed_box.setText("4242")
window.seed_box.editingFinished.emit()
check("a typed seed reaches the renderer", window.params().seed == 4242, str(window.params().seed))
check("the seed is remembered", capture_module.load_settings()["seed"] == 4242)
window.seed_box.setText("")
window.seed_box.editingFinished.emit()
check("an empty box puts the seed back", window.seed_box.text() == "4242", window.seed_box.text())
window.look_box.setCurrentIndex(4)
check("Filter has no seed", not window.seed_box.isEnabled() and not window.another_button.isEnabled())

# A region turns the logo orange and starts rendering, with no Start button.
work = window.screen().availableGeometry()
window._region_picked(QRect(work.left() + 1500, work.top() + 200, 480, 320))
pump(1.0)
check("a region starts rendering", window.worker is not None and window.logo.on)
check("the status shows it's running", window.status.text().startswith(("Live", "Paused")), window.status.text())
check("the shutter is ready", window.capture_button.isEnabled())
worker = window.worker
click_widget(stage.orb)
click_widget(window.look_box._group.button(3))
check("an AI look from Filter swaps the engine", window.worker is not worker and window._engine is LocalTurboEngine)
click_widget(window.look_box._group.button(4))
worker = window.worker
pump(0.5)
check("Filter brings the filter back", window._engine is StandInEngine and window.worker is worker)
click(stage.mapToGlobal(QPoint(300, 300)))

# Try another, with a stand-in that uses a seed.
class Seeded(StandInEngine):
    uses_seed = True


window.stop()
window._engine = Seeded
window.start()
window._refresh_seed()
pump(0.6)
check("Try another is ready with a region", window.another_button.isEnabled())
window.pause_button.setChecked(True)
click_widget(window.another_button)
pump(0.6)
seed = window.params().seed
check("Try another picks a new seed", seed != 4242 and window.seed_box.text() == str(seed), str(seed))
check("Try another carries on from Pause", not window.pause_button.isChecked())
check("the image knows its seed", stage.current_image().text("seed") == str(seed), stage.current_image().text("seed"))
folder = Path(tempfile.mkdtemp(prefix="camera_seed_"))
saved = capture_module.save_image(stage.current_image(), folder)
check("the capture's name has the seed", saved.stem.endswith(f"_seed{seed}"), saved.name)
check("the saved file holds the seed too", QImage(str(saved)).text("seed") == str(seed))
window._engine = StandInEngine
window.stop()
window.start()
pump(0.4)
check("images from an engine with no seed have no seed", stage.current_image().text("seed") == "")

# The logo clears the region but keeps the last render.
click_widget(window.logo)
pump(0.3)
check("the logo clears the region", window.worker is None and not window.logo.on and not window.region_frame.isVisible())
check("the last render stays up", stage.current_image() is not None and not stage.message.isVisible())
check("it can still be captured", window.capture_button.isEnabled())
check("the status says so", window.status.text() == "Nothing selected yet", window.status.text())


# The controls fade away when the pointer leaves.
point_to(QPoint(work.left() + 40, work.top() + 40))
pump(0.5)
check("controls fade out when the pointer leaves", stage._chrome < 0.05, str(stage._chrome))
point_to(stage.mapToGlobal(QPoint(300, 300)))
pump(0.4)
check("controls come back", stage._chrome > 0.95, str(stage._chrome))

# The stuck hover: clicking the render starts a Windows drag loop, and the pointer's return then went unnoticed.
outside = QPoint(work.left() + 40, work.top() + 40)
click(stage.mapToGlobal(QPoint(300, 300)))
point_to(outside)
pump(0.5)
point_to(stage.mapToGlobal(QPoint(300, 300)))
pump(0.5)
check("controls come back after clicking the render", stage._chrome > 0.95, str(stage._chrome))
point_to(outside)
pump(0.5)
point_to(window.status.mapToGlobal(window.status.rect().center()))
pump(0.5)
check("the bottom line counts as over the window", stage._chrome > 0.95, str(stage._chrome))
maximise = stage.maximise_button
point_to(maximise.mapToGlobal(maximise.rect().center()))
pump(1.0)
check("controls stay on over the maximise button", stage._chrome > 0.95, str(stage._chrome))
point_to(outside)
pump(0.5)
point_to(stage.mapToGlobal(QPoint(300, 300)))
pump(0.5)
check("controls come back after the maximise button", stage._chrome > 0.95, str(stage._chrome))
click_widget(stage.orb)
point_to(QPoint(work.left() + 40, work.top() + 40))
pump(0.5)
check("an open panel keeps the controls up", stage._chrome > 0.95, str(stage._chrome))
stage.show_panel(False)

# The shortcut, pressed with the pointer away from the window.
CTRL, ALT, C_KEY, KEY_UP = 0x11, 0x12, 0x43, 0x0002


def press_shortcut():
    for key in (CTRL, ALT, C_KEY):
        user32.keybd_event(key, 0, 0, 0)
    for key in (C_KEY, ALT, CTRL):
        user32.keybd_event(key, 0, KEY_UP, 0)
    pump(0.4)


# Pressing it while another copy of the app owns it would take real captures in that copy.
if window._key_window == int(window.winId()):
    folder = Path(tempfile.mkdtemp(prefix="camera_shots_"))
    window.capture_settings["folder"] = str(folder)
    point_to(outside)
    QGuiApplication.clipboard().setText("untouched")
    pump(0.05)
    press_shortcut()
    check("the shortcut saves the render", len(list(folder.glob("*.png"))) == 1)
    check("the shortcut copies the render", QGuiApplication.clipboard().text() != "untouched" and not QGuiApplication.clipboard().image().isNull())
    window.on_top.setChecked(False)
    pump(0.3)
    window.on_top.setChecked(True)
    pump(0.3)
    press_shortcut()
    check("the shortcut survives Keep on top", len(list(folder.glob("*.png"))) == 2)
    window.to_clipboard.setChecked(False)
    window.to_folder.setChecked(False)
    press_shortcut()
    check("the shortcut explains when both are off", window.status.text() == "Turn on clipboard or folder first", window.status.text())
    window.to_clipboard.setChecked(True)
    window.to_folder.setChecked(True)
else:
    print("SKIP the shortcut checks: another copy of the app owns the key", flush=True)

# The space around the render continues its edges.
wide = np.full((100, 600, 3), 255, np.uint8)
wide[40:60] = 0
stage.show_image(QImage(wide.data, 600, 100, 1800, QImage.Format.Format_RGB888).copy())
pump(0.1)
above = stage._frame.pixelColor(stage._frame.width() // 2, 4)
below = stage._frame.pixelColor(stage._frame.width() // 2, stage._frame.height() - 4)
check("a white render has white margins", min(above.red(), below.red()) >= 250, f"{above.red()}, {below.red()}")
tall = np.full((600, 100, 3), 20, np.uint8)
stage.show_image(QImage(tall.data, 100, 600, 300, QImage.Format.Format_RGB888).copy())
pump(0.1)
left = stage._frame.pixelColor(4, stage._frame.height() // 2)
check("a dark tall render has dark margins", left.red() <= 25, str(left.red()))

# Screenshots of the design with a real picture.
if OUT:
    if SAMPLE:
        picture = QImage(SAMPLE).convertToFormat(QImage.Format.Format_RGB888)
    else:
        noise = np.full((320, 480, 3), 180, np.uint8)
        picture = QImage(noise.data, 480, 320, 1440, QImage.Format.Format_RGB888).copy()
    window.look_box.setCurrentIndex(0)
    window.logo.set_on(True)
    window._show_frame(picture, 10.0)
    stage.set_chrome(1.0)
    stage._fade.stop()
    pump(0.3)
    stage.set_chrome(1.0)
    snap("cam_3_live.png")
    stage.show_panel(True)
    pump(0.2)
    snap("cam_4_panel.png")
    stage.show_panel(False)
    window.resize(640, 600)
    pump(0.4)
    stage.set_chrome(1.0)
    snap("cam_5_narrow.png")
    stage.show_panel(True)
    pump(0.2)
    snap("cam_6_narrow_panel.png")

window.close()
print("ALL PASSED" if all(results) else "SOME FAILED", flush=True)
sys.exit(0 if all(results) else 1)
