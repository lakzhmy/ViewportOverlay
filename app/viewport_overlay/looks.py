"""The looks you pick from the orb. Each one knows which engine makes it.

An AI look keeps its wording and reference image in its own folder under app/looks,
so both can be changed there without touching the code.
"""
from dataclasses import dataclass
from pathlib import Path

from .engines import LocalKleinEngine, LocalTurboEngine, StandInEngine

LOOKS_FOLDER = Path(__file__).resolve().parents[1] / "looks"
WORDING_FILE = "wording.txt"
REFERENCE_FILES = ("reference.png", "reference.jpg", "reference.jpeg", "reference.webp")


def changed_at(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


@dataclass(frozen=True)
class Look:
    label: str
    first_wording: str  # used until the look has its own wording file, and if that file is emptied
    engine: type
    colors: tuple  # the orb's highlight, body and edge. Stand-ins until real sample renders exist.
    folder: str = ""

    @property
    def path(self) -> Path:
        return LOOKS_FOLDER / self.folder

    @property
    def style(self) -> str:
        if not self.folder:
            return self.first_wording
        try:
            wording = (self.path / WORDING_FILE).read_text(encoding="utf-8-sig", errors="replace").strip()
        except OSError:
            wording = ""
        return wording or self.first_wording

    @property
    def reference(self) -> str:
        if not self.folder:
            return ""
        return next((str(self.path / name) for name in REFERENCE_FILES if (self.path / name).exists()), "")

    def stamp(self) -> tuple:
        """Changes whenever the look's files do."""
        if not self.folder:
            return ()
        return tuple(changed_at(self.path / name) for name in (WORDING_FILE, *REFERENCE_FILES))

    def write_wording(self) -> None:
        if self.folder and not (self.path / WORDING_FILE).exists():
            self.path.mkdir(parents=True, exist_ok=True)
            (self.path / WORDING_FILE).write_text(self.first_wording + "\n", encoding="utf-8")


LOOKS = [
    Look("Casino", "Place it on a casino floor with warm lights and a softly blurred background.", LocalKleinEngine,
         ("#FFD9BD", "#F2703E", "#C8443A"), "casino"),
    Look("Black studio", "Place it on a pure black studio backdrop with dramatic rim light and a glossy reflective floor.",
         LocalKleinEngine, ("#6A6E76", "#2A2C30", "#0A0B0C"), "black studio"),
    Look("White studio", "Place it on a seamless white studio backdrop with soft even light.", LocalKleinEngine,
         ("#FFFFFF", "#E6E5E1", "#B4B7BC"), "white studio"),
    Look("Fast", "Product render", LocalTurboEngine, ("#F8D08A", "#DE8A3A", "#B4682A")),
    Look("Filter", "Filter", StandInEngine, ("#E6E5E1", "#8C9097", "#4A4D52")),
]
