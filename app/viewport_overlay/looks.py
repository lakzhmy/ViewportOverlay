"""The looks you pick from the orb. Each one knows which engine makes it."""
from dataclasses import dataclass

from .engines import LocalTurboEngine, StandInEngine


@dataclass(frozen=True)
class Look:
    label: str
    style: str
    engine: type
    colors: tuple  # the orb's highlight, body and edge. Stand-ins until real sample renders exist.


LOOKS = [
    Look("Product", "Product render", LocalTurboEngine, ("#FFD9BD", "#F2703E", "#C8443A")),
    Look("Clay", "Clay model", LocalTurboEngine, ("#F8D08A", "#DE8A3A", "#B4682A")),
    Look("Marker", "Marker sketch", LocalTurboEngine, ("#A5765A", "#6A3826", "#3F2018")),
    Look("Studio", "Studio photo", LocalTurboEngine, ("#F9B4D3", "#DF4E97", "#B52E78")),
    Look("Filter", "Filter", StandInEngine, ("#E6E5E1", "#8C9097", "#4A4D52")),
]
