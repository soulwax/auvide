# auvide

**AI video upscaler + vibrant HDR10 remapper.**

`auvide` takes any video, upscales every frame 2×/3×/4× with
[Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) (GPU, via Vulkan), and
re-encodes it to a proper **HDR10** file (BT.2020 primaries + PQ transfer,
10-bit HEVC) with a configurable vibrance grade. The original audio is muxed
back in untouched.

> **About "HDR from SDR":** an 8-bit SDR source has no real HDR detail to
> recover. `auvide` does a clean inverse tone-map into an HDR10 container and
> a saturation/highlight boost, so the result is flagged as HDR and looks
> punchier on an HDR display. It is a stylized remap, not reconstruction.

---

## Setup

Requires **Python 3.9+**, a **Vulkan-capable GPU** (any modern integrated or
discrete GPU), and three prerequisites on your **PATH** — auvide does not bundle
binaries, it uses your system package manager (canonical, fast, and cross-platform):

| tool | why |
|------|-----|
| `ffmpeg` + `ffprobe` | decode / encode / color pipeline |
| `realesrgan-ncnn-vulkan` | AI upscaler (GPU) |

**Install the prerequisites:**

```powershell
# Windows (scoop is canonical) — installs ffmpeg + realesrgan and caches models
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```
```bash
# macOS
brew install ffmpeg realesrgan-ncnn-vulkan
# Arch
sudo pacman -S ffmpeg && yay -S realesrgan-ncnn-vulkan     # realesrgan from AUR
# Ubuntu / Debian
sudo apt install ffmpeg     # + realesrgan-ncnn-vulkan from the upstream release
# Fedora
sudo dnf install ffmpeg     # + realesrgan-ncnn-vulkan from the upstream release
```

The **Real-ESRGAN models** (`.param`/`.bin`, data not binaries) are cached in
`%LOCALAPPDATA%\auvide\models` (or `~/.cache/auvide/models`). `setup.ps1` fetches
them; on other OSes drop the model files there, or install a realesrgan build
that ships models beside its binary. auvide checks all of this up front and
prints exactly what's missing.

Then install the engine package (only Pillow as a real dependency; everything
else is stdlib): `pip install ./engine` (or, from a checkout, `pip install -e
./engine` for development). This exposes the `auvide` console script and the
`auvide` importable package. `uv` users can skip the install and run directly:
`uv run --project ./engine --python 3.12 -m auvide.cli ...`.

## Project layout

```
engine/   <- the auvide Python package (src/auvide/) — the ONLY copy of the
             engine source; CLI, legacy GUI, and the Tauri app all import it
desktop/  <- Tauri 2 desktop app (Vite/TypeScript frontend + Rust backend);
             stages a build-time copy of engine/ into desktop/src-tauri/engine/
desktop/legacy/gui.py  <- the Tkinter GUI, kept for reference — no new
                          features land here; the Tauri app is the actively
                          developed GUI
input/    <- put source videos here (CLI/GUI auto-pick a lone video)
output/   <- renders land here
```

Binaries are **not** here — they live on your PATH (see Setup).

With one video in `input/`, just run `auvide` — no arguments needed. The GUI
auto-loads it too.

---

## Usage

```powershell
# defaults: 2x, animevideo model, vibrant HDR10
auvide "movie.mp4"

# explicit
auvide "movie.mp4" -o "movie_hdr.mp4" --scale 2 --vibrance vibrant

# sharper photographic model (4x native, slower, more VRAM)
auvide "movie.mp4" --model x4plus --scale 2

# stay SDR, just upscale
auvide "movie.mp4" --hdr off

# resume an interrupted run
auvide "movie.mp4" --resume
```

Or drag a video file onto **`desktop/run.bat`** to process it with defaults.

### Desktop app

The actively developed GUI is a Tauri 2 desktop app in `desktop/` (Vite +
TypeScript frontend, Rust backend). It's a thin wrapper — it collects options,
launches the `auvide` engine as a subprocess, streams its log, and shows a
progress bar driven by the CLI's per-chunk output.

```powershell
# From the repository root: checks Bun/Rust, prepares dependencies and the
# verified uv sidecar, then opens the GUI. No global Python or uv is required.
.\run-gui.bat

# Or, from desktop/: .\run-desktop.bat
# Add --check to verify prerequisites without opening the app.
```

On its first engine request, the desktop app installs its managed Python 3.12
runtime and engine environment under your app-data directory. Later launches
reuse that environment and invoke its Python directly. FFmpeg and Real-ESRGAN
bootstrap is the next setup step; use `setup.ps1` until it is integrated.

### Legacy GUI

The original Tkinter front-end (`desktop/legacy/gui.py`) still works and gets
no new features — the Tauri app above is the one to use going forward.

```powershell
# uv provides Python + tkinter + pillow (no system Python needed)
cd desktop
uv run --python 3.12 --with ./../engine --with pillow legacy/gui.py
```

The legacy GUI remains available through **`desktop/run-gui.bat`**. Two tabs:

- **Render** — pick an input, set scale / model / HDR / encoder, hit **Start**.
  "Show command" prints the equivalent CLI; **Cancel** stops the run (re-launch
  with Resume ticked to continue).
- **Render** extras: **encoder preset**, **include-audio**, **open-when-done**,
  **notify + sleep-when-done** (for overnight jobs), a **Trim** (start/length)
  for quick test renders, and **Batch** (render every video in `input/`).
- **Grade & Preview** — the frame loads automatically; **scrub the timeline**
  (or ◀ ▶) to check the grade anywhere in the clip. Dial the look with live
  sliders (exposure, saturation, vibrance, contrast, midtones, warmth, tint,
  sharpen) and watch a real **before/after** — drag the image to move the wipe
  divider, **hold Space** to flash the untouched original, **double-click** any
  slider to reset it, and **Save…** your look as a named preset (right-click to
  delete). Hit **AI upscale** + **1:1** to pixel-peek the actual Real-ESRGAN
  detail before committing, and **Scopes** for a live waveform + vectorscope.
  The grade you tune is exactly what the render applies (both use `grade.py`).
- The **Style** chips (top) apply whole looks one-tap; the **Pipeline** line
  shows the active stage chain; **Save/Load recipe** persists a full job as a
  versioned JSON document. Older flat recipe JSON remains supported on load.

No GUI? Get the same comparison from the CLI without a full run:

```powershell
auvide --preview            # before/after stills at 20/50/80%
auvide --preview --at 25,95 # at chosen seconds -> output/preview/
```

### Options

| flag | default | meaning |
|------|---------|---------|
| `--style NAME` | | one-tap look (Vibrant HDR / Cinematic / Natural / Punchy SDR / Sharp Photo / Clean / **Smooth 60**); explicit flags still win |
| `--interpolate {2,3,4}` | `0` | RIFE AI frame interpolation — smoother motion / ~60fps |
| `--slowmo` | | with `--interpolate`: slow-motion (keep fps) instead of smoother |
| `--target NAME` | `source` | delivery preset: crop/pad + SDR for platforms (reel · tiktok · post · story · x · web · youtube) |
| `--lut FILE` | | apply a 3D LUT (`.cube`) after the grade |
| `--deinterlace` | | restore: deinterlace (bwdif) |
| `--denoise {off,light,medium,strong}` | `off` | restore: denoise before upscaling |
| `--stabilize` | | restore: stabilize shaky footage (vidstab, 2-pass) |
| `--recipe FILE` / `--save-recipe FILE` | | load a legacy or versioned job recipe / save a versioned full-job recipe (`.json`) |
| `--scale {2,3,4}` | `2` | upscale factor |
| `--model {animevideo,x4plus,x4plus-anime}` | `animevideo` | `animevideo` = fast, denoises, best for real video; `x4plus` = sharper photographic detail |
| `--vibrance {none,subtle,vibrant,max}` | `vibrant` | grade **preset** — the base for the knobs below |
| `--hdr {on,off}` | `on` | HDR10 remap, or stay SDR BT.709 |
| `--encoder {x265,qsv}` | `x265` | `x265` = software (best HDR fidelity); `qsv` = Intel Quick Sync GPU (faster) |
| `--crf N` | `19` | quality, lower = better (18–23 typical) |
| **grade overrides** | *(preset)* | fine-tune the look; leave unset to use the preset |
| `--saturation F` | | `1.0` = unchanged |
| `--vibrance-amt F` | | selective saturation, `0..1` (protects skin) |
| `--contrast F` | | S-curve strength, `0..1` |
| `--gamma F` | | midtone lift, `>1` brighter |
| `--warmth F` | | `-1` cool … `+1` warm (negative neutralizes a warm cast) |
| `--sharpen F` | | unsharp amount, `0..1.5` |
| `--hdr-gain F` | `1.5` | HDR highlight expansion (HDR mode only) |
| `--preview` | | render before/after grade stills to `output/preview/`, then exit |
| `--at S,S,…` | *(20/50/80%)* | timestamps (seconds) for `--preview` |
| `--upscale` | | with `--preview`: AI-upscale the "after" half (see real detail) |
| `--inspect` / `--inspect-json` | | show normalized source metadata for people / JSON clients, then exit |
| `--start S` / `--duration S` | | trim: render only a section (great for tests) |
| `--no-audio` | | drop the audio track |
| `--batch` | | render every video in `input/` sequentially |
| `--chunk N` | `300` | frames per encode chunk (bounds disk use) |
| `--gpu N` | `0` | Real-ESRGAN GPU id (`-1` = CPU) |
| `--tile N` | `0` | tile size (0 = auto); lower it if you hit VRAM OOM |
| `--resume` | | reuse frames/chunks already produced |
| `--keep` | | keep scratch files after finishing |
| `--dry-run` | | print the plan and exit |

---

## How it works

1. **Extract** every frame to PNG (`ffmpeg`).
2. **Upscale** each frame with Real-ESRGAN on the GPU.
3. **Encode** in chunks to HDR10 HEVC with the vibrance grade — chunking keeps
   peak disk usage to a few GB and makes the run **resumable**.
4. **Concat** the chunks and **mux** the original audio.

Scratch files live under `%TEMP%\auvide\<name>` (override with `--work`).

## Performance

Real-ESRGAN is GPU-bound. Rough throughput on an **Intel Iris Xe** (integrated,
2 GB shared): ~**1.4 s/frame** at 2× with the `animevideo` model, i.e. roughly
**2 hours per 5,000 frames**. A discrete NVIDIA/AMD GPU is dramatically faster.
The `x4plus` model is sharper but slower and needs more VRAM.

## Roadmap

- ✅ **GUI front-end** — first `legacy/gui.py` (Tkinter), now a Tauri 2 desktop
  app (`desktop/`) over the same CLI engine.
- ✅ **Live grade preview** — before/after wipe + sliders, shared with the render.
- ✅ **AI upscale preview** (1:1 pixel-peek), **saved presets**, **trim**, **batch**,
  **notify/sleep-when-done**, **accent themes**.
- ✅ **RIFE 60fps / slow-mo**, **LUTs**, **delivery targets** (platform export),
  **restoration** (deinterlace / denoise / stabilize) — all one stage each.
- ✅ **Recipe save/load in the GUI**, live **pipeline summary**, **scopes**
  (waveform + vectorscope) in the preview.
- **Face restoration** (GFPGAN/CodeFormer) — needs a torch model, not yet packaged.
- **Curves editor** (the 8 grade sliders + LUTs already cover most of this).
- **`auvide` on PyPI** — `pip install auvide` / `uv tool install auvide`.
- **Signed, self-updating desktop installers** with a first-run setup screen
  that fetches ffmpeg/Real-ESRGAN — see `docs/MASTERPLAN.md`.

## Credits

- [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) — Xintao Wang et al.
- [FFmpeg](https://ffmpeg.org/) — encode / color pipeline.
