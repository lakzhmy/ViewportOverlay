"""Keeping a render: to a folder, to the clipboard, and remembering those choices."""
import json
from datetime import datetime
from pathlib import Path

from PySide6.QtGui import QGuiApplication, QImage

SETTINGS_FILE = Path(__file__).resolve().parents[1] / "settings.json"
DEFAULTS = {"to_folder": True, "to_clipboard": True, "folder": "", "quality": "medium", "cloud_agreed": False, "seed": 7}


def load_settings() -> dict:
    """A missing or damaged settings file just means starting from the defaults."""
    try:
        return {**DEFAULTS, **json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))}
    except (OSError, TypeError, ValueError):
        return dict(DEFAULTS)


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def free_path(folder: Path, moment: datetime, seed: str = "") -> Path:
    """A file name from the date, time and seed. Captures in the same second get a number."""
    stem = f"ViewportOverlay_{moment:%Y-%m-%d_%H-%M-%S}" + (f"_seed{seed}" if seed else "")
    path = folder / f"{stem}.png"
    number = 2
    while path.exists():
        path = folder / f"{stem}_{number}.png"
        number += 1
    return path


def save_image(image: QImage, folder: Path) -> Path | None:
    """Saves a PNG and returns where it went, or None if the folder can't be written to."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    path = free_path(folder, datetime.now(), image.text("seed"))
    return path if image.save(str(path), "PNG") else None


def copy_image(image: QImage) -> None:
    QGuiApplication.clipboard().setImage(image)
