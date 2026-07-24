#!/usr/bin/env python3
"""auvide - AI video upscaler + vibrant HDR10 remapper.

Pipeline:
  1. extract every frame of the source video to PNG
  2. AI-upscale each frame with Real-ESRGAN (Vulkan / GPU)
  3. re-encode in chunks to HDR10 (BT.2020 + PQ, 10-bit) with a vibrance grade
  4. concat the chunks and mux the original audio back in

Prerequisites (ffmpeg, ffprobe, realesrgan-ncnn-vulkan) are resolved from PATH
via your package manager — run setup.ps1 on Windows, or see tools.py / README
for macOS / Arch / Ubuntu / Fedora. Real-ESRGAN models live in a local cache.

Chunked encoding keeps peak disk usage bounded (a few GB) and makes the run
resumable: finished chunks are skipped on re-run with --resume.

Examples
--------
  auvide "movie.mp4"
  auvide "movie.mp4" -o out.mp4 --scale 2 --vibrance vibrant
  auvide "movie.mp4" --model x4plus --hdr off
  auvide "movie.mp4" --resume
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import NoReturn

from . import grade
from . import recipe as recipes
from . import stages
from . import tools
from .progress import Reporter

# CWD, not the installed package's location: `input/`/`output/` are a
# convenience for running from a checkout, not part of the installed package.
HERE = Path.cwd()
INPUT_DIR = HERE / "input"
OUTPUT_DIR = HERE / "output"
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}
REPORTER = Reporter()
CANCEL_FILE: Path | None = None
WORK_DIR: Path | None = None

# model key -> (realesrgan model name, native scale or None for "any 2/3/4")
MODEL_MAP = {
    "animevideo": ("realesr-animevideov3", None),   # fast, denoises, great for video
    "x4plus": ("realesrgan-x4plus", 4),             # sharper photographic detail, 4x only
    "x4plus-anime": ("realesrgan-x4plus-anime", 4), # illustration / anime, 4x only
}

# restore: hqdn3d denoise presets (luma_spatial:chroma_spatial:luma_tmp:chroma_tmp)
DENOISE = {
    "light":  "hqdn3d=1.5:1.5:6:6",
    "medium": "hqdn3d=3:2:9:9",
    "strong": "hqdn3d=6:4:12:12",
}

# HDR10 mastering-display + content-light metadata (generic P3-ish, 1000-nit master)
MASTER_DISPLAY = ("G(13250,34500)B(7500,3000)R(34000,16000)"
                  "WP(15635,16450)L(10000000,50)")
MAX_CLL = "1000,400"


def die(msg: str) -> NoReturn:
    REPORTER.event("failed", code="pipeline_error", message=msg)
    print(f"\n[error] {msg}", file=sys.stderr)
    sys.exit(1)


class Cancelled(RuntimeError):
    pass


def cancel_requested() -> bool:
    return CANCEL_FILE is not None and CANCEL_FILE.exists()


def check_cancelled() -> None:
    if cancel_requested():
        raise Cancelled


def finish_cancelled() -> NoReturn:
    if WORK_DIR:
        for batch_dir in WORK_DIR.glob("batch_*"):
            shutil.rmtree(batch_dir, ignore_errors=True)
    REPORTER.event(
        "cancelled",
        resumable=WORK_DIR is not None,
        work_dir=str(WORK_DIR) if WORK_DIR else "",
    )
    REPORTER.log("[interrupted] re-run with --resume to continue", error=True)
    sys.exit(130)


def resolve_input(arg) -> Path:
    """Explicit path if given, else the single video in ./input."""
    if arg:
        p = Path(arg).resolve()
        if not p.exists():
            die(f"input not found: {p}")
        return p
    vids = ([p for p in sorted(INPUT_DIR.glob("*")) if p.suffix.lower() in VIDEO_EXTS]
            if INPUT_DIR.exists() else [])
    if len(vids) == 1:
        return vids[0].resolve()
    if not vids:
        die(f"no input given and no video found in {INPUT_DIR}")
    die("multiple videos in ./input — pass one explicitly: "
        + ", ".join(p.name for p in vids))


def check_deps() -> None:
    m = tools.missing()
    if m:
        die("missing prerequisite(s): " + ", ".join(m) + "\n\n" + tools.INSTALL_HINT)


def probe(src: Path) -> dict:
    out = subprocess.run(
        [str(tools.ffprobe()), "-v", "error", "-print_format", "json",
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


def resolve_grade(args) -> grade.Grade:
    """Grade preset with any per-knob CLI overrides applied."""
    return grade.from_overrides(
        grade.PRESETS[args.vibrance],
        saturation=args.saturation, vibrance=args.vibrance_amt,
        contrast=args.contrast, gamma=args.gamma,
        warmth=args.warmth, sharpen=args.sharpen,
        exposure=args.exposure, tint=args.tint)


def build_vf(args, info) -> str:
    filters = []

    # if realesrgan over-scaled (x4plus at 4x) but a smaller target was asked,
    # scale down to the requested factor.
    if args.rescale_to:
        tw, th = args.rescale_to
        filters.append(f"scale={tw}:{th}:flags=lanczos")

    # shared best-practice grade, in float RGB; leave pixels in that space so
    # the HDR tail (below) can pick up without a round-trip through 8-bit.
    filters.append(grade.build_chain(resolve_grade(args), out_format=None,
                                     working="gbrpf32le",
                                     lut=str(args.lut) if args.lut else "", curve=args.curve))

    if args.hdr == "on":
        # graded BT.709 (float RGB) -> HDR10 PQ / BT.2020, 10-bit.
        filters += [
            "zscale=tin=bt709:min=bt709:pin=bt709:rin=pc:t=linear:npl=100",
            "format=gbrpf32le",
            "zscale=p=bt2020",
            f"tonemap=tonemap=linear:desat=0:param={args.hdr_gain}",
            "zscale=t=smpte2084:m=bt2020nc:p=bt2020:r=tv",
            "format=yuv420p10le",
        ]
    else:
        filters.append("format=yuv420p")

    if args.target and args.target != "source":      # crop/pad to the delivery size
        tf, _ = recipes.target_transform(args.target, info["width"] * args.scale,
                                         info["height"] * args.scale)
        if tf:
            filters.append(tf)
    return ",".join(filters)


def make_preview(args, src: Path, info: dict) -> None:
    """Render before/after grade stills and exit — no full run.

    Default: left = original, right = graded (source resolution, fast).
    --upscale: right = AI-upscaled + graded, left = bicubic-upscaled original,
    so you can judge real upscale detail before committing to a full run.
    """
    grade_vf = grade.build_chain(resolve_grade(args), out_format="rgb24", working="gbrpf32le",
                                 lut=str(args.lut) if args.lut else "", curve=args.curve)
    dur = info["duration"]
    if args.at:
        times = [float(x) for x in args.at.split(",") if x.strip()]
    else:
        times = [round(dur * f, 1) for f in (0.2, 0.5, 0.8)] if dur else [5.0]
    pdir = OUTPUT_DIR / "preview"
    pdir.mkdir(parents=True, exist_ok=True)
    tw, th = info["width"] * args.scale, info["height"] * args.scale
    model_name, native = MODEL_MAP[args.model]
    re_scale = 4 if (native == 4 and args.scale != 4) else args.scale
    tag = "upscaled" if args.upscale else "grade"
    print(f"[preview] {len(times)} before/after ({tag}) stills -> {pdir}")
    for t in times:
        out = pdir / f"{src.stem}_t{int(t)}s_{tag}.png"
        frame = pdir / "_frame.png"
        run([
            str(tools.ffmpeg()), "-y", "-ss", str(t), "-i", str(src),
            "-frames:v", "1", str(frame),
        ])
        if args.upscale:
            up = pdir / "_up.png"
            run([
                str(tools.realesrgan()), "-i", str(frame), "-o", str(up), "-n", model_name,
                "-s", str(re_scale), "-m", str(tools.models_dir()), "-g", str(args.gpu),
                "-f", "png",
            ])
            down = f"scale={tw}:{th}:flags=lanczos," if re_scale != args.scale else ""
            vf = (f"[1:v]scale={tw}:{th}:flags=bicubic,format=rgb24[la];"
                  f"[0:v]{down}{grade_vf}[lg];[la][lg]hstack=inputs=2")
            run([str(tools.ffmpeg()), "-y", "-i", str(up), "-i", str(frame),
                 "-filter_complex", vf, str(out)], cwd=getattr(args, "_lut_cwd", None))
        else:
            vf = f"split=2[a][b];[a]format=rgb24[la];[b]{grade_vf}[lg];[la][lg]hstack=inputs=2"
            run([str(tools.ffmpeg()), "-y", "-i", str(frame), "-vf", vf, str(out)],
                cwd=getattr(args, "_lut_cwd", None))
        print(f"  {out.name}")
    for tmp in (pdir / "_frame.png", pdir / "_up.png"):   # scrub intermediates
        tmp.unlink(missing_ok=True)
    left = "bicubic-upscaled original" if args.upscale else "original"
    right = "AI-upscaled + graded" if args.upscale else "graded"
    print(f"[preview] done — left = {left}, right = {right}")


def normalize_seq(d: Path) -> str:
    """Rename a dir's PNGs to a contiguous 1-based sequence, return the ffmpeg
    pattern. Lets any stage's output naming/count feed the numeric image2 demuxer
    (this ffmpeg build has no glob input)."""
    for idx, f in enumerate(sorted(Path(d).glob("*.png")), 1):
        f.rename(Path(d) / f"_seq_{idx:08d}.png")
    return str(Path(d) / "_seq_%08d.png")


def encode_cmd(args, info, in_pattern: str, out_fps: str, out_file: Path) -> list[str]:
    vf = build_vf(args, info)
    cmd = [str(tools.ffmpeg()), "-y", "-framerate", out_fps]
    if args.hdr == "on":
        # Tag the extracted-frame PNG sequence as BT.709 SDR on the input side.
        # PNGs carry no colorspace metadata, so without this some ffmpeg/zimg
        # builds fail the HDR chain's zscale=...t=linear conversion with
        # "no path between colorspaces" (zscale can't infer a source
        # colorimetry to convert *from*). Source frames are SDR, so bt709 is
        # the correct assumption regardless of build.
        cmd += ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
    cmd += ["-start_number", "1", "-i", in_pattern, "-vf", vf]

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


def run(cmd: list[str], quiet: bool = True, cwd=None) -> None:
    child = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL if quiet else None,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=_NOWINDOW,
        cwd=cwd,
    )
    stderr: list[str] = []

    def drain_stderr() -> None:
        if child.stderr:
            stderr.append(child.stderr.read())

    reader = threading.Thread(target=drain_stderr, daemon=True)
    reader.start()
    while child.poll() is None:
        if cancel_requested():
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            reader.join()
            raise Cancelled
        time.sleep(0.1)
    reader.join()
    if child.returncode != 0:
        die(f"command failed ({cmd[0]}):\n{''.join(stderr)[-2000:]}")


def fmt_eta(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}h{m:02d}m" if h else f"{m:d}m{s:02d}s"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="AI upscale a video and remap it to vibrant HDR10.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("input", nargs="?", type=Path,
                    help="source video (default: the single video in ./input)")
    ap.add_argument("-o", "--output", type=Path,
                    help="output file (default: ./output/<name>_<scale>x_<hdr|sdr>.mp4)")
    ap.add_argument("--scale", type=int, default=2, choices=[2, 3, 4], help="upscale factor")
    ap.add_argument("--model", default="animevideo", choices=list(MODEL_MAP),
                    help="Real-ESRGAN model (animevideo=fast/video, x4plus=sharp photo)")
    ap.add_argument("--style", choices=list(recipes.STYLES),
                    help="one-tap named look (sets the knobs; explicit flags still win)")
    ap.add_argument("--recipe", type=Path, help="load a saved recipe .json")
    ap.add_argument("--save-recipe", type=Path, dest="save_recipe",
                    help="write the effective recipe to .json and continue")
    ap.add_argument("--target", choices=list(recipes.TARGETS), default="source",
                    help="delivery target: crop/pad + SDR for social (reel/tiktok/post/x/web)")
    ap.add_argument("--lut", type=Path, help="apply a 3D LUT (.cube) after the grade")
    ap.add_argument("--curve", default="",
                    help="custom master curve points 'x/y x/y …' (overrides the contrast S-curve)")
    ap.add_argument("--vibrance", default="vibrant", choices=list(grade.PRESETS),
                    help="grade preset (base for the --grade knobs below)")
    # per-knob grade overrides (default None -> take the preset's value)
    grp = ap.add_argument_group("grade overrides (leave unset to use the preset)")
    grp.add_argument("--saturation", type=float, help="1.0 = unchanged")
    grp.add_argument("--vibrance-amt", type=float, dest="vibrance_amt",
                     help="selective saturation, 0..1")
    grp.add_argument("--contrast", type=float, help="S-curve strength, 0..1")
    grp.add_argument("--gamma", type=float, help="midtone lift, >1 brighter")
    grp.add_argument("--warmth", type=float, help="-1 cool .. +1 warm")
    grp.add_argument("--tint", type=float, help="-1 green .. +1 magenta")
    grp.add_argument("--exposure", type=float, help="-1 .. +1 overall brightness")
    grp.add_argument("--sharpen", type=float, help="unsharp amount, 0..1.5")
    grp.add_argument("--hdr-gain", type=float, default=1.5, dest="hdr_gain",
                     help="HDR highlight expansion")
    grp.add_argument("--preview", action="store_true",
                     help="render before/after grade stills (no full run) and exit")
    grp.add_argument("--at", help="comma-separated seconds for --preview (default: 20/50/80%%)")
    grp.add_argument("--upscale", action="store_true",
                     help="with --preview: AI-upscale the 'after' half (see real detail)")
    ap.add_argument("--batch", action="store_true",
                    help="process every video in ./input sequentially")
    ap.add_argument("--hdr", default="on", choices=["on", "off"],
                    help="remap to HDR10 (on) or stay SDR BT.709 (off)")
    ap.add_argument("--encoder", default="x265", choices=["x265", "qsv"],
                    help="x265=software (best HDR fidelity), qsv=Intel GPU (faster)")
    ap.add_argument("--crf", type=int, default=19, help="quality (lower=better, 18-23 typical)")
    ap.add_argument("--preset", default="medium", help="x264/x265 preset")
    ap.add_argument("--start", type=float, default=0.0, help="trim: start seconds")
    ap.add_argument("--duration", type=float, help="trim: seconds to process (default: to end)")
    ap.add_argument("--no-audio", action="store_true", dest="no_audio", help="drop audio")
    ap.add_argument("--interpolate", type=int, default=0, choices=[0, 2, 3, 4],
                    help="RIFE frame interpolation (0=off, 2=2x smoother/~60fps)")
    ap.add_argument("--slowmo", action="store_true",
                    help="with --interpolate: keep fps (slow-motion) instead of smoother")
    ap.add_argument("--deinterlace", action="store_true", help="restore: deinterlace (bwdif)")
    ap.add_argument("--denoise", choices=["off", "light", "medium", "strong"], default="off",
                    help="restore: denoise before upscaling")
    ap.add_argument("--stabilize", action="store_true",
                    help="restore: stabilize shaky footage (vidstab, 2-pass)")
    ap.add_argument("--chunk", type=int, default=300, help="frames encoded per chunk")
    ap.add_argument("--gpu", type=int, default=0, help="Real-ESRGAN GPU id (-1 = CPU)")
    ap.add_argument("--tile", type=int, default=0, help="Real-ESRGAN tile size (0=auto)")
    ap.add_argument("--work", type=Path, help="scratch dir (default: system temp)")
    ap.add_argument("--resume", action="store_true", help="reuse frames/chunks already done")
    ap.add_argument("--keep", action="store_true", help="keep scratch files after finishing")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    ap.add_argument("--dump-config", action="store_true", dest="dump_config",
                    help=argparse.SUPPRESS)   # emit styles/targets/knobs as JSON (for GUIs)
    ap.add_argument("--progress-json", action="store_true",
                    help="emit versioned NDJSON progress events on stdout")
    ap.add_argument("--run-id", help=argparse.SUPPRESS)
    ap.add_argument("--cancel-file", type=Path, help=argparse.SUPPRESS)
    args = ap.parse_args()

    global REPORTER, CANCEL_FILE, WORK_DIR
    REPORTER = Reporter(args.progress_json, args.run_id)
    CANCEL_FILE = args.cancel_file.expanduser() if args.cancel_file else None
    WORK_DIR = None
    if CANCEL_FILE and not CANCEL_FILE.is_absolute():
        die("--cancel-file must be an absolute path")
    stages.set_cancel_checker(cancel_requested)

    if args.dump_config and args.progress_json:
        die("--dump-config cannot be combined with --progress-json")
    if args.progress_json:
        # Keep legacy print calls readable while reserving original stdout for
        # NDJSON events. Reporter captured stdout before this redirection.
        sys.stdout = REPORTER.stderr

    if args.dump_config:
        import dataclasses
        print(json.dumps({
            "styles": {n: dataclasses.asdict(r) for n, r in recipes.STYLES.items()},
            "targets": list(recipes.TARGETS.keys()),
            "grade_knobs": list(recipes.GRADE_KNOBS),
            "models": list(MODEL_MAP.keys()),
        }))
        return

    # recipe / style overlay (explicit flags always win)
    given = {a.split("=")[0] for a in sys.argv[1:] if a.startswith("--")}
    if args.recipe:
        recipes.apply_to_args(recipes.load(args.recipe), args, given)
    if args.style:
        recipes.apply_to_args(recipes.STYLES[args.style], args, given)
    if args.target and args.target != "source":     # social targets force SDR
        th = recipes.target_hdr(args.target)
        if th and "--hdr" not in given:
            args.hdr = th
    if args.save_recipe:
        g = resolve_grade(args)
        rc = recipes.Recipe(
            scale=args.scale, model=args.model, hdr=args.hdr, encoder=args.encoder,
            crf=args.crf, preset=args.preset, hdr_gain=args.hdr_gain,
            grade={k: getattr(g, k) for k in recipes.GRADE_KNOBS},
            trim_start=args.start, trim_dur=args.duration or 0.0, audio=not args.no_audio,
            interpolate=args.interpolate, slowmo=args.slowmo,
            deinterlace=args.deinterlace, denoise=args.denoise, stabilize=args.stabilize,
            lut=str(args.lut) if args.lut else "", target=args.target, curve=args.curve)
        recipes.save(rc, args.save_recipe)
        print(f"[recipe] saved -> {args.save_recipe}")

    # LUT: copy to a no-space cache and reference by bare name (ffmpeg's
    # filtergraph parser can't handle the Windows drive-colon in a path).
    args._lut_cwd = None
    if args.lut:
        dest = tools.APP_CACHE / "lut.cube"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.lut, dest)
        args.lut = "lut.cube"
        args._lut_cwd = str(tools.APP_CACHE)

    check_deps()
    check_cancelled()

    if args.batch:
        vids = ([p for p in sorted(INPUT_DIR.glob("*")) if p.suffix.lower() in VIDEO_EXTS]
                if INPUT_DIR.exists() else [])
        if not vids:
            die(f"--batch: no videos found in {INPUT_DIR}")
        passthrough = [a for a in sys.argv[1:] if a != "--batch"]
        print(f"[batch] {len(vids)} videos in {INPUT_DIR}")
        for i, v in enumerate(vids, 1):
            print(f"\n===== batch {i}/{len(vids)}: {v.name} =====", flush=True)
            r = subprocess.run([sys.executable, "-m", "auvide.cli", str(v)]
                               + passthrough)
            if r.returncode != 0:
                print(f"[batch] {v.name} failed (exit {r.returncode}) — continuing")
        print("\n[batch] done")
        return

    src = resolve_input(args.input)

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

    out = (args.output or OUTPUT_DIR / f"{src.stem}_{args.scale}x_"
           f"{'hdr' if args.hdr=='on' else 'sdr'}.mp4").resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    work = (args.work or Path(tempfile.gettempdir()) / "auvide" / src.stem).resolve()
    WORK_DIR = work
    frames_in = work / "frames_in"
    seg_dir = work / "segments"
    for d in (frames_in, seg_dir):
        d.mkdir(parents=True, exist_ok=True)

    # effective (possibly trimmed) frame count
    expected = info["total"]
    if args.duration:
        expected = min(expected, int(round(args.duration * info["fps"])))
    elif args.start:
        expected = max(1, expected - int(round(args.start * info["fps"])))
    n_chunks = math.ceil(expected / args.chunk)
    progress_stages = []
    if args.stabilize:
        progress_stages.append("stabilize_analysis")
    progress_stages.append("extract")
    progress_stages.append("upscale")
    if args.interpolate and args.interpolate > 1:
        progress_stages.append("interpolate")
    progress_stages.extend(["encode", "concat_mux"])
    if not args.keep:
        progress_stages.append("cleanup")

    def stage_started(stage: str, **extra) -> None:
        REPORTER.event("stage_started", stage=stage,
                       ordinal=progress_stages.index(stage) + 1,
                       stage_count=len(progress_stages), **extra)

    def stage_completed(stage: str, **extra) -> None:
        REPORTER.event("stage_completed", stage=stage, **extra)

    REPORTER.event(
        "plan", input=str(src), output=str(out), total_frames=expected,
        total_chunks=n_chunks, stages=progress_stages,
    )
    trim = f"  trim        {args.start:g}s"
    trim += f" +{args.duration:g}s" if args.duration else " -> end"

    print("=" * 60)
    print(f"  auvide  |  {src.name}")
    print("=" * 60)
    print(f"  source      {info['width']}x{info['height']}  "
          f"{info['fps']:.3f} fps  {info['total']} frames  "
          f"{fmt_eta(info['duration'])}")
    print(f"  target      {tw}x{th}  ({args.scale}x)")
    print(f"  model       {model_name}  (realesrgan -s {realesr_scale})")
    if args.interpolate and args.interpolate > 1:
        print(f"  interpolate {args.interpolate}x RIFE "
              f"({'slow-mo' if args.slowmo else 'smooth'})")
    rest = [n for n, on in (("deinterlace", args.deinterlace),
                            (f"denoise:{args.denoise}", args.denoise != "off"),
                            ("stabilize", args.stabilize)) if on]
    if rest:
        print(f"  restore     {', '.join(rest)}")
    if args.lut:
        print(f"  lut         {Path(args.lut).name}")
    if args.target and args.target != "source":
        _, (dw, dh) = recipes.target_transform(args.target, tw, th)
        print(f"  deliver     {args.target}  {dw}x{dh}")
    style_s = f"style={args.style}  " if args.style else ""
    print(f"  grade       {args.hdr.upper()}  {style_s}encoder={args.encoder}  crf={args.crf}")
    if args.start or args.duration:
        print(trim + f"   (~{expected} frames)")
    print(f"  chunks      {n_chunks} x {args.chunk} frames")
    print(f"  work dir    {work}")
    print(f"  output      {out}")
    print("=" * 60)
    if args.dry_run:
        return
    if args.preview:
        check_cancelled()
        make_preview(args, src, info)
        return

    # ---- phase 1: extract all frames (with restoration pre-processing) ---
    # deinterlace/denoise/stabilize run before upscaling so the AI gets clean input
    pre = []
    if args.deinterlace:
        pre.append("bwdif")
    if args.denoise != "off":
        pre.append(DENOISE[args.denoise])

    marker = frames_in / ".extracted"
    sig = (f"{args.start}|{args.duration}|{args.deinterlace}|{args.denoise}|"
           f"{args.stabilize}")
    have = len(list(frames_in.glob("frame_*.png")))
    if (args.resume and marker.exists() and marker.read_text() == sig
            and have >= expected - 1):
        stage_started("extract")
        print(f"[1/3] frames: reusing {have} extracted frames")
        stage_completed("extract")
    else:
        check_cancelled()
        cwd = None
        if args.stabilize:
            stage_started("stabilize_analysis")
            print("[1/3] stabilize pass 1 (motion analysis) ...", flush=True)
            cwd = str(work)                    # bare .trf name; cwd avoids the drive-colon
            det = [str(tools.ffmpeg()), "-y"]
            if args.start:
                det += ["-ss", str(args.start)]
            det += ["-i", str(src)]
            if args.duration:
                det += ["-t", str(args.duration)]
            det += ["-vf", "vidstabdetect=result=transforms.trf", "-f", "null", "-"]
            run(det, cwd=cwd)
            stage_completed("stabilize_analysis")
            pre.append("vidstabtransform=input=transforms.trf:smoothing=20")
        stage_started("extract")
        print(f"[1/3] extracting {expected} frames ...", flush=True)
        t0 = time.time()
        ex = [str(tools.ffmpeg()), "-y"]
        if args.start:
            ex += ["-ss", str(args.start)]
        ex += ["-i", str(src)]
        if args.duration:
            ex += ["-t", str(args.duration)]
        if pre:
            ex += ["-vf", ",".join(pre)]
        ex += ["-vsync", "passthrough", str(frames_in / "frame_%06d.png")]
        run(ex, cwd=cwd)
        marker.write_text(sig)
        have = len(list(frames_in.glob("frame_*.png")))
        print(f"      extracted {have} frames in {fmt_eta(time.time()-t0)}")
        stage_completed("extract")

    total = have  # actual frames on disk (may differ from container's nb_frames)
    n_chunks = math.ceil(total / args.chunk)

    frame_stages = stages.build_frame_stages(args)
    fmult = stages.total_frame_multiplier(frame_stages)
    smooth = not args.slowmo
    if fmult > 1 and smooth:
        out_fps = f"{info['fps_num'] * fmult}/{info['fps_den']}"
    else:
        out_fps = f"{info['fps_num']}/{info['fps_den']}"
    chain = " -> ".join(s.label for s in frame_stages)

    # ---- phase 2: process + encode each chunk ----------------------------
    stage_started("upscale")
    if args.interpolate and args.interpolate > 1:
        stage_started("interpolate")
    stage_started("encode")
    print(f"[2/3] {chain} + encode ({total} frames, {n_chunks} chunks) ...", flush=True)
    batch_in = work / "batch_in"
    done_frames = 0
    run_start = time.time()

    for c in range(n_chunks):
        check_cancelled()
        start = c * args.chunk + 1                     # 1-based global index
        if start > total:
            break
        end = min(start + args.chunk - 1, total)
        count = end - start + 1
        seg = seg_dir / f"seg_{c:05d}.mp4"

        if args.resume and seg.exists() and seg.stat().st_size > 0:
            print(f"      chunk {c+1}/{n_chunks}: skip (done)")
            done_frames += count
            REPORTER.event("progress", stage="encode", current=c + 1, total=n_chunks,
                           unit="chunks", chunk=c + 1)
            continue

        # fresh batch input
        if batch_in.exists():
            shutil.rmtree(batch_in)
        batch_in.mkdir(parents=True)
        for i in range(start, end + 1):
            name = f"frame_{i:06d}.png"
            shutil.copy2(frames_in / name, batch_in / name)

        t0 = time.time()
        cur = batch_in
        try:
            for si, stage in enumerate(frame_stages):     # upscale -> [interpolate] -> ...
                nxt = work / f"batch_s{si}"
                if nxt.exists():
                    shutil.rmtree(nxt)
                nxt.mkdir(parents=True)
                stage.process(cur, nxt)
                if cur is not batch_in:
                    shutil.rmtree(cur, ignore_errors=True)
                cur = nxt
        except stages.StageCancelled:
            raise Cancelled
        except stages.StageError as e:
            die(str(e))
        pattern = normalize_seq(cur)
        run(encode_cmd(args, info, pattern, out_fps, seg), cwd=args._lut_cwd)
        shutil.rmtree(cur, ignore_errors=True)

        done_frames += count
        elapsed = time.time() - run_start
        rate = done_frames / elapsed if elapsed else 0
        remaining = (total - done_frames) / rate if rate else 0
        print(f"      chunk {c+1}/{n_chunks}: {count} frames in "
              f"{fmt_eta(time.time()-t0)}  |  {rate:.2f} fps  |  ETA {fmt_eta(remaining)}",
              flush=True)
        REPORTER.event("progress", stage="encode", current=c + 1, total=n_chunks,
                       unit="chunks", chunk=c + 1)

    stage_completed("upscale")
    if args.interpolate and args.interpolate > 1:
        stage_completed("interpolate")
    stage_completed("encode")

    # tidy transient batch dirs
    for d in list(work.glob("batch_*")):
        shutil.rmtree(d, ignore_errors=True)

    # ---- phase 3: concat + mux audio -------------------------------------
    check_cancelled()
    stage_started("concat_mux")
    print("[3/3] concatenating chunks + muxing audio ...", flush=True)
    segs = sorted(seg_dir.glob("seg_*.mp4"))
    if not segs:
        die("no encoded segments were produced")
    list_file = work / "concat.txt"
    list_file.write_text("".join(f"file '{s.as_posix()}'\n" for s in segs))

    concat_cmd = [str(tools.ffmpeg()), "-y", "-f", "concat", "-safe", "0", "-i", str(list_file)]
    # slow-mo changes duration, so audio can't be kept in sync -> drop it
    keep_audio = info["has_audio"] and not args.no_audio and (fmult == 1 or smooth)
    if keep_audio:
        au = []                                  # trim audio to match the video
        if args.start:
            au += ["-ss", str(args.start)]
        if args.duration:
            au += ["-t", str(args.duration)]
        au += ["-i", str(src)]
        concat_cmd += au + ["-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "copy"]
    else:
        concat_cmd += ["-map", "0:v:0", "-c:v", "copy"]
    concat_cmd += ["-movflags", "+faststart", str(out)]
    run(concat_cmd)
    stage_completed("concat_mux")

    # ---- done ------------------------------------------------------------
    if not args.keep:
        stage_started("cleanup")
        shutil.rmtree(work, ignore_errors=True)
        stage_completed("cleanup")

    size_mb = out.stat().st_size / (1024 * 1024)
    eff_fps = info["fps"] * fmult if smooth else info["fps"]
    print("=" * 60)
    print(f"  done  ->  {out}")
    print(f"  {tw}x{th}  {eff_fps:.3f} fps  {size_mb:.1f} MB  "
          f"total {fmt_eta(time.time()-run_start)}")
    print("=" * 60)
    REPORTER.event("completed", output=str(out))


if __name__ == "__main__":
    try:
        main()
    except Cancelled:
        finish_cancelled()
    except KeyboardInterrupt:
        finish_cancelled()
