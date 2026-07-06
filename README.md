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

Requires **Python 3.8+** and a Vulkan-capable GPU (any modern integrated or
discrete GPU works).

```powershell
# one-time: download ffmpeg, ffprobe, realesrgan + models into ./bin
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

The heavy binaries in `bin/` are **not** committed (ffmpeg alone exceeds
GitHub's 100 MB file limit) — `setup.ps1` fetches them.

---

## Usage

```powershell
# defaults: 2x, animevideo model, vibrant HDR10
python upscale_hdr.py "movie.mp4"

# explicit
python upscale_hdr.py "movie.mp4" -o "movie_hdr.mp4" --scale 2 --vibrance vibrant

# sharper photographic model (4x native, slower, more VRAM)
python upscale_hdr.py "movie.mp4" --model x4plus --scale 2

# stay SDR, just upscale
python upscale_hdr.py "movie.mp4" --hdr off

# resume an interrupted run
python upscale_hdr.py "movie.mp4" --resume
```

Or drag a video file onto **`run.bat`** to process it with defaults.

### Options

| flag | default | meaning |
|------|---------|---------|
| `--scale {2,3,4}` | `2` | upscale factor |
| `--model {animevideo,x4plus,x4plus-anime}` | `animevideo` | `animevideo` = fast, denoises, best for real video; `x4plus` = sharper photographic detail |
| `--vibrance {none,subtle,vibrant,max}` | `vibrant` | color/saturation punch |
| `--hdr {on,off}` | `on` | HDR10 remap, or stay SDR BT.709 |
| `--encoder {x265,qsv}` | `x265` | `x265` = software (best HDR fidelity); `qsv` = Intel Quick Sync GPU (faster) |
| `--crf N` | `19` | quality, lower = better (18–23 typical) |
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

- **GUI front-end** (planned) — a Tkinter desktop window (file picker / drag-drop,
  scale/model/vibrance/HDR dropdowns, live progress bar) wrapping the existing
  pipeline. The CLI stays the engine; the GUI just calls `main()`'s logic.
- **Standalone `.exe`** — package GUI + `bin/` with PyInstaller for double-click use.
- **QSV HDR validation** — confirm/tune the `--encoder qsv` HDR10 metadata path.

## Credits

- [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) — Xintao Wang et al.
- [FFmpeg](https://ffmpeg.org/) — encode / color pipeline.
