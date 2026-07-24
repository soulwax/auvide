"""Locate external tools and model directories for the auvide pipeline.

The canonical source is the system package manager — auvide does not bundle
binaries (they're large, and on Windows a copy inside a OneDrive folder is
re-scanned on every launch, adding ~4s per call):

  Windows : scoop install ffmpeg realesrgan-ncnn-vulkan   (run setup.ps1)
  macOS   : brew install ffmpeg realesrgan-ncnn-vulkan
  Arch    : sudo pacman -S ffmpeg  &&  yay -S realesrgan-ncnn-vulkan   (AUR)
  Ubuntu  : sudo apt install ffmpeg   (realesrgan-ncnn-vulkan from upstream release)
  Fedora  : sudo dnf install ffmpeg   (realesrgan-ncnn-vulkan from upstream release)

CLI users normally resolve everything from PATH. Desktop builds inject absolute
paths with ``AUVIDE_*`` overrides so bundled/downloaded tools take precedence
without mutating the user's PATH. The Real-ESRGAN models (data, not an exe)
are provisioned into a local cache by setup and found automatically.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

APP_CACHE = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".cache")) / "auvide"
MODELS_CACHE = APP_CACHE / "models"
RIFE_MODELS_CACHE = APP_CACHE / "rife-models"

ENV_FFMPEG = "AUVIDE_FFMPEG"
ENV_FFPROBE = "AUVIDE_FFPROBE"
ENV_REALESRGAN = "AUVIDE_REALESRGAN"
ENV_REALESRGAN_MODELS = "AUVIDE_REALESRGAN_MODELS"
ENV_RIFE = "AUVIDE_RIFE"
ENV_RIFE_MODELS = "AUVIDE_RIFE_MODELS"

INSTALL_HINT = (
    "Install the prerequisites, then retry:\n"
    "  Windows : run setup.ps1  (scoop install ffmpeg realesrgan-ncnn-vulkan + models)\n"
    "  macOS   : brew install ffmpeg realesrgan-ncnn-vulkan\n"
    "  Arch    : sudo pacman -S ffmpeg && yay -S realesrgan-ncnn-vulkan\n"
    "  Ubuntu  : sudo apt install ffmpeg  (+ realesrgan-ncnn-vulkan from upstream)\n"
    "  Fedora  : sudo dnf install ffmpeg  (+ realesrgan-ncnn-vulkan from upstream)\n"
    "  Real-ESRGAN models: run setup.ps1, or drop the .param/.bin files into\n"
    f"    {MODELS_CACHE}\n"
)


def _which(*names):
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def _override_path(variable: str, *, directory: bool = False) -> str | None:
    """Return a valid explicit override, or None when unset/invalid.

    An explicitly configured but invalid override never falls back to PATH:
    that would make desktop setup failures look like it selected a system tool.
    ``override_error`` exposes the reason to callers.
    """
    if variable not in os.environ:
        return None
    raw = os.environ[variable].strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        return None
    if directory:
        return str(path) if path.is_dir() else None
    return str(path) if path.is_file() else None


def override_error(variable: str) -> str | None:
    """Explain an invalid explicit override, or return None when it is valid/unset."""
    if variable not in os.environ:
        return None
    raw = os.environ[variable].strip()
    if not raw:
        return f"{variable} is set but empty"
    path = Path(raw).expanduser()
    if not path.is_absolute():
        return f"{variable} must be an absolute path (got {raw!r})"

    models = variable in {ENV_REALESRGAN_MODELS, ENV_RIFE_MODELS}
    if models:
        if not path.is_dir():
            return f"{variable} must name an existing model directory: {path}"
        if not any(path.glob("*.param")):
            return f"{variable} has no .param model files: {path}"
        return None

    if not path.is_file():
        return f"{variable} must name an existing executable file: {path}"
    return None


def _binary(variable: str, *names: str) -> str | None:
    if variable in os.environ:
        return _override_path(variable)
    return _which(*names)


def ffmpeg():
    return _binary(ENV_FFMPEG, "ffmpeg")


def ffprobe():
    return _binary(ENV_FFPROBE, "ffprobe")


def realesrgan():
    return _binary(ENV_REALESRGAN, "realesrgan-ncnn-vulkan", "realesrgan")


def rife():
    return _binary(ENV_RIFE, "rife-ncnn-vulkan", "rife")


def rife_model(name="rife-v4.6"):
    """Locate a RIFE model folder (or None). Optional — only for interpolation."""
    if ENV_RIFE_MODELS in os.environ:
        return None if override_error(ENV_RIFE_MODELS) else _override_path(
            ENV_RIFE_MODELS, directory=True)
    exe = rife()
    if exe:
        p = Path(exe)
        if "scoop" in p.parts and "shims" in p.parts:   # scoop bundles models in app dir
            i = p.parts.index("scoop")
            cand = Path(*p.parts[:i + 1], "apps", "rife-ncnn-vulkan", "current", name)
            if cand.exists():
                return cand
        near = p.resolve().parent / name                 # some installs: models beside exe
        if near.exists():
            return near
    cache = RIFE_MODELS_CACHE / name
    if cache.exists() and any(cache.glob("*.param")):
        return cache
    return None


def models_dir():
    """Where the Real-ESRGAN .param/.bin models live (or None)."""
    if ENV_REALESRGAN_MODELS in os.environ:
        return None if override_error(ENV_REALESRGAN_MODELS) else _override_path(
            ENV_REALESRGAN_MODELS, directory=True)
    exe = realesrgan()
    if exe:                                   # some installs ship models beside the exe
        near = Path(exe).resolve().parent / "models"
        if near.exists() and any(near.glob("*.param")):
            return near
    if MODELS_CACHE.exists() and any(MODELS_CACHE.glob("*.param")):
        return MODELS_CACHE
    return None


def missing():
    """List of prerequisites that are not resolvable (empty = all good)."""
    out = []
    if error := override_error(ENV_FFMPEG):
        out.append(error)
    elif not ffmpeg():
        out.append("ffmpeg")
    if error := override_error(ENV_FFPROBE):
        out.append(error)
    elif not ffprobe():
        out.append("ffprobe")
    if error := override_error(ENV_REALESRGAN):
        out.append(error)
    elif not realesrgan():
        out.append("realesrgan-ncnn-vulkan")
    if error := override_error(ENV_REALESRGAN_MODELS):
        out.append(error)
    elif not models_dir():
        out.append("Real-ESRGAN models")
    return out
