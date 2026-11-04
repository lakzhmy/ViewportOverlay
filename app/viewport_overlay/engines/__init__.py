from .base import Engine, RenderParams
from .local_klein import LocalKleinEngine
from .local_turbo import LocalTurboEngine
from .standin import StandInEngine

# The first engine is the default. Add cloud engines here later.
ENGINES = [LocalKleinEngine, LocalTurboEngine, StandInEngine]

__all__ = ["ENGINES", "Engine", "LocalKleinEngine", "LocalTurboEngine", "RenderParams", "StandInEngine"]
