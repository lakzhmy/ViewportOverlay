"""Background renderer for FLUX.2 klein. The app starts this and talks to it through private pipes.

It opens no network ports and blocks model downloads. Each request is one line of JSON
followed by raw RGB bytes, and each reply has the same shape. Models are read from the
folder given as the first argument, and nothing there is changed.
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
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

DEVICE = "cuda"
LONG_SIDE = 768
STEPS = 2
REFERENCE_SIDE = 512
KEEP_PROMPTS = 16
FP4_VALUES = (0, 0.5, 1, 1.5, 2, 3, 4, 6, -0.0, -0.5, -1, -1.5, -2, -3, -4, -6)
QWEN3_CHAT = ("{% for m in messages %}<|im_start|>{{ m['role'] }}\n{{ m['content'] }}<|im_end|>\n{% endfor %}"
              "<|im_start|>assistant\n<think>\n\n</think>\n\n\n")  # the template engine drops the last line break


def send(header: dict, payload: bytes = b"") -> None:
    reply_pipe.write(json.dumps(header).encode() + b"\n")
    reply_pipe.write(payload)
    reply_pipe.flush()


def unblock_scales(stored, rows: int, columns: int):
    """Puts 4-bit block scales back into plain row order."""
    row_blocks, column_blocks = -(-rows // 128), -(-columns // 4)
    plain = stored.reshape(row_blocks * column_blocks, 32, 4, 4).transpose(1, 2)
    plain = plain.reshape(row_blocks, column_blocks, 128, 4).permute(0, 2, 1, 3)
    return plain.reshape(row_blocks * 128, column_blocks * 4)[:rows, :columns]


def unpack_fp4(torch, packed, block_scales, overall_scale):
    rows, half = packed.shape
    values = torch.tensor(FP4_VALUES, device=packed.device)
    high, low = (packed >> 4).long(), (packed & 15).long()
    weight = torch.stack([values[high], values[low]], dim=-1).reshape(rows, half * 2)
    scales = unblock_scales(block_scales.float(), rows, half * 2 // 16)
    return (weight.reshape(rows, -1, 16) * scales[:, :, None] * overall_scale.float()).reshape(rows, half * 2)


def load_text_encoder(torch, models: Path):
    """Unpacks the compressed encoder file into plain numbers."""
    from safetensors import safe_open
    from transformers import Qwen3Config, Qwen3ForCausalLM

    plain = {}
    with safe_open(models / "text_encoders" / "qwen_3_4b_fp8_mixed.safetensors", "pt", device=DEVICE) as f:
        names = set(f.keys())
        for name in names:
            if not name.endswith(".weight"):
                continue
            stem = name[: -len(".weight")]
            tensor = f.get_tensor(name)
            if tensor.dtype == torch.uint8:
                tensor = unpack_fp4(torch, tensor, f.get_tensor(f"{stem}.weight_scale"), f.get_tensor(f"{stem}.weight_scale_2"))
            elif f"{stem}.weight_scale" in names:
                tensor = tensor.float() * f.get_tensor(f"{stem}.weight_scale").float()
            plain[name] = tensor.to(torch.bfloat16)
    config = Qwen3Config(
        vocab_size=151936, hidden_size=2560, intermediate_size=9728, num_hidden_layers=36, num_attention_heads=32,
        num_key_value_heads=8, head_dim=128, rms_norm_eps=1e-6, rope_theta=1000000.0, max_position_embeddings=40960,
        tie_word_embeddings=True,
    )
    with torch.device(DEVICE):
        model = Qwen3ForCausalLM(config).to(torch.bfloat16)
    model.load_state_dict(plain, strict=False)
    model.tie_weights()
    return model.eval()


def load_tokenizer():
    from transformers import Qwen2TokenizerFast

    tokenizer = Qwen2TokenizerFast.from_pretrained(str(ROOT / "word_list"), local_files_only=True)
    tokenizer.chat_template = QWEN3_CHAT
    return tokenizer


def load_transformer(torch, models: Path):
    from diffusers import Flux2Transformer2DModel
    from diffusers.loaders.single_file_utils import convert_flux2_transformer_checkpoint_to_diffusers
    from safetensors.torch import load_file

    raw = load_file(models / "diffusion_models" / "flux-2-klein-4b.safetensors", device=DEVICE)
    converted = convert_flux2_transformer_checkpoint_to_diffusers(raw)
    with torch.device(DEVICE):
        model = Flux2Transformer2DModel(
            in_channels=128, num_layers=5, num_single_layers=20, attention_head_dim=128, num_attention_heads=24,
            joint_attention_dim=7680, guidance_embeds=False,
        )
    model.load_state_dict(converted)
    return model.to(torch.bfloat16).eval()


def load_vae(torch, models: Path):
    from diffusers import AutoencoderKLFlux2
    from safetensors.torch import load_file

    model = AutoencoderKLFlux2()
    model.load_state_dict(load_file(models / "vae" / "flux2-vae.safetensors"))
    return model.to(DEVICE, torch.bfloat16).eval()


def load_pipeline(torch, models: Path):
    from diffusers import FlowMatchEulerDiscreteScheduler, Flux2KleinPipeline

    scheduler = FlowMatchEulerDiscreteScheduler(
        num_train_timesteps=1000, shift=3.0, use_dynamic_shifting=True, base_shift=0.5, max_shift=1.15,
        base_image_seq_len=256, max_image_seq_len=4096, time_shift_type="exponential",
    )
    transformer = load_transformer(torch, models)  # the biggest file goes first, while the most memory is free
    return Flux2KleinPipeline(
        scheduler=scheduler, vae=load_vae(torch, models), text_encoder=load_text_encoder(torch, models),
        tokenizer=load_tokenizer(), transformer=transformer, is_distilled=True,
    )


def render_size(width: int, height: int) -> tuple:
    scale = LONG_SIDE / max(width, height)
    return max(round(width * scale / 16) * 16, 256), max(round(height * scale / 16) * 16, 256)


def main() -> None:
    import torch
    from PIL import Image

    pipe = load_pipeline(torch, Path(sys.argv[1]))
    prompts = {}
    references = {}

    def prompt_embeds(text: str):
        if text not in prompts:
            if len(prompts) >= KEEP_PROMPTS:
                prompts.clear()
            with torch.no_grad():
                prompts[text] = pipe.encode_prompt(prompt=text, device=DEVICE, num_images_per_prompt=1)[0]
        return prompts[text]

    def reference_image(path: str):
        if path not in references:
            image = Image.open(path).convert("RGB")
            image.thumbnail((REFERENCE_SIDE, REFERENCE_SIDE))
            references[path] = image
        return references[path]

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
            source = Image.frombytes("RGB", (width, height), data)
            source.thumbnail((LONG_SIDE, LONG_SIDE))
            images = [source]
            if request.get("reference"):
                images.append(reference_image(request["reference"]))
            out_width, out_height = render_size(width, height)
            result = pipe(
                image=images, prompt_embeds=prompt_embeds(request["prompt"]), width=out_width, height=out_height,
                num_inference_steps=STEPS, guidance_scale=1.0,
                generator=torch.Generator(DEVICE).manual_seed(request["seed"]),
            ).images[0].convert("RGB")
            send({"width": result.width, "height": result.height, "ms": (time.perf_counter() - started) * 1000}, result.tobytes())
        except Exception as error:
            send({"error": f"{type(error).__name__}: {error}"})


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        send({"error": f"{type(error).__name__}: {error}"})
        raise
