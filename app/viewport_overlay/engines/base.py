"""The engine slot. Local, cloud and stand-in engines all follow this shape."""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RenderParams:
    prompt: str = ""
    style: str = ""
    follow: float = 0.33  # how closely Fast and Filter stay to the input: 0 = loose, 1 = strict
    reference: str = ""  # a look's reference image, for engines that use one
    seed: int = 7  # which variation of the design, for engines that use one


class Engine:
    name = "Engine"
    uses_prompt = True
    uses_seed = False
    slow_to_load = False  # kept loaded for a while after a region closes, so the next one starts at once
    settle_seconds = 0.0  # above zero, the engine only renders once the screen has been still this long

    def start(self) -> None:
        """Load models or open connections. Runs on the worker thread."""

    def stop(self) -> None:
        """Release whatever start() acquired."""

    def abort(self) -> None:
        """Interrupt slow work. Can be called from another thread."""

    def render(self, frame: np.ndarray, params: RenderParams) -> np.ndarray:
        """Take an RGB uint8 array (height, width, 3) and return one."""
        raise NotImplementedError
