"""A simple image filter that stands in for AI, so the UI can run without a GPU."""
import numpy as np

from .base import Engine, RenderParams

MAX_SIDE = 768


def _shrink(frame: np.ndarray) -> np.ndarray:
    step = max(1, -(-max(frame.shape[:2]) // MAX_SIDE))
    return frame[::step, ::step]


def _box_blur(image: np.ndarray, radius: int) -> np.ndarray:
    if radius < 1:
        return image
    size = 2 * radius + 1
    for axis in (0, 1):
        pad = [(0, 0)] * image.ndim
        pad[axis] = (radius + 1, radius)
        total = np.cumsum(np.pad(image, pad, mode="edge"), axis=axis)
        length = total.shape[axis]
        upper = np.take(total, range(size, length), axis=axis)
        lower = np.take(total, range(0, length - size), axis=axis)
        image = (upper - lower) / size
    return image


class StandInEngine(Engine):
    name = "Stand-in filter (no AI)"
    uses_prompt = False

    def render(self, frame: np.ndarray, params: RenderParams) -> np.ndarray:
        follow = min(1.0, max(0.0, params.follow))
        image = _shrink(frame).astype(np.float32)

        soft = _box_blur(image, round((1.0 - follow) * 14))
        levels = 3 + round(follow * 13)
        painted = np.round(soft / 255.0 * levels) / levels * 255.0

        gray = image.mean(axis=2)
        edges = np.zeros_like(gray)
        edges[:, 1:] += np.abs(np.diff(gray, axis=1))
        edges[1:, :] += np.abs(np.diff(gray, axis=0))
        ink = np.clip(edges / 60.0, 0.0, 1.0) * follow

        result = painted * (1.0 - 0.85 * ink[..., None])
        return np.ascontiguousarray(np.clip(result, 0, 255).astype(np.uint8))
