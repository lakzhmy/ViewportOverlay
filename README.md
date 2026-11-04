# ViewportOverlay

A Windows desktop app for designers. Draw a rectangle over any app, such as Rhino, PowerPoint or Miro, and a floating window shows a live AI render of what's under it.

**Status: early prototype.** It has only been tested on one PC, with an NVIDIA RTX 3090.

## What works today

- Draw, move, resize and clear the capture region
- A branded window with the render on top, glass controls and dark settings below
- Live render at about 10 frames per second with SD-Turbo, running on your own PC
- Editable prompt and style while it runs
- A "Follow my drawing" slider
- The app hides its own windows from the capture, with an on/off switch
- Rendering pauses when the screen isn't changing

While that switch is on, the windows also won't appear in screenshots, recordings or screen sharing.

## Planned

- Better shape accuracy with ControlNet
- Cloud engines and a "Render final" button using your own API key
- Product packs: trained styles and vocabulary for a product type

## Setup

This repository holds the code only. The installed software and AI models are not included, so you need to add them yourself. You'll need Windows, an NVIDIA graphics card and [Miniconda](https://docs.conda.io/projects/miniconda/).

1. **App:** create a Python 3.12 environment at `app\env`, then install `PySide6_Essentials`, `numpy` and `mss`.
2. **AI engine:** in `StreamDiffusionTest`, clone [StreamDiffusion](https://github.com/cumulo-autumn/StreamDiffusion) (tested at commit `b623251`) and create a Python 3.10 environment at `env`. Install StreamDiffusion, then `torch 2.1.0`, `torchvision 0.16.0` (both CUDA 12.1) and `xformers 0.0.22.post7`.
3. **Models:** put [SD-Turbo](https://huggingface.co/stabilityai/sd-turbo) in `StreamDiffusionTest\models\sd-turbo` and [TAESD](https://huggingface.co/madebyollin/taesd) in `StreamDiffusionTest\models\taesd`. Use `.safetensors` files only.
4. **Run:** double-click `app\Start Viewport Overlay.bat`.

Without the AI engine, you can still try the app by choosing the stand-in engine, which applies a simple filter.

## Credits and licences

- [StreamDiffusion](https://github.com/cumulo-autumn/StreamDiffusion) runs the real-time rendering.
- [SD-Turbo](https://huggingface.co/stabilityai/sd-turbo) is by Stability AI and has its own licence. Check its terms before any commercial use.
- [TAESD](https://github.com/madebyollin/taesd) is MIT licensed.
- [PySide6](https://doc.qt.io/qtforpython-6/) is LGPL licensed.
- [Inter Tight](https://github.com/rsms/inter-tight) is bundled under the SIL Open Font License (`app/assets/OFL.txt`).

No licence has been chosen for this project's own code yet.
