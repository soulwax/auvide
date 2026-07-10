#!/usr/bin/env python3
"""auvide - AI video upscaler + vibrant HDR10 remapper.

Pipeline:
  1. extract every frame of the source video to PNG
  2. AI-upscale each frame with Real-ESRGAN (Vulkan / GPU)
  3. re-encode in chunks to HDR10 (BT.2020 + PQ, 10-bit) with a vibrance grade
  4. concat the chunks and mux the original audio back in

The tool is self-contained: it looks for ffmpeg/ffprobe/realesrgan and the
Real-ESRGAN models inside ./bin (run setup.ps1 once to provision them).

Chunked encoding keeps peak disk usage bounded (a few GB) and makes the run
resumable: finished chunks are skipped on re-run with --resume.

Examples
--------
  python upscale_hdr.py "movie.mp4"
  python upscale_hdr.py "movie.mp4" -o out.mp4 --scale 2 --vibrance vibrant
  python upscale_hdr.py "movie.mp4" --model x4plus --hdr off
  python upscale_hdr.py "movie.mp4" --resume
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BIN = HERE / "bin"
FFMPEG = BIN / "ffmpeg.exe"
FFPROBE = BIN / "ffprobe.exe"
REALESRGAN = BIN / "realesrgan-ncnn-vulkan.exe"
MODELS = BIN / "models"

# model key -> (realesrgan model name, native scale or None for "any 2/3/4")
MODEL_MAP = {
    "animevideo": ("realesr-animevideov3", None),   # fast, denoises, great for video
    "x4plus": ("realesrgan-x4plus", 4),             # sharper photographic detail, 4x only
    "x4plus-anime": ("realesrgan-x4plus-anime", 4), # illustration / anime, 4x only
}

# vibrance preset -> (saturation, contrast, hdr_highlight_gain)
VIBRANCE = {
    "none":    (1.00, 1.00, 1.0),
    "subtle":  (1.12, 1.02, 1.2),
    "vibrant": (1.30, 1.05, 1.5),
    "max":     (1.50, 1.10, 2.2),
}

# HDR10 mastering-display + content-light metadata (generic P3-ish, 1000-nit master)
MASTER_DISPLAY = ("G(13250,34500)B(7500,3000)R(34000,16000)"
                  "WP(15635,16450)L(10000000,50)")
MAX_CLL = "1000,400"


def die(msg: str) -> None:
    print(f"\n[error] {msg}", file=sys.stderr)
    sys.exit(1)


def check_deps() -> None:
    missing = [str(p) for p in (FFMPEG, FFPROBE, REALESRGAN) if not p.exists()]
    if missing:
        die("missing bundled binaries:\n  " + "\n  ".join(missing) +
            "\nRun setup.ps1 to download them into ./bin")
    if not MODELS.exists():
        die(f"missing models folder: {MODELS}\nRun setup.ps1 to provision it.")


def probe(src: Path) -> dict:
    out = subprocess.run(
        [str(FFPROBE), "-v", "error", "-print_format", "json",
         "-show_streams", "-show_format", str(src)],
        capture_output=True, text=True)
    if out.returncode != 0:
        die(f"ffprobe failed:\n{out.stderr}")
    data = json.loads(out.stdout)
    vstream = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    astream = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    if vstream is None:
        die("no video stream found in input")

    num, den = (vstream.get("r_frame_rate", "24/1").split("/") + ["1"])[:2]
    fps_num, fps_den = int(num), int(den or 1)
    fps = fps_num / fps_den

    nb = vstream.get("nb_frames")
    if nb and nb.isdigit() and int(nb) > 0:
        total = int(nb)
    else:
        dur = float(vstream.get("duration") or data["format"].get("duration") or 0)
        total = int(round(dur * fps)) if dur else 0

    return {
        "width": int(vstream["width"]),
        "height": int(vstream["height"]),
        "fps_num": fps_num,
        "fps_den": fps_den,
        "fps": fps,
        "total": total,
        "has_audio": astream is not None,
        "duration": float(data["format"].get("duration") or 0),
    }


def build_vf(args, info) -> str:
    sat, con, gain = VIBRANCE[args.vibrance]
    filters = []

    # if realesrgan over-scaled (x4plus at 4x) but a smaller target was asked,
    # scale down to the requested factor.
    if args.rescale_to:
        tw, th = args.rescale_to
        filters.append(f"scale={tw}:{th}:flags=lanczos")

    if args.vibrance != "none":
        filters.append(f"eq=saturation={sat}:contrast={con}")

    if args.hdr == "on":
        # SDR BT.709 (full-range RGB PNGs) -> HDR10 PQ / BT.2020, 10-bit.
        filters += [
            "zscale=tin=bt709:min=bt709:pin=bt709:rin=pc:t=linear:npl=100",
            "format=gbrpf32le",
            "zscale=p=bt2020",
            f"tonemap=tonemap=linear:desat=0:param={gain}",
            "zscale=t=smpte2084:m=bt2020nc:p=bt2020:r=tv",
            "format=yuv420p10le",
        ]
    else:
        filters.append("format=yuv420p")
    return ",".join(filters)


def encode_cmd(args, info, in_pattern: str, start_number: int, out_file: Path) -> list[str]:
    vf = build_vf(args, info)
    fps = f"{info['fps_num']}/{info['fps_den']}"
    cmd = [str(FFMPEG), "-y", "-framerate", fps,
           "-start_number", str(start_number), "-i", in_pattern,
           "-vf", vf]

    if args.hdr == "on":
        if args.encoder == "qsv":
            cmd += ["-c:v", "hevc_qsv", "-preset", "slow", "-global_quality", str(args.crf),
                    "-pix_fmt", "p010le"]
        else:
            xp = (f"colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc:"
                  f"master-display={MASTER_DISPLAY}:max-cll={MAX_CLL}:"
                  f"hdr10=1:hdr10-opt=1:repeat-headers=1")
            cmd += ["-c:v", "libx265", "-preset", args.preset, "-crf", str(args.crf),
                    "-pix_fmt", "yuv420p10le", "-x265-params", xp]
        cmd += ["-color_primaries", "bt2020", "-color_trc", "smpte2084",
                "-colorspace", "bt2020nc"]
    else:
        if args.encoder == "qsv":
            cmd += ["-c:v", "hevc_qsv", "-preset", "slow", "-global_quality", str(args.crf)]
        else:
            cmd += ["-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
                    "-pix_fmt", "yuv420p"]
        cmd += ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]

    cmd.append(str(out_file))
    return cmd


# suppress child-process console windows when driven from a GUI (Windows only)
_NOWINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def run(cmd: list[str], quiet: bool = True) -> None:
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL if quiet else None,
                       stderr=subprocess.PIPE, text=True, creationflags=_NOWINDOW)
    if r.returncode != 0:
        die(f"command failed ({cmd[0]}):\n{r.stderr[-2000:]}")


def fmt_eta(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}h{m:02d}m" if h else f"{m:d}m{s:02d}s"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="AI upscale a video and remap it to vibrant HDR10.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("input", type=Path, help="source video file")
    ap.add_argument("-o", "--output", type=Path, help="output file (default: <name>_2x_hdr.mp4)")
    ap.add_argument("--scale", type=int, default=2, choices=[2, 3, 4], help="upscale factor")
    ap.add_argument("--model", default="animevideo", choices=list(MODEL_MAP),
                    help="Real-ESRGAN model (animevideo=fast/video, x4plus=sharp photo)")
    ap.add_argument("--vibrance", default="vibrant", choices=list(VIBRANCE),
                    help="color punch")
    ap.add_argument("--hdr", default="on", choices=["on", "off"],
                    help="remap to HDR10 (on) or stay SDR BT.709 (off)")
    ap.add_argument("--encoder", default="x265", choices=["x265", "qsv"],
                    help="x265=software (best HDR fidelity), qsv=Intel GPU (faster)")
    ap.add_argument("--crf", type=int, default=19, help="quality (lower=better, 18-23 typical)")
    ap.add_argument("--preset", default="medium", help="x264/x265 preset")
    ap.add_argument("--chunk", type=int, default=300, help="frames encoded per chunk")
    ap.add_argument("--gpu", type=int, default=0, help="Real-ESRGAN GPU id (-1 = CPU)")
    ap.add_argument("--tile", type=int, default=0, help="Real-ESRGAN tile size (0=auto)")
    ap.add_argument("--work", type=Path, help="scratch dir (default: system temp)")
    ap.add_argument("--resume", action="store_true", help="reuse frames/chunks already done")
    ap.add_argument("--keep", action="store_true", help="keep scratch files after finishing")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    args = ap.parse_args()

    check_deps()
    src = args.input.resolve()
    if not src.exists():
        die(f"input not found: {src}")

    info = probe(src)
    if info["total"] <= 0:
        die("could not determine frame count")

    # resolve model / scale plan
    model_name, native = MODEL_MAP[args.model]
    if native == 4 and args.scale != 4:
        realesr_scale = 4
        args.rescale_to = (info["width"] * args.scale, info["height"] * args.scale)
    else:
        realesr_scale = args.scale
        args.rescale_to = None
    tw, th = info["width"] * args.scale, info["height"] * args.scale

    out = args.output or src.with_name(f"{src.stem}_{args.scale}x_"
                                       f"{'hdr' if args.hdr=='on' else 'sdr'}.mp4")
    out = out.resolve()

    work = (args.work or Path(tempfile.gettempdir()) / "auvide" / src.stem).resolve()
    frames_in = work / "frames_in"
    seg_dir = work / "segments"
    for d in (frames_in, seg_dir):
        d.mkdir(parents=True, exist_ok=True)

    n_chunks = math.ceil(info["total"] / args.chunk)

    print("=" * 60)
    print(f"  auvide  |  {src.name}")
    print("=" * 60)
    print(f"  source      {info['width']}x{info['height']}  "
          f"{info['fps']:.3f} fps  {info['total']} frames  "
          f"{fmt_eta(info['duration'])}")
    print(f"  target      {tw}x{th}  ({args.scale}x)")
    print(f"  model       {model_name}  (realesrgan -s {realesr_scale})")
    print(f"  grade       {args.hdr.upper()}  vibrance={args.vibrance}  "
          f"encoder={args.encoder}  crf={args.crf}")
    print(f"  chunks      {n_chunks} x {args.chunk} frames")
    print(f"  work dir    {work}")
    print(f"  output      {out}")
    print("=" * 60)
    if args.dry_run:
        return

    # ---- phase 1: extract all frames -------------------------------------
    marker = frames_in / ".extracted"
    have = len(list(frames_in.glob("frame_*.png")))
    if args.resume and marker.exists() and have >= info["total"] - 1:
        print(f"[1/3] frames: reusing {have} extracted frames")
    else:
        print(f"[1/3] extracting {info['total']} frames ...", flush=True)
        t0 = time.time()
        run([str(FFMPEG), "-y", "-i", str(src), "-vsync", "passthrough",
             str(frames_in / "frame_%06d.png")])
        marker.write_text("ok")
        have = len(list(frames_in.glob("frame_*.png")))
        print(f"      extracted {have} frames in {fmt_eta(time.time()-t0)}")

    total = have  # actual frames on disk (may differ from container's nb_frames)
    n_chunks = math.ceil(total / args.chunk)

    # ---- phase 2: upscale + encode each chunk ----------------------------
    print(f"[2/3] upscaling + HDR encoding ({total} frames, {n_chunks} chunks) ...",
          flush=True)
    batch_in = work / "batch_in"
    batch_out = work / "batch_out"
    done_frames = 0
    run_start = time.time()

    for c in range(n_chunks):
        start = c * args.chunk + 1                     # 1-based global index
        if start > total:
            break
        end = min(start + args.chunk - 1, total)
        count = end - start + 1
        seg = seg_dir / f"seg_{c:05d}.mp4"

        if args.resume and seg.exists() and seg.stat().st_size > 0:
            print(f"      chunk {c+1}/{n_chunks}: skip (done)")
            done_frames += count
            continue

        # fresh batch folders
        for d in (batch_in, batch_out):
            if d.exists():
                shutil.rmtree(d)
            d.mkdir(parents=True)

        for i in range(start, end + 1):
            name = f"frame_{i:06d}.png"
            shutil.copy2(frames_in / name, batch_in / name)

        t0 = time.time()
        re_cmd = [str(REALESRGAN), "-i", str(batch_in), "-o", str(batch_out),
                  "-n", model_name, "-s", str(realesr_scale),
                  "-m", str(MODELS), "-g", str(args.gpu), "-f", "png"]
        if args.tile > 0:
            re_cmd += ["-t", str(args.tile)]
        run(re_cmd)

        run(encode_cmd(args, info, str(batch_out / "frame_%06d.png"), start, seg))

        done_frames += count
        elapsed = time.time() - run_start
        rate = done_frames / elapsed if elapsed else 0
        remaining = (total - done_frames) / rate if rate else 0
        print(f"      chunk {c+1}/{n_chunks}: {count} frames in "
              f"{fmt_eta(time.time()-t0)}  |  {rate:.2f} fps  |  ETA {fmt_eta(remaining)}",
              flush=True)

    # tidy transient batch dirs
    for d in (batch_in, batch_out):
        if d.exists():
            shutil.rmtree(d)

    # ---- phase 3: concat + mux audio -------------------------------------
    print("[3/3] concatenating chunks + muxing audio ...", flush=True)
    segs = sorted(seg_dir.glob("seg_*.mp4"))
    if not segs:
        die("no encoded segments were produced")
    list_file = work / "concat.txt"
    list_file.write_text("".join(f"file '{s.as_posix()}'\n" for s in segs))

    concat_cmd = [str(FFMPEG), "-y", "-f", "concat", "-safe", "0", "-i", str(list_file)]
    if info["has_audio"]:
        concat_cmd += ["-i", str(src), "-map", "0:v:0", "-map", "1:a:0",
                       "-c:v", "copy", "-c:a", "copy"]
    else:
        concat_cmd += ["-map", "0:v:0", "-c:v", "copy"]
    concat_cmd += ["-movflags", "+faststart", str(out)]
    run(concat_cmd)

    # ---- done ------------------------------------------------------------
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)

    size_mb = out.stat().st_size / (1024 * 1024)
    print("=" * 60)
    print(f"  done  ->  {out}")
    print(f"  {tw}x{th}  {info['fps']:.3f} fps  {size_mb:.1f} MB  "
          f"total {fmt_eta(time.time()-run_start)}")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[interrupted] re-run with --resume to continue", file=sys.stderr)
        sys.exit(130)
