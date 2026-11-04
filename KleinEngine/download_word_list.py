"""Fetches Qwen's word list from its official page. These are text files, not model weights."""
import urllib.request
from pathlib import Path

SOURCE = "https://huggingface.co/Qwen/Qwen3-4B/resolve/main"
FOLDER = Path(__file__).parent / "word_list"
FILES = ("tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt")

FOLDER.mkdir(exist_ok=True)
for name in FILES:
    request = urllib.request.Request(f"{SOURCE}/{name}", headers={"User-Agent": "ViewportOverlay-setup"})
    with urllib.request.urlopen(request, timeout=60) as reply:
        (FOLDER / name).write_bytes(reply.read())
    print("saved", name)
