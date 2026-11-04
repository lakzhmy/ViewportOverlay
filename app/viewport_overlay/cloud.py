"""Render final: one high-quality image from a cloud model, through fal.ai.

This runs on request, one image at a time. It costs money on your fal account, and
what's inside your region leaves this computer, so nothing here runs by itself.
"""
import base64
import ctypes
import json
import threading
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from pathlib import Path

import mss
import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, Qt, Signal
from PySide6.QtGui import QImage

from .engines import RenderParams

KEY_FILE = Path(__file__).resolve().parents[1] / "secrets.key"
QUEUE_URL = "https://queue.fal.run"
MODEL = "openai/gpt-image-2/edit"
QUALITIES = ("low", "medium", "high")
SEND_LONG_SIDE = 1536  # the model sizes its result from the picture it receives
WAIT_SECONDS = 300
POLL_SECONDS = 1.0
CALL_TIMEOUT = 60
KEEP_ON_FAL_SECONDS = 3600
FOLLOW_DRAWING = "Keep the exact shapes, proportions, layout and viewing angle of the input image."

# Dollars for one image, from fal's page for this model: (width, height): (low, medium, high).
PRICES = {
    (1024, 768): (0.011, 0.043, 0.151),
    (1024, 1024): (0.015, 0.061, 0.219),
    (1024, 1536): (0.018, 0.054, 0.178),
    (1920, 1080): (0.017, 0.053, 0.158),
}


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_char))]


def _crypt(function, data: bytes) -> bytes:
    """Windows encrypts this for your account, so only you, on this computer, can read it."""
    source = ctypes.create_string_buffer(data, len(data))
    blob_in = _Blob(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_char)))
    blob_out = _Blob()
    if not function(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        raise OSError("Windows couldn't protect the key")
    try:
        return ctypes.string_at(blob_out.data, blob_out.size)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.data)


def save_key(key: str) -> None:
    KEY_FILE.write_bytes(_crypt(ctypes.windll.crypt32.CryptProtectData, key.encode()))


def load_key() -> str:
    try:
        return _crypt(ctypes.windll.crypt32.CryptUnprotectData, KEY_FILE.read_bytes()).decode()
    except (OSError, UnicodeDecodeError):
        return ""


def forget_key() -> None:
    KEY_FILE.unlink(missing_ok=True)


def send_size(width: int, height: int) -> tuple:
    """The picture's size when sent: the same shape, with its long side at SEND_LONG_SIDE."""
    scale = SEND_LONG_SIDE / max(width, height)
    return max(round(width * scale), 1), max(round(height * scale), 1)


def estimate_price(width: int, height: int, quality: str) -> float:
    """The listed price for the closest listed size. fal's bill is the real figure."""
    sent = send_size(width, height)
    closest = min(PRICES, key=lambda size: abs(size[0] * size[1] - sent[0] * sent[1])
                  + abs(size[0] / size[1] - sent[0] / sent[1]) * 1_000_000)
    return PRICES[closest][QUALITIES.index(quality)]


def final_prompt(params: RenderParams) -> str:
    subject = f"{params.style} of {params.prompt}" if params.prompt else params.style
    return f"{subject}. {FOLLOW_DRAWING}"


def grab_region(region: dict) -> np.ndarray:
    with mss.MSS() as capture:
        shot = capture.grab(region)
    bgra = np.frombuffer(shot.bgra, np.uint8).reshape(shot.height, shot.width, 4)
    return np.ascontiguousarray(bgra[:, :, 2::-1])


def to_data_uri(rgb: np.ndarray) -> str:
    height, width, _ = rgb.shape
    image = QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888)
    sized = image.scaled(*send_size(width, height), Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    sized.save(buffer, "PNG")
    return "data:image/png;base64," + base64.b64encode(bytes(data)).decode()


def explain(error: Exception) -> str:
    """A plain sentence for the status line."""
    if isinstance(error, urllib.error.HTTPError):
        try:
            detail = json.loads(error.read()).get("detail", "")
        except (ValueError, AttributeError):
            detail = ""
        words = str(detail).lower()
        if "balance" in words or "credit" in words or error.code == 402:
            return "fal says there's no credit left on your account"
        if error.code in (401, 403):
            return "fal didn't accept your key"
        if error.code == 422:
            return "fal couldn't use this request. The image model may have changed"
        return f"fal had a problem (error {error.code})"
    if isinstance(error, (urllib.error.URLError, TimeoutError, OSError)):
        return "Can't reach fal. Check your internet connection"
    return str(error) or type(error).__name__


class FinalRender(QObject):
    """One image from fal, on a background thread that can't hold up closing the app."""

    finished = Signal(QImage)
    failed = Signal(str)

    def __init__(self, key: str, rgb: np.ndarray, params: RenderParams, quality: str):
        super().__init__()
        self._key = key
        self._rgb = rgb
        self._params = params
        self._quality = quality
        self._cancelled = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def cancel(self) -> None:
        self._cancelled.set()

    def _call(self, url: str, body: dict | None = None, method: str = "GET") -> dict:
        headers = {
            "Authorization": f"Key {self._key}",
            "Content-Type": "application/json",
            "User-Agent": "ViewportOverlay",
            "X-Fal-Store-IO": "0",  # keep this out of fal's 90-day request history
            "X-Fal-Object-Lifecycle-Preference": json.dumps({"expiration_duration_seconds": KEEP_ON_FAL_SECONDS}),
        }
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=CALL_TIMEOUT) as reply:
            return json.loads(reply.read() or b"{}")

    def _run(self) -> None:
        try:
            image = self._render()
            if image is not None and not self._cancelled.is_set():
                self.finished.emit(image)
        except Exception as error:  # shown in the window, so a failure is never silent
            if not self._cancelled.is_set():
                self.failed.emit(explain(error))

    def _render(self) -> QImage | None:
        job = self._call(f"{QUEUE_URL}/{MODEL}", {
            "prompt": final_prompt(self._params),
            "image_urls": [to_data_uri(self._rgb)],
            "image_size": "auto",
            "quality": self._quality,
            "num_images": 1,
            "output_format": "png",
        }, "POST")
        deadline = time.monotonic() + WAIT_SECONDS
        while self._call(job["status_url"]).get("status") != "COMPLETED":
            if self._cancelled.wait(POLL_SECONDS):
                self._call(job["cancel_url"], method="PUT")
                return None
            if time.monotonic() > deadline:
                raise RuntimeError("fal took too long, so this render was dropped")
        images = self._call(job["response_url"]).get("images")
        if not images:
            raise RuntimeError("fal finished without an image")
        with urllib.request.urlopen(images[0]["url"], timeout=CALL_TIMEOUT) as reply:  # no key sent here
            image = QImage.fromData(reply.read())
        if image.isNull():
            raise RuntimeError("fal's image couldn't be opened")
        return image
