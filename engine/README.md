# auvide

AI video upscaler and vibrant HDR10 remapper. auvide extracts video frames,
upscales them with Real-ESRGAN, applies a configurable grade, then encodes a
resumable HDR10 or SDR output while preserving source audio.

## Install

```bash
pip install auvide
# or
uv tool install auvide
```

The Python package needs a Vulkan-capable GPU plus `ffmpeg`, `ffprobe`, and
`realesrgan-ncnn-vulkan` available on PATH. Real-ESRGAN model files must be
installed beside its executable or in auvide's model cache. The desktop app is
the recommended GUI and will eventually bootstrap these prerequisites itself.

## Use

```bash
auvide input.mp4 -o output.mp4 --scale 2 --vibrance vibrant
auvide input.mp4 --hdr off
auvide input.mp4 --resume
```

Run `auvide --help` for all pipeline, grade, restoration, interpolation, and
delivery-target options. For project documentation and the desktop application,
see <https://github.com/soulwax/auvide>.

## Managed tool overrides

Desktop/bootstrap integrations can provide absolute paths instead of modifying
PATH. Invalid explicit paths fail with an actionable error and never fall back
to a different system tool.

```text
AUVIDE_FFMPEG
AUVIDE_FFPROBE
AUVIDE_REALESRGAN
AUVIDE_REALESRGAN_MODELS
AUVIDE_RIFE
AUVIDE_RIFE_MODELS
```

The `*_MODELS` values must name directories containing `.param` model files.

## License

MIT. See `LICENSE`.
