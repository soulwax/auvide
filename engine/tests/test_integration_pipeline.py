"""End-to-end integration test: synthetic clip -> full auvide pipeline -> HDR10
output, verified via ffprobe.

This is the test that protects the actual product promise (BT.2020 + PQ,
10-bit HEVC, audio retained, frame count preserved) without needing a GPU or
the real Real-ESRGAN binary: a stub "realesrgan-ncnn-vulkan" is placed on PATH
that upscales frames with ffmpeg's nearest-neighbor scaler instead of an AI
model — visually wrong, but byte-for-byte exercises the same subprocess
plumbing (stages.py, chunking, resume markers, concat, mux) as a real run.

Skipped automatically if ffmpeg/ffprobe aren't on PATH (e.g. a minimal CI
image that hasn't installed them).
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
FIXTURES = Path(__file__).parent / "fixtures"

pytestmark = pytest.mark.skipif(
    not (FFMPEG and FFPROBE), reason="ffmpeg/ffprobe not found on PATH")


@pytest.fixture
def fake_realesrgan_on_path(tmp_path):
    """Prepend a directory containing a `realesrgan-ncnn-vulkan` shim (backed
    by fake_realesrgan.py) onto PATH, and a fake model file so tools.py's
    models_dir() resolves. Yields the modified PATH-prefix dir."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    stub = FIXTURES / "fake_realesrgan.py"

    if sys.platform == "win32":
        shim = bin_dir / "realesrgan-ncnn-vulkan.bat"
        shim.write_text(f'@echo off\r\n"{sys.executable}" "{stub}" %*\r\n')
    else:
        shim = bin_dir / "realesrgan-ncnn-vulkan"
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{stub}" "$@"\n')
        shim.chmod(shim.stat().st_mode | stat.S_IEXEC)

    models_dir = bin_dir / "models"
    models_dir.mkdir()
    (models_dir / "realesr-animevideov3.param").write_text("")
    (models_dir / "realesr-animevideov3.bin").write_text("")

    yield bin_dir


@pytest.fixture
def synthetic_clip(tmp_path):
    """A ~1s, 24fps, 64x64 test clip with a 1kHz sine audio track."""
    src = tmp_path / "src.mp4"
    subprocess.run([
        FFMPEG, "-y", "-f", "lavfi", "-i", "testsrc2=size=64x64:duration=1:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
        "-shortest", "-pix_fmt", "yuv420p", str(src),
    ], check=True, capture_output=True)
    return src


def ffprobe_json(path: Path) -> dict:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-print_format", "json", "-show_streams",
         "-show_format", str(path)],
        check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def run_cli(args, cwd, env):
    return subprocess.run(
        [sys.executable, "-m", "auvide.cli", *args],
        cwd=str(cwd), env=env, capture_output=True, text=True, check=False)


@pytest.fixture
def env_with_fake_tools(fake_realesrgan_on_path, monkeypatch):
    env = dict(os.environ)
    env["PATH"] = str(fake_realesrgan_on_path) + os.pathsep + env.get("PATH", "")
    env["LOCALAPPDATA"] = str(fake_realesrgan_on_path)  # tools.py's APP_CACHE fallback, unused here
    return env


def test_inspect_json_exposes_normalized_media(synthetic_clip, tmp_path):
    result = run_cli([str(synthetic_clip), "--inspect-json"], cwd=tmp_path, env=dict(os.environ))

    assert result.returncode == 0, result.stderr
    inspection = json.loads(result.stdout)
    assert inspection["schema"] == "auvide.media"
    assert inspection["version"] == 1
    assert inspection["video"]["width"] == 64
    assert inspection["video"]["height"] == 64
    assert inspection["video"]["fps"] == {"numerator": 24, "denominator": 1}
    assert inspection["audio"]["present"] is True


def test_hdr10_render_end_to_end(synthetic_clip, tmp_path, env_with_fake_tools):
    out = tmp_path / "out.mp4"
    work = tmp_path / "work"
    result = run_cli([
        str(synthetic_clip), "-o", str(out), "--scale", "2", "--hdr", "on",
        "--work", str(work), "--chunk", "100", "--vibrance", "none",
    ], cwd=tmp_path, env=env_with_fake_tools)

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert out.exists(), "no output file produced"

    info = ffprobe_json(out)
    vstream = next(s for s in info["streams"] if s["codec_type"] == "video")
    astream = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)

    # resolution doubled (2x scale)
    assert vstream["width"] == 128
    assert vstream["height"] == 128

    # HDR10 tagging: BT.2020 primaries + PQ (SMPTE 2084) transfer, 10-bit
    assert vstream["color_primaries"] == "bt2020"
    assert vstream["color_transfer"] == "smpte2084"
    assert vstream["pix_fmt"] == "yuv420p10le"

    # audio retained
    assert astream is not None, "audio track was dropped"

    # frame count preserved (no dropped/duplicated frames through the pipeline)
    nb = vstream.get("nb_frames")
    if nb and nb.isdigit():
        assert int(nb) == 24


def test_sdr_render_stays_bt709(synthetic_clip, tmp_path, env_with_fake_tools):
    out = tmp_path / "out_sdr.mp4"
    work = tmp_path / "work"
    result = run_cli([
        str(synthetic_clip), "-o", str(out), "--scale", "2", "--hdr", "off",
        "--work", str(work), "--chunk", "100", "--vibrance", "none",
    ], cwd=tmp_path, env=env_with_fake_tools)

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    info = ffprobe_json(out)
    vstream = next(s for s in info["streams"] if s["codec_type"] == "video")
    # ffprobe reports colorimetry under different keys depending on codec:
    # HEVC (libx265) -> color_primaries/color_transfer; H.264 (libx264) often
    # collapses all three into a single `color_space` field instead. Accept
    # either so this test isn't coupled to which encoder auvide defaults to.
    primaries = vstream.get("color_primaries") or vstream.get("color_space")
    assert primaries == "bt709"
    assert vstream["pix_fmt"] == "yuv420p"


def test_explicit_upscaler_overrides_work_without_path_entry(
        synthetic_clip, tmp_path, fake_realesrgan_on_path):
    """Desktop-managed tools must win without adding their folder to PATH."""
    out = tmp_path / "out_override.mp4"
    work = tmp_path / "work"
    suffix = ".bat" if sys.platform == "win32" else ""
    env = dict(os.environ)
    env["AUVIDE_REALESRGAN"] = str(fake_realesrgan_on_path / f"realesrgan-ncnn-vulkan{suffix}")
    env["AUVIDE_REALESRGAN_MODELS"] = str(fake_realesrgan_on_path / "models")

    result = run_cli([
        str(synthetic_clip), "-o", str(out), "--scale", "2", "--hdr", "off",
        "--work", str(work), "--chunk", "100", "--vibrance", "none",
    ], cwd=tmp_path, env=env)

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert out.exists()


def test_progress_json_is_pure_ndjson_with_ordered_terminal_events(
        synthetic_clip, tmp_path, env_with_fake_tools):
    out = tmp_path / "out_progress.mp4"
    work = tmp_path / "work"
    result = run_cli([
        str(synthetic_clip), "-o", str(out), "--scale", "2", "--hdr", "off",
        "--work", str(work), "--chunk", "100", "--vibrance", "none",
        "--progress-json", "--run-id", "integration-progress",
    ], cwd=tmp_path, env=env_with_fake_tools)

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    events = [json.loads(line) for line in result.stdout.splitlines() if line]
    assert events
    assert all(event["protocol"] == "auvide.progress" for event in events)
    assert all(event["version"] == 1 for event in events)
    assert all(event["run_id"] == "integration-progress" for event in events)
    assert events[0]["type"] == "plan"
    assert events[-1] == {
        "protocol": "auvide.progress",
        "version": 1,
        "run_id": "integration-progress",
        "type": "completed",
        "output": str(out),
    }
    assert any(event["type"] == "progress" and event["stage"] == "encode"
               for event in events)
    assert "[1/3]" not in result.stdout
    assert "[1/3]" in result.stderr


def test_cancel_after_completed_chunk_is_resumable(
        synthetic_clip, tmp_path, env_with_fake_tools):
    out = tmp_path / "out_cancelled.mp4"
    work = tmp_path / "work"
    cancel_file = tmp_path / "cancel.requested"
    common = [
        str(synthetic_clip), "-o", str(out), "--scale", "2", "--hdr", "off",
        "--work", str(work), "--chunk", "8", "--vibrance", "none", "--keep",
    ]
    child = subprocess.Popen(
        [sys.executable, "-m", "auvide.cli", *common, "--progress-json", "--run-id", "cancel-test",
         "--cancel-file", str(cancel_file)],
        cwd=str(tmp_path), env=env_with_fake_tools, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )
    assert child.stdout is not None
    events = []
    while True:
        line = child.stdout.readline()
        if not line:
            break
        event = json.loads(line)
        events.append(event)
        if event["type"] == "progress" and event["current"] >= 1:
            cancel_file.touch()
            break

    stdout, stderr = child.communicate(timeout=60)
    events.extend(json.loads(line) for line in stdout.splitlines() if line)

    assert child.returncode == 130, stderr
    assert events[-1]["type"] == "cancelled"
    assert events[-1]["resumable"] is True

    segments = sorted((work / "segments").glob("seg_*.mp4"))
    assert segments
    mtimes_before = {segment: segment.stat().st_mtime_ns for segment in segments}

    resumed = run_cli(common + ["--resume"], cwd=tmp_path, env=env_with_fake_tools)
    assert resumed.returncode == 0, resumed.stderr
    assert out.exists()
    for segment, before in mtimes_before.items():
        assert segment.stat().st_mtime_ns == before, f"{segment.name} was re-encoded after resume"


def test_resume_skips_completed_chunks(synthetic_clip, tmp_path, env_with_fake_tools):
    out = tmp_path / "out.mp4"
    work = tmp_path / "work"
    common = [str(synthetic_clip), "-o", str(out), "--scale", "2", "--hdr", "off",
              "--work", str(work), "--chunk", "8", "--vibrance", "none", "--keep"]

    first = run_cli(common, cwd=tmp_path, env=env_with_fake_tools)
    assert first.returncode == 0, first.stderr

    segments_dir = work / "segments"
    seg_files = sorted(segments_dir.glob("seg_*.mp4"))
    assert len(seg_files) >= 1
    mtimes_before = {f: f.stat().st_mtime_ns for f in seg_files}

    second = run_cli(common + ["--resume"], cwd=tmp_path, env=env_with_fake_tools)
    assert second.returncode == 0, second.stderr
    assert "skip" in second.stdout.lower() or "reusing" in second.stdout.lower()

    for f, before in mtimes_before.items():
        assert f.stat().st_mtime_ns == before, f"{f.name} was re-encoded on --resume"
