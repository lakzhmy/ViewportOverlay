"""Round two: three fixed looks, a no-extra-parts rule, clean inputs and speed. Local only.

Run with the genai Python. Results go to the git-ignored app/reference folder.
"""
import gc
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import klein_direct as k

ROOT = Path(__file__).resolve().parents[1] / "app" / "reference"
SOURCE = ROOT / "gaming cabinet"
OUT = ROOT / "test results" / "klein 2"
OUT.mkdir(parents=True, exist_ok=True)
SEED = 7
INPUTS = {
    "S1": ("sketch", "115426"), "S2": ("sketch", "115439"), "S3": ("sketch", "115505"), "S4": ("sketch", "115835"),
    "C1": ("cad screenshot", "115535"), "C2": ("cad screenshot", "115922"), "C3": ("cad screenshot", "121338"),
}
START = ("Turn image 1 into a photorealistic product render of a tall upright gaming terminal. "
         "Keep the exact silhouette, proportions, parts and viewing angle of image 1, and do not change its shape. ")
NO_EXTRAS = "Do not add buttons, controls, panels or any parts that are not in image 1. "
END = ("Ignore sketch construction lines and any grid. The screens are blank and switched off. "
       "From image 2 take only the materials and lighting mood, not the shape of its product. No logos and no text. ")
LOOKS = {
    "white": ("generated image", "115603", "Place it on a seamless white studio backdrop with soft even light."),
    "black": ("generated image", "115739", "Place it on a pure black studio backdrop with dramatic rim light and a glossy reflective floor."),
    "casino": ("generated image", "115632", "Place it on a casino floor with warm lights and a softly blurred background."),
}


def open_input(name):
    folder, stamp = INPUTS[name]
    return Image.open(next((SOURCE / folder).glob(f"*{stamp}.png"))).convert("RGB")


def open_reference(look):
    folder, stamp, _ = LOOKS[look]
    image = Image.open(next((SOURCE / folder).glob(f"*{stamp}.png"))).convert("RGB")
    image.thumbnail((768, 768))
    return image


def without_red(image):
    """Paints the red guide line out of C2 using the white page behind it."""
    pixels = np.array(image).astype(int)
    red = (pixels[..., 0] > 120) & (pixels[..., 0] - pixels[..., 1] > 50) & (pixels[..., 0] - pixels[..., 2] > 50)
    grown = red.copy()
    for shift in (-2, -1, 1, 2):
        grown |= np.roll(red, shift, 0) | np.roll(red, shift, 1)
    pixels[grown] = 255
    return Image.fromarray(pixels.astype(np.uint8))


def out_size(image, long_side):
    scale = long_side / max(image.size)
    return tuple(max(round(side * scale / 16) * 16, 256) for side in image.size)


def main():
    pipe = k.load_pipeline()
    check = pipe.tokenizer.apply_chat_template([{"role": "user", "content": "x"}], tokenize=False, add_generation_prompt=True)
    assert check.endswith("</think>\n\n"), repr(check)
    prompts = {look: START + NO_EXTRAS + END + words for look, (_, _, words) in LOOKS.items()}
    prompts["white no rule"] = START + END + LOOKS["white"][2]
    prompts["black no rule"] = START + END + LOOKS["black"][2]
    with torch.no_grad():
        embeds = {name: pipe.encode_prompt(prompt=text, device=k.DEVICE, num_images_per_prompt=1)[0] for name, text in prompts.items()}
    (OUT / "prompts.json").write_text(json.dumps(prompts, indent=1))
    pipe.text_encoder = None
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    references = {look: open_reference(look) for look in LOOKS}
    log = {}

    def render(tag, source, look, embed, seed=SEED, long_side=1344, steps=4):
        width, height = out_size(source, long_side)
        started = time.time()
        result = pipe(image=[source, references[look]], prompt_embeds=embeds[embed], height=height, width=width,
                      num_inference_steps=steps, guidance_scale=1.0, generator=torch.Generator(k.DEVICE).manual_seed(seed)).images[0]
        torch.cuda.synchronize()
        seconds = time.time() - started
        result.save(OUT / f"{tag}.png")
        log[tag] = {"seconds": round(seconds, 2), "size": [width, height], "steps": steps}
        print(f"{tag} {seconds:.1f} s {width}x{height}", flush=True)
        return seconds

    for name in INPUTS:
        for look in LOOKS:
            render(f"{name}_{look}", open_input(name), look, look)
    clean = without_red(open_input("C2"))
    clean.save(OUT / "C2 without red line.png")
    for look in LOOKS:
        render(f"C2clean_{look}", clean, look, look)
    for name, look in (("C3", "white"), ("C3", "black"), ("S1", "white"), ("S1", "black")):
        render(f"{name}_{look}_norule", open_input(name), look, f"{look} no rule")
    for seed in (8, 9):
        for name in ("C3", "C1"):
            render(f"{name}_white_seed{seed}", open_input(name), "white", "white", seed=seed)

    speed = {}
    source = open_input("C3")
    for long_side, steps in ((1344, 4), (1024, 4), (768, 4), (512, 4), (768, 2), (512, 2)):
        small = source.copy()
        small.thumbnail((long_side, long_side))
        small_reference = references["white"].copy()
        small_reference.thumbnail((min(long_side, 512), min(long_side, 512)))
        keep = references["white"]
        references["white"] = small_reference
        times = [render(f"speed_{long_side}_{steps}step", small, "white", "white", long_side=long_side, steps=steps) for _ in range(3)]
        references["white"] = keep
        speed[f"{long_side} long side, {steps} steps"] = round(min(times), 2)
    log["speed"] = speed
    log["peak_gb"] = round(torch.cuda.max_memory_allocated() / 2**30, 1)
    (OUT / "times.json").write_text(json.dumps(log, indent=1))
    print(speed, "peak GB", log["peak_gb"], flush=True)
    sheets()


def sheet(name, rows, heads, cell_w=330, cell_h=500):
    canvas = Image.new("RGB", (cell_w * len(heads), 26 + cell_h * len(rows)), "white")
    pen = ImageDraw.Draw(canvas)
    for column, head in enumerate(heads):
        pen.text((column * cell_w + 6, 6), head, fill="black")
    for row, cells in enumerate(rows):
        for column, image in enumerate(cells):
            image = image.copy()
            image.thumbnail((cell_w - 8, cell_h - 12))
            canvas.paste(image, (column * cell_w + 4, 26 + row * cell_h + 4))
    canvas.save(OUT / f"{name}.png")


def sheets():
    load = lambda tag: Image.open(OUT / f"{tag}.png").convert("RGB")
    ghost = lambda source, result: Image.blend(result, source.resize(result.size), 0.5)
    heads = ["INPUT", "White studio", "White over input", "Black studio", "Casino"]

    def row(name):
        source = open_input(name)
        white = load(f"{name}_white")
        return [source, white, ghost(source, white), load(f"{name}_black"), load(f"{name}_casino")]

    sheet("1 sketches", [row(n) for n in ("S1", "S2", "S3", "S4")], heads)
    sheet("2 cad", [row(n) for n in ("C1", "C2", "C3")], heads)
    clean = load("C2 without red line")
    sheet("3 tests", [
        [clean, load("C2clean_white"), load("C2clean_black"), load("C2clean_casino"), load("C2_white")],
        [open_input("C3"), load("C3_white"), load("C3_white_norule"), load("C3_black"), load("C3_black_norule")],
        [open_input("S1"), load("S1_white"), load("S1_white_norule"), load("S1_black"), load("S1_black_norule")],
        [open_input("C3"), load("C3_white"), load("C3_white_seed8"), load("C3_white_seed9"), load("C1_white")],
        [open_input("C1"), load("C1_white"), load("C1_white_seed8"), load("C1_white_seed9")],
    ], ["INPUT", "row 1 no red / rows 2-3 rule / rows 4-5 seed 7", "no rule or seed 8", "with rule or seed 9", "no rule or compare"])
    sizes = ["speed_1344_4step", "speed_1024_4step", "speed_768_4step", "speed_512_4step", "speed_768_2step", "speed_512_2step"]
    sheet("4 speed", [[load(tag) for tag in sizes]], [tag.replace("speed_", "") for tag in sizes], cell_w=300, cell_h=640)


if __name__ == "__main__":
    main()
