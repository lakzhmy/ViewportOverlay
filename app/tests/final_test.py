"""Checks Render final against a pretend fal server on this computer. Nothing leaves it, and nothing costs money.

It proves the app's side only. The real fal connection needs a real key, and hasn't been tried.
The mouse pointer moves by itself. Arguments: output folder for screenshots (optional).
"""
import base64
import ctypes
import json
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QRect
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import QApplication, QMessageBox

from viewport_overlay import capture as capture_module
from viewport_overlay import cloud
from viewport_overlay import window as window_module
from viewport_overlay.engines import RenderParams
from viewport_overlay.screen import to_physical

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else None
app = QApplication([])
user32 = ctypes.windll.user32
results = []
scratch = Path(tempfile.mkdtemp(prefix="final_test_"))
real_key_file = cloud.KEY_FILE
key_before = real_key_file.read_bytes() if real_key_file.exists() else None
capture_module.SETTINGS_FILE = scratch / "settings.json"
cloud.KEY_FILE = scratch / "secrets.key"
cloud.POLL_SECONDS = 0.05
renders = scratch / "Renders"
renders.mkdir()
TEST_KEY = "pretend-key-for-tests"


def check(name, passed, detail=""):
    results.append(bool(passed))
    print(("PASS " if passed else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def wait_for(condition, seconds=5):
    end = time.time() + seconds
    while time.time() < end and not condition():
        pump(0.02)
    return condition()


def picture(color) -> QImage:
    image = QImage(640, 480, QImage.Format.Format_RGB888)
    image.fill(color)
    return image


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


class Fal:
    """What the pretend server should do next, and what it was sent."""
    mode = "ok"
    polls_needed = 2
    requests = []
    cancels = 0
    picture = b""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, kind="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fal.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
        if Fal.mode == "bad key":
            return self._send(401, {"detail": "Invalid key"})
        if Fal.mode == "no credit":
            return self._send(403, {"detail": "User is locked. Reason: Exhausted balance."})
        if Fal.mode == "rejected":
            return self._send(422, {"detail": [{"loc": ["body", "image_size"], "msg": "no", "type": "x"}]})
        Fal.polls = 0
        base = f"http://127.0.0.1:{server.server_port}/requests/1"
        self._send(200, {"request_id": "1", "status_url": f"{base}/status", "response_url": base, "cancel_url": f"{base}/cancel"})

    def do_GET(self):
        if self.path.endswith("/status"):
            Fal.polls += 1
            finished = Fal.mode != "slow" and Fal.polls >= Fal.polls_needed
            return self._send(200, {"status": "COMPLETED" if finished else "IN_PROGRESS"})
        if self.path == "/requests/1":
            if Fal.mode == "empty":
                return self._send(200, {"images": []})
            return self._send(200, {"images": [{"url": f"http://127.0.0.1:{server.server_port}/file.png"}]})
        Fal.file_headers = {k.lower(): v for k, v in self.headers.items()}
        self._send(200, Fal.picture, "image/png")

    def do_PUT(self):
        Fal.cancels += 1
        self._send(200, {"status": "CANCELLATION_REQUESTED"})


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
cloud.QUEUE_URL = f"http://127.0.0.1:{server.server_port}"
Fal.picture = png_bytes(picture(0xFF3366))


class Asker:
    """Stands in for the one-time message box."""
    answer = QMessageBox.StandardButton.Cancel
    asked = 0
    StandardButton = QMessageBox.StandardButton

    @classmethod
    def question(cls, *args):
        cls.asked += 1
        return cls.answer


window_module.QMessageBox = Asker


def point_to(point: QPoint):
    spot = to_physical(QRect(point, point + QPoint(1, 1)))
    user32.SetCursorPos(spot["left"], spot["top"])
    pump(0.25)


def click(widget):
    middle = widget.mapToGlobal(widget.rect().center())
    point_to(middle)

    def steps():
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.06)
        user32.mouse_event(0x0004, 0, 0, 0, 0)

    thread = threading.Thread(target=steps)
    thread.start()
    while thread.is_alive():
        pump(0.02)
    pump(0.25)


# The small parts first.
check("no key to start with", cloud.load_key() == "")
cloud.save_key(TEST_KEY)
check("the key comes back", cloud.load_key() == TEST_KEY)
check("the key file doesn't contain the key", TEST_KEY.encode() not in cloud.KEY_FILE.read_bytes())
cloud.KEY_FILE.write_bytes(b"damaged")
check("a damaged key file is survived", cloud.load_key() == "")
cloud.forget_key()
check("forgetting removes the file", not cloud.KEY_FILE.exists())
check("a landscape region keeps its shape", cloud.send_size(800, 400) == (1536, 768), str(cloud.send_size(800, 400)))
check("a portrait region keeps its shape", cloud.send_size(300, 600) == (768, 1536), str(cloud.send_size(300, 600)))
check("Medium is the listed price", cloud.estimate_price(1920, 1080, "medium") == 0.053, str(cloud.estimate_price(1920, 1080, "medium")))
check("High costs more than Low", cloud.estimate_price(800, 800, "high") > cloud.estimate_price(800, 800, "low"))
wording = cloud.final_prompt(RenderParams(prompt="a red kettle", style="Clay model"))
check("the prompt has the look, the words and the drawing rule", wording.startswith("Clay model of a red kettle") and "proportions" in wording, wording)

window = window_module.MainWindow()
stage = window.preview
panel = stage.panel
window.look_box.setCurrentIndex(4)
window.hide_capture.setChecked(False)
window.capture_settings["folder"] = str(renders)
window.move(200, 60)
window.show()
pump(0.5)
work = window.screen().availableGeometry()

check("no key: no pill", not stage.final_pill.isVisible())

# Setting up in the Cloud tab, with real clicks.
click(stage.orb)
click(panel.cloud_tab)
check("the Cloud tab opens", panel.pages.currentIndex() == 1 and panel.key_box.isVisible())
if OUT:
    window.grab().save(str(OUT / "final_1_cloud_tab.png"))
check("Medium starts selected", panel.quality_buttons["medium"].isChecked())
check("the key box hides what's typed", panel.key_box.echoMode() == panel.key_box.EchoMode.Password)
panel.key_box.setText(f"  {TEST_KEY}  ")
click(panel.key_button)
check("Save keeps the key", cloud.load_key() == TEST_KEY)
check("the box is emptied after saving", panel.key_box.text() == "" and not panel.key_box.isEnabled())
check("the key isn't in the settings file", TEST_KEY not in capture_module.SETTINGS_FILE.read_text() if capture_module.SETTINGS_FILE.exists() else True)
click(panel.quality_buttons["high"])
check("quality is remembered", json.loads(capture_module.SETTINGS_FILE.read_text())["quality"] == "high")
click(panel.quality_buttons["medium"])
click(panel.local_tab)
check("the Local tab comes back", panel.pages.currentIndex() == 0 and window.look_box.isVisible())
stage.show_panel(False)
pump(0.2)

check("a key but no region: no pill", not stage.final_pill.isVisible())
window._region_picked(QRect(work.left() + 1300, work.top() + 200, 480, 320))
pump(0.8)
pill = stage.final_pill
check("key and region: the pill shows a price", pill.isVisible() and pill.text().startswith("Render final · ~$"), pill.text())
live_before = stage.current_image()
if OUT:
    window.grab().save(str(OUT / "final_2_pill.png"))

# Saying no at the first message.
click(pill)
check("the first use asks", Asker.asked == 1)
check("saying no sends nothing", len(Fal.requests) == 0 and window._final is None)

# Saying yes.
Asker.answer = QMessageBox.StandardButton.Yes
window.prompt_box.setPlainText("a red kettle")
window.look_box.setCurrentIndex(1)
pump(0.8)
window.look_box.setCurrentIndex(4)
pump(0.5)
click(pill)
check("the status says it's working", wait_for(lambda: len(Fal.requests) == 1))
wait_for(lambda: window._final is None)
sent = Fal.requests[-1]
check("it calls the right model", sent["path"] == "/openai/gpt-image-2/edit", sent["path"])
check("it sends the key", sent["headers"].get("authorization") == f"Key {TEST_KEY}")
check("it asks fal not to keep history", sent["headers"].get("x-fal-store-io") == "0")
check("it asks fal to delete files soon", '"expiration_duration_seconds": 3600' in sent["headers"].get("x-fal-object-lifecycle-preference", ""))
check("the key isn't sent to the file download", "authorization" not in Fal.file_headers)
check("the quality is Medium, not fal's default", sent["body"]["quality"] == "medium")
uri = sent["body"]["image_urls"][0]
check("the region goes as an image", uri.startswith("data:image/png;base64,"))
received = QImage.fromData(base64.b64decode(uri.split(",", 1)[1]))
check("the image is the full-size shape of the region", received.width() == 1536 and received.height() == 1024, f"{received.width()} × {received.height()}")
check("Filter sends a real look instead", sent["body"]["prompt"].startswith("Product render of a red kettle"), sent["body"]["prompt"])

# The result.
final = QImage.fromData(Fal.picture).convertToFormat(QImage.Format.Format_RGB888)
shown = stage.current_image().convertToFormat(QImage.Format.Format_RGB888)
check("the final shows in the viewfinder", shown == final)
check("the pill offers the way back", pill.text() == "Back to live", pill.text())
check("the final was saved straight away", len(list(renders.glob("*.png"))) == 1)
check("the final was copied", QGuiApplication.clipboard().image().convertToFormat(QImage.Format.Format_RGB888) == final)
check("the status says so", window.status.text() == "Saved and copied", window.status.text())
pump(0.6)
check("live rendering doesn't replace it", stage.current_image().convertToFormat(QImage.Format.Format_RGB888) == final)
pump(3.0)
check("the status then names the final", window.status.text().startswith("Final · 640 × 480"), window.status.text())
if OUT:
    window.grab().save(str(OUT / "final_3_result.png"))
click(pill)
check("Back to live resumes rendering", wait_for(lambda: window.status.text().startswith(("Live", "Paused"))), window.status.text())
pump(0.5)
check("the live view is back", stage.current_image().convertToFormat(QImage.Format.Format_RGB888) != final)
check("the pill shows the price again", pill.text().startswith("Render final"), pill.text())

# The first-use message only appears once.
asked = Asker.asked
Fal.mode = "slow"
click(pill)
check("it doesn't ask twice", Asker.asked == asked)
wait_for(lambda: len(Fal.requests) == 2)
pump(1.2)
check("the pill counts the wait", pill.text().startswith("Cancel · "), pill.text())
check("the status stays on the wait", window.status.text() == "Rendering final…", window.status.text())
if OUT:
    window.grab().save(str(OUT / "final_4_waiting.png"))
click(pill)
check("Cancel stops waiting", window._final is None and pill.text().startswith("Render final"), pill.text())
check("Cancel warns about the charge", "may still be charged" in window.status.text(), window.status.text())
check("Cancel tells fal", wait_for(lambda: Fal.cancels == 1))

# Things going wrong: each gets a plain sentence, and nothing is lost.
for mode, words in (("bad key", "didn't accept your key"), ("no credit", "no credit left"),
                    ("rejected", "couldn't use this request"), ("empty", "without an image")):
    Fal.mode = mode
    window.render_final()
    wait_for(lambda: window._final is None)
    check(f"{mode} is explained", words in window.status.text(), window.status.text())
    check(f"{mode} leaves the app ready", pill.text().startswith("Render final") and window.worker is not None)

saved_url = cloud.QUEUE_URL
cloud.QUEUE_URL = "http://127.0.0.1:9"
window.render_final()
wait_for(lambda: window._final is None)
check("no connection is explained", "Check your internet" in window.status.text(), window.status.text())
cloud.QUEUE_URL = saved_url

# Clearing the region while holding a final.
Fal.mode = "ok"
window.render_final()
wait_for(lambda: window._final is None)
check("a second final holds again", window._holding)
window.clear_region()
check("clearing leaves the final up", stage.current_image().convertToFormat(QImage.Format.Format_RGB888) == final)
check("clearing hides the pill", not pill.isVisible() and not window._holding)
window._region_picked(QRect(work.left() + 1300, work.top() + 200, 480, 320))
pump(0.6)
check("a new region goes live", window.worker is not None and not window._holding)

# Forgetting the key.
click(stage.orb)
click(panel.cloud_tab)
click(panel.key_button)
check("Forget removes the key", not cloud.KEY_FILE.exists() and window._fal_key == "")
check("the box is ready for a new key", panel.key_box.isEnabled())
click(panel.local_tab)
stage.show_panel(False)
pump(0.2)
check("no key: the pill goes", not pill.isVisible())

# Closing while a final is on its way must not hang.
cloud.save_key(TEST_KEY)
window._fal_key = TEST_KEY
Fal.mode = "slow"
window.render_final()
pump(0.2)
started = time.time()
window.close()
check("closing during a final is quick", time.time() - started < 3, f"{time.time() - started:.1f} s")
pump(0.3)

now = real_key_file.read_bytes() if real_key_file.exists() else None
check("your real key file wasn't touched", now == key_before)
server.shutdown()
shutil.rmtree(scratch, ignore_errors=True)
print("ALL PASSED" if all(results) else "SOME FAILED", flush=True)
sys.exit(0 if all(results) else 1)
