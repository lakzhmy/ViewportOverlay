"""Background renderer. The app starts this and talks to it through private pipes.

It opens no network ports and blocks model downloads. Each request is one line
of JSON followed by raw RGB bytes, and each reply has the same shape.
"""
import json
import os
import sys
import time
from pathlib import Path

# Libraries print to stdout, so keep the real one for images and redirect the rest.
reply_pipe = os.fdopen(os.dup(1), "wb")
os.dup2(2, 1)
request_pipe = sys.stdin.buffer

ROOT = Path(__file__).resolve().parent
os.environ["HF_HOME"] = str(ROOT / ".hf_home")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
sys.path.insert(0, str(ROOT / "StreamDiffusion"))

SIZE = 512
START_INDEX = 15


def send(header: dict, payload: bytes = b"") -> None:
    reply_pipe.write(json.dumps(header).encode() + b"\n")
    reply_pipe.write(payload)
    reply_pipe.flush()


def fit_to_square(image):
    """Place the image on a square canvas without changing its proportions."""
    from PIL import Image, ImageOps, ImageStat

    fitted = ImageOps.contain(image, (SIZE, SIZE))
    background = tuple(ImageStat.Stat(image.resize((8, 8))).median)
    canvas = Image.new("RGB", (SIZE, SIZE), background)
    left = (SIZE - fitted.width) // 2
    top = (SIZE - fitted.height) // 2
    canvas.paste(fitted, (left, top))
    return canvas, (left, top, left + fitted.width, top + fitted.height)


def main() -> None:
    from PIL import Image

    from utils.wrapper import StreamDiffusionWrapper

    stream = StreamDiffusionWrapper(
        model_id_or_path=str(ROOT / "models" / "sd-turbo"),
        vae_id=str(ROOT / "models" / "taesd"),
        t_index_list=[START_INDEX],
        frame_buffer_size=1,
        width=SIZE,
        height=SIZE,
        warmup=10,
        acceleration="xformers",
        mode="img2img",
        use_denoising_batch=True,
        cfg_type="none",
        seed=2,
        output_type="pil",
    )
    prompt = ""
    index = START_INDEX
    stream.prepare(prompt=prompt, num_inference_steps=50, guidance_scale=1.0)
    send({"ready": True})

    while True:
        line = request_pipe.readline()
        if not line:  # the app closed, so stop too
            return
        request = json.loads(line)
        width, height = request["width"], request["height"]
        data = request_pipe.read(width * height * 3)
        started = time.perf_counter()
        try:
            new_prompt, new_index = request["prompt"], request["index"]
            if new_index != index:
                index, prompt = new_index, new_prompt
                stream.stream.t_list = [index]
                stream.prepare(prompt=prompt, num_inference_steps=50, guidance_scale=1.0)
            elif new_prompt != prompt:
                prompt = new_prompt
                stream.stream.update_prompt(prompt)

            canvas, box = fit_to_square(Image.frombytes("RGB", (width, height), data))
            tensor = stream.preprocess_image(canvas)
            result = stream.postprocess_image(stream.stream(tensor).cpu(), output_type="pil")
            result = result.crop(box).convert("RGB")
            send(
                {"width": result.width, "height": result.height, "ms": (time.perf_counter() - started) * 1000},
                result.tobytes(),
            )
        except Exception as error:
            send({"error": f"{type(error).__name__}: {error}"})


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        send({"error": f"{type(error).__name__}: {error}"})
        raise
