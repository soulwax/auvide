"""Frame-op stages — the composable 'tricks' of the pipeline.

Each stage is a folder-in -> folder-out pass (the ncnn-vulkan pattern shared by
Real-ESRGAN and RIFE). The runner in upscale_hdr.py chains them per chunk:

    batch_in --Upscale--> s0 --Interpolate--> s1 --> encode

Adding a new AI trick = a new Stage class resolved through tools.py. Stages that
change frame COUNT (interpolate) report their output multiplier so the encoder
can pick the right output frame rate.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Protocol

from . import tools

NOWINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class StageError(RuntimeError):
    pass


class StageCancelled(StageError):
    pass


def _not_cancelled() -> bool:
    return False


_cancel_requested: Callable[[], bool] = _not_cancelled


def set_cancel_checker(checker: Callable[[], bool]) -> None:
    """Set the per-render cancellation check used by long-running AI stages."""
    global _cancel_requested
    _cancel_requested = checker


class Stage(Protocol):
    """Structural type for a folder-in -> folder-out pipeline stage. Both
    UpscaleStage and InterpolateStage satisfy this without inheriting it."""
    label: str
    frame_multiplier: int

    def process(self, in_dir: Path, out_dir: Path) -> None: ...


def _run(cmd):
    child = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=NOWINDOW,
    )
    stderr: list[str] = []

    def drain_stderr() -> None:
        if child.stderr:
            stderr.append(child.stderr.read())

    reader = threading.Thread(target=drain_stderr, daemon=True)
    reader.start()
    while child.poll() is None:
        if _cancel_requested():
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            reader.join()
            raise StageCancelled("frame stage cancelled")
        time.sleep(0.1)
    reader.join()
    if child.returncode != 0:
        raise StageError(f"{Path(cmd[0]).name} failed:\n{''.join(stderr)[-800:]}")


class UpscaleStage:
    """Real-ESRGAN AI upscale. Changes resolution; frame count unchanged."""
    label = "upscale"
    frame_multiplier = 1

    def __init__(self, model_name, scale, gpu=0, tile=0):
        self.model_name, self.scale, self.gpu, self.tile = model_name, scale, gpu, tile

    def process(self, in_dir: Path, out_dir: Path) -> None:
        exe, models = tools.realesrgan(), tools.models_dir()
        if not exe or not models:
            raise StageError("realesrgan / models not found — run setup.ps1")
        cmd = [exe, "-i", str(in_dir), "-o", str(out_dir), "-n", self.model_name,
               "-s", str(self.scale), "-m", str(models), "-g", str(self.gpu), "-f", "png"]
        if self.tile > 0:
            cmd += ["-t", str(self.tile)]
        _run(cmd)


class InterpolateStage:
    """RIFE frame interpolation. Multiplies frame count by `factor`."""
    label = "interpolate"

    def __init__(self, factor, gpu=0, model="rife-v4.6"):
        self.factor = int(factor)
        self.frame_multiplier = self.factor
        self.gpu, self.model = gpu, model

    def process(self, in_dir: Path, out_dir: Path) -> None:
        exe, mdir = tools.rife(), tools.rife_model(self.model)
        if not exe or not mdir:
            detail = tools.override_error(tools.ENV_RIFE) or tools.override_error(
                tools.ENV_RIFE_MODELS)
            if detail:
                raise StageError(detail)
            raise StageError("rife-ncnn-vulkan / models not found — scoop install "
                             "rife-ncnn-vulkan (or see README)")
        n_in = len(list(Path(in_dir).glob("*.png")))
        target = max(2, n_in * self.factor)
        _run([exe, "-i", str(in_dir), "-o", str(out_dir), "-m", str(mdir),
              "-n", str(target), "-g", str(self.gpu), "-f", "%08d.png"])


def build_frame_stages(args) -> list[Stage]:
    """Ordered folder-op stages from CLI args: upscale, then optional interpolate."""
    from .cli import MODEL_MAP
    model_name, native = MODEL_MAP[args.model]
    re_scale = 4 if (native == 4 and args.scale != 4) else args.scale
    stages: list[Stage] = [UpscaleStage(model_name, re_scale, args.gpu, args.tile)]
    if getattr(args, "interpolate", 0) and args.interpolate > 1:
        stages.append(InterpolateStage(args.interpolate, args.gpu))
    return stages


def total_frame_multiplier(stages: list[Stage]) -> int:
    m = 1
    for s in stages:
        m *= getattr(s, "frame_multiplier", 1)
    return m
