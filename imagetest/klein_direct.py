"""FLUX.2 klein 4B straight from your files, through diffusers. No ComfyUI code, and nothing goes online."""
import gc
import os
import time
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

import torch
from diffusers import AutoencoderKLFlux2, FlowMatchEulerDiscreteScheduler, Flux2KleinPipeline, Flux2Transformer2DModel
from diffusers.loaders.single_file_utils import convert_flux2_transformer_checkpoint_to_diffusers
from safetensors import safe_open
from safetensors.torch import load_file
from transformers import Qwen2TokenizerFast, Qwen3Config, Qwen3ForCausalLM

MODELS = Path(r"C:\ComfyUI\models")
WORD_LIST = Path(r"C:\ComfyUI\comfy\text_encoders\qwen25_tokenizer")  # plain data files only, no code runs from here
DEVICE = "cuda"
DTYPE = torch.bfloat16
FP4_VALUES = torch.tensor([0, 0.5, 1, 1.5, 2, 3, 4, 6, -0.0, -0.5, -1, -1.5, -2, -3, -4, -6])
QWEN3_CHAT = ("{% for m in messages %}<|im_start|>{{ m['role'] }}\n{{ m['content'] }}<|im_end|>\n{% endfor %}"
              "<|im_start|>assistant\n<think>\n\n</think>\n\n\n")  # the template engine drops the last line break


def unblock_scales(stored: torch.Tensor, rows: int, columns: int) -> torch.Tensor:
    """Puts 4-bit block scales back into plain row order."""
    row_blocks, column_blocks = -(-rows // 128), -(-columns // 4)
    plain = stored.reshape(row_blocks * column_blocks, 32, 4, 4).transpose(1, 2)
    plain = plain.reshape(row_blocks, column_blocks, 128, 4).permute(0, 2, 1, 3)
    return plain.reshape(row_blocks * 128, column_blocks * 4)[:rows, :columns]


def unpack_fp4(packed, block_scales, overall_scale) -> torch.Tensor:
    rows, half = packed.shape
    values = FP4_VALUES.to(packed.device)
    high, low = (packed >> 4).long(), (packed & 15).long()
    weight = torch.stack([values[high], values[low]], dim=-1).reshape(rows, half * 2)
    scales = unblock_scales(block_scales.float(), rows, half * 2 // 16)
    return (weight.reshape(rows, -1, 16) * scales[:, :, None] * overall_scale.float()).reshape(rows, half * 2)


def load_text_encoder() -> Qwen3ForCausalLM:
    """Unpacks the compressed encoder file into plain numbers."""
    plain = {}
    with safe_open(MODELS / "text_encoders/qwen_3_4b_fp8_mixed.safetensors", "pt", device=DEVICE) as f:
        names = set(f.keys())
        for name in names:
            if not name.endswith(".weight"):
                continue
            stem = name[: -len(".weight")]
            tensor = f.get_tensor(name)
            if tensor.dtype == torch.uint8:
                tensor = unpack_fp4(tensor, f.get_tensor(f"{stem}.weight_scale"), f.get_tensor(f"{stem}.weight_scale_2"))
            elif f"{stem}.weight_scale" in names:
                tensor = tensor.float() * f.get_tensor(f"{stem}.weight_scale").float()
            plain[name] = tensor.to(DTYPE)
    config = Qwen3Config(
        vocab_size=151936, hidden_size=2560, intermediate_size=9728, num_hidden_layers=36, num_attention_heads=32,
        num_key_value_heads=8, head_dim=128, rms_norm_eps=1e-6, rope_theta=1000000.0, max_position_embeddings=40960,
        tie_word_embeddings=True,
    )
    with torch.device(DEVICE):
        model = Qwen3ForCausalLM(config).to(DTYPE)
    missing, unexpected = model.load_state_dict(plain, strict=False)
    print("encoder missing", [m for m in missing if "lm_head" not in m][:4], "unexpected", unexpected[:4], flush=True)
    model.tie_weights()
    return model.to(DEVICE, DTYPE).eval()


def load_tokenizer() -> Qwen2TokenizerFast:
    tokenizer = Qwen2TokenizerFast.from_pretrained(str(WORD_LIST), local_files_only=True)
    tokenizer.add_tokens(["<tool_response>", "</tool_response>", "<think>", "</think>"])  # the extra Qwen 3 entries
    tokenizer.chat_template = QWEN3_CHAT
    return tokenizer


def load_transformer() -> Flux2Transformer2DModel:
    raw = load_file(MODELS / "diffusion_models/flux-2-klein-4b.safetensors", device=DEVICE)
    converted = convert_flux2_transformer_checkpoint_to_diffusers(raw)
    with torch.device(DEVICE):
        model = Flux2Transformer2DModel(
            in_channels=128, num_layers=5, num_single_layers=20, attention_head_dim=128, num_attention_heads=24,
            joint_attention_dim=7680, guidance_embeds=False,
        )
    missing, unexpected = model.load_state_dict(converted, strict=False)
    print("transformer missing", missing[:4], "unexpected", unexpected[:4], flush=True)
    del raw, converted
    return model.to(DTYPE).eval()


def load_vae() -> AutoencoderKLFlux2:
    model = AutoencoderKLFlux2()
    missing, unexpected = model.load_state_dict(load_file(MODELS / "vae/flux2-vae.safetensors"), strict=False)
    print("vae missing", missing[:4], "unexpected", unexpected[:4], flush=True)
    return model.to(DEVICE, DTYPE).eval()


def load_pipeline() -> Flux2KleinPipeline:
    started = time.time()
    scheduler = FlowMatchEulerDiscreteScheduler(
        num_train_timesteps=1000, shift=3.0, use_dynamic_shifting=True, base_shift=0.5, max_shift=1.15,
        base_image_seq_len=256, max_image_seq_len=4096, time_shift_type="exponential",
    )
    transformer = load_transformer()  # the biggest file goes first, while the most memory is free
    gc.collect()
    vae = load_vae()
    text_encoder = load_text_encoder()
    gc.collect()
    pipe = Flux2KleinPipeline(
        scheduler=scheduler, vae=vae, text_encoder=text_encoder, tokenizer=load_tokenizer(),
        transformer=transformer, is_distilled=True,
    )
    print(f"loaded in {time.time() - started:.1f} s", flush=True)
    return pipe
