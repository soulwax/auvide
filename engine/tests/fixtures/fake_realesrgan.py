#!/usr/bin/env python3
"""Stub for realesrgan-ncnn-vulkan, used only by the integration test.

Mimics the subset of the real CLI's interface that auvide.stages.UpscaleStage
invokes (-i in_dir -o out_dir -n model -s scale -m models_dir -g gpu -f png
[-t tile]) and actually scales the frames with ffmpeg, so the rest of the
pipeline (encode, HDR tag, mux) runs against real, correctly-sized PNGs
without needing a GPU or the real Real-ESRGAN binary in CI.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", dest="in_dir", required=True)
    ap.add_argument("-o", dest="out_dir", required=True)
    ap.add_argument("-n", dest="model", default="")
    ap.add_argument("-s", dest="scale", type=int, default=2)
    ap.add_argument("-m", dest="models_dir", default="")
    ap.add_argument("-g", dest="gpu", default="0")
    ap.add_argument("-f", dest="fmt", default="png")
    ap.add_argument("-t", dest="tile", default="0")
    args = ap.parse_args()

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("fake_realesrgan: ffmpeg not found on PATH", file=sys.stderr)
        sys.exit(1)

    in_dir, out_dir = Path(args.in_dir), Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for frame in sorted(in_dir.glob("*.png")):
        dest = out_dir / frame.name
        r = subprocess.run(
            [ffmpeg, "-y", "-i", str(frame), "-vf",
             f"scale=iw*{args.scale}:ih*{args.scale}:flags=neighbor", str(dest)], check=False,
            capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stderr, file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
