"""Runs SD-Turbo on this PC through the background render program."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from .base import Engine, RenderParams

AI_FOLDER = Path(__file__).resolve().parents[3] / "StreamDiffusionTest"
PYTHON = AI_FOLDER / "env" / "python.exe"
SERVER = AI_FOLDER / "render_server.py"
LOG = AI_FOLDER / "render_server.log"

# How much the AI may change the image. Lower numbers change it more.
LOOSEST_INDEX = 5
STRICTEST_INDEX = 35

STYLE_WORDS = {
    "Product render": "studio product render, clean background, soft lighting, high detail",
    "Clay model": "matte white clay model, soft studio light, monochrome",
    "Marker sketch": "industrial design marker sketch, loose confident lines, on paper",
    "Studio photo": "professional product photograph, softbox lighting, sharp focus",
}


def build_prompt(params: RenderParams) -> str:
    return ", ".join(part for part in (params.prompt, STYLE_WORDS.get(params.style, "")) if part)


def strength_index(follow: float) -> int:
    return round(LOOSEST_INDEX + (STRICTEST_INDEX - LOOSEST_INDEX) * follow)


class LocalTurboEngine(Engine):
    name = "Local SD-Turbo (this PC)"
    label = "Local"

    def __init__(self):
        self._process = None

    def start(self) -> None:
        if not PYTHON.exists() or not SERVER.exists():
            raise RuntimeError(f"AI install not found in {AI_FOLDER}")
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        with open(LOG, "wb") as log:
            self._process = subprocess.Popen(
                [str(PYTHON), str(SERVER)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=log,
                cwd=str(AI_FOLDER),
                creationflags=flags,
            )
        self._read_header()

    def stop(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        try:
            process.stdin.close()
            process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()

    def abort(self) -> None:
        process = self._process
        if process is not None:
            process.kill()

    def _read_header(self) -> dict:
        line = self._process.stdout.readline() if self._process else b""
        if not line:
            raise RuntimeError(f"The AI program stopped. Details are in {LOG.name}")
        header = json.loads(line)
        if "error" in header:
            raise RuntimeError(header["error"])
        return header

    def render(self, frame: np.ndarray, params: RenderParams) -> np.ndarray:
        height, width, _ = frame.shape
        request = {
            "width": width,
            "height": height,
            "prompt": build_prompt(params),
            "index": strength_index(params.follow),
        }
        pipe = self._process.stdin
        pipe.write(json.dumps(request).encode() + b"\n")
        pipe.write(frame.tobytes())
        pipe.flush()
        header = self._read_header()
        size = header["width"] * header["height"] * 3
        data = self._process.stdout.read(size)
        if len(data) != size:
            raise RuntimeError(f"The AI program stopped. Details are in {LOG.name}")
        return np.frombuffer(data, np.uint8).reshape(header["height"], header["width"], 3)
