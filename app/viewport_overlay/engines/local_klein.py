"""Runs FLUX.2 klein on this PC through its own background render program."""
import json
import os
from pathlib import Path

from .base import RenderParams
from .local_turbo import LocalTurboEngine

AI_FOLDER = Path(__file__).resolve().parents[3] / "KleinEngine"
MODELS = Path(os.environ.get("VIEWPORT_MODELS", r"C:\ComfyUI\models"))  # read only
SEED = 7

START = ("Turn image 1 into a photorealistic product render of a tall upright gaming terminal. "
         "Keep the exact silhouette, proportions, parts and viewing angle of image 1, and do not change its shape. "
         "Do not add buttons, controls, panels or any parts that are not in image 1. "
         "Ignore sketch construction lines and any grid. The screens are blank and switched off. ")
USE_REFERENCE = "From image 2 take only the materials and lighting mood, not the shape of its product. "
END = "No logos and no text. "


def build_prompt(params: RenderParams) -> str:
    notes = f"Design notes: {params.prompt}. " if params.prompt else ""
    return START + (USE_REFERENCE if params.reference else "") + notes + END + params.style


class LocalKleinEngine(LocalTurboEngine):
    name = "FLUX.2 klein"
    label = "Klein"
    folder = AI_FOLDER
    server_arguments = (str(MODELS),)

    def _request(self, width: int, height: int, params: RenderParams) -> bytes:
        return json.dumps({
            "width": width,
            "height": height,
            "prompt": build_prompt(params),
            "reference": params.reference,
            "seed": SEED,
        }).encode()
