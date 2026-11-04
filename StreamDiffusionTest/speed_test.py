"""Measures SD-Turbo speed on a drawn test blockout. Uses only local files."""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ["HF_HOME"] = str(ROOT / ".hf_home")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
sys.path.insert(0, str(ROOT / "StreamDiffusion"))

import torch  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from utils.wrapper import StreamDiffusionWrapper  # noqa: E402

OUT = ROOT / "speed_test_output"
FRAMES = 100
PROMPT = (
    "modern coffee machine, brushed metal body, glass panel, "
    "soft edge lighting, studio product render, clean background"
)
NEGATIVE = "vintage, cartoon, text, blurry"
SETTINGS = {"1_step": [35], "2_steps": [32, 45], "strength_t25": [25], "strength_t15": [15], "strength_t5": [5]}


def blockout() -> Image.Image:
    image = Image.new("RGB", (512, 512), (225, 225, 228))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((166, 40, 346, 100), 18, fill=(150, 150, 156))   # top section
    draw.rounded_rectangle((156, 104, 356, 330), 14, fill=(95, 96, 104))    # main body
    draw.rounded_rectangle((176, 122, 336, 310), 8, fill=(35, 38, 48))      # display
    draw.polygon([(146, 334), (366, 334), (386, 386), (126, 386)], fill=(120, 121, 128))  # deck
    draw.rectangle((150, 390, 362, 490), fill=(80, 81, 88))                 # base
    return image


def measure(name: str, steps: list, source: Image.Image) -> None:
    torch.cuda.reset_peak_memory_stats()
    stream = StreamDiffusionWrapper(
        model_id_or_path=str(ROOT / "models" / "sd-turbo"),
        vae_id=str(ROOT / "models" / "taesd"),
        t_index_list=steps,
        frame_buffer_size=1,
        width=512,
        height=512,
        warmup=10,
        acceleration="xformers",
        mode="img2img",
        use_denoising_batch=True,
        cfg_type="none",
        seed=2,
        output_type="pil",
    )
    stream.prepare(prompt=PROMPT, negative_prompt=NEGATIVE, num_inference_steps=50, guidance_scale=1.0)

    tensor = stream.preprocess_image(source)
    for _ in range(len(steps) + 10):
        result = stream.stream(tensor)

    torch.cuda.synchronize()
    started = time.perf_counter()
    for _ in range(FRAMES):
        result = stream.stream(tensor).cpu()
    seconds = time.perf_counter() - started

    stream.postprocess_image(result, output_type="pil").save(OUT / f"{name}.png")
    peak = torch.cuda.max_memory_allocated() / 1024**3
    print(f"RESULT {name}: {FRAMES / seconds:.1f} fps, {seconds / FRAMES * 1000:.1f} ms per frame, "
          f"peak VRAM {peak:.2f} GB", flush=True)
    del stream
    torch.cuda.empty_cache()


def main() -> None:
    OUT.mkdir(exist_ok=True)
    source = blockout()
    source.save(OUT / "input.png")
    print("GPU", torch.cuda.get_device_name(0), flush=True)
    for name, steps in SETTINGS.items():
        measure(name, steps, source)


if __name__ == "__main__":
    main()
