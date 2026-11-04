"""The looks you pick from the orb. Each one knows which engine makes it."""
from dataclasses import dataclass

from pathlib import Path

from .engines import LocalKleinEngine, LocalTurboEngine, StandInEngine

LOOKS_FOLDER = Path(__file__).resolve().parents[1] / "looks"


@dataclass(frozen=True)
class Look:
    label: str
    style: str
    engine: type
    colors: tuple  # the orb's highlight, body and edge. Stand-ins until real sample renders exist.
    folder: str = ""  # where this look keeps its reference image

    @property
    def reference(self) -> str:
        path = LOOKS_FOLDER / self.folder / "reference.png"
        return str(path) if self.folder and path.exists() else ""


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
