"""Normalized FFprobe inspection for desktop and automation clients.

The render pipeline needs a compact frame/size dictionary, while GUI and CLI
clients need stable, explicit metadata. This module owns both representations
so the desktop never interprets FFprobe's inconsistent raw fields itself.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import tools

SCHEMA = "auvide.media"
VERSION = 1


class MediaError(RuntimeError):
    """Source probing failed or produced no usable video stream."""


@dataclass(frozen=True)
class Rational:
    numerator: int
    denominator: int

    @property
    def value(self) -> float:
        return self.numerator / self.denominator

    def to_dict(self) -> dict[str, int]:
        return {"numerator": self.numerator, "denominator": self.denominator}


@dataclass(frozen=True)
class MediaInspection:
    path: str
    width: int
    height: int
    fps: Rational
    frames: int | None
    duration_seconds: float | None
    codec: str | None
    pixel_format: str | None
    bit_depth: int | None
    color_primaries: str | None
    transfer: str | None
    color_space: str | None
    interlaced: bool | None
    variable_frame_rate: bool | None
    has_audio: bool
    audio_codec: str | None
    audio_channels: int | None
    container_format: str | None
    size_bytes: int | None
    warnings: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "version": VERSION,
            "path": self.path,
            "video": {
                "width": self.width,
                "height": self.height,
                "fps": self.fps.to_dict(),
                "frames": self.frames,
                "duration_seconds": self.duration_seconds,
                "codec": self.codec,
                "pixel_format": self.pixel_format,
                "bit_depth": self.bit_depth,
                "color_primaries": self.color_primaries,
                "transfer": self.transfer,
                "color_space": self.color_space,
                "interlaced": self.interlaced,
                "variable_frame_rate": self.variable_frame_rate,
            },
            "audio": {
                "present": self.has_audio,
                "codec": self.audio_codec,
                "channels": self.audio_channels,
            },
            "container": {
                "format": self.container_format,
                "size_bytes": self.size_bytes,
            },
            "warnings": list(self.warnings),
        }

    def render_info(self) -> dict[str, Any]:
        """Return the compact, backwards-compatible metadata used by render."""
        total = self.frames
        if total is None and self.duration_seconds is not None:
            total = round(self.duration_seconds * self.fps.value)
        return {
            "width": self.width,
            "height": self.height,
            "fps_num": self.fps.numerator,
            "fps_den": self.fps.denominator,
            "fps": self.fps.value,
            "total": total or 0,
            "has_audio": self.has_audio,
            "duration": self.duration_seconds or 0.0,
        }


def inspect(source: Path) -> MediaInspection:
    """Run FFprobe and normalize its output into the stable media contract."""
    ffprobe = tools.ffprobe()
    if not ffprobe:
        detail = tools.override_error(tools.ENV_FFPROBE)
        raise MediaError(detail or "ffprobe is required to inspect source media")
    result = subprocess.run(
        [str(ffprobe), "-v", "error", "-print_format", "json", "-show_streams",
         "-show_format", str(source)],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise MediaError(f"ffprobe failed:\n{result.stderr.strip()}")
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise MediaError(f"ffprobe returned invalid JSON: {error}") from error
    return normalize(source, raw)


def normalize(source: Path, raw: dict[str, Any]) -> MediaInspection:
    """Normalize an FFprobe JSON payload without invoking external tools."""
    raw_streams = raw.get("streams")
    streams = raw_streams if isinstance(raw_streams, list) else []
    video = next(
        (stream for stream in streams
         if isinstance(stream, dict) and stream.get("codec_type") == "video"),
        None,
    )
    audio = next(
        (stream for stream in streams
         if isinstance(stream, dict) and stream.get("codec_type") == "audio"),
        None,
    )
    if not isinstance(video, dict):
        raise MediaError("no video stream found in input")
    raw_container = raw.get("format")
    container: dict[str, Any] = raw_container if isinstance(raw_container, dict) else {}
    fps = _parse_rate(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    native_rate = _parse_rate(video.get("r_frame_rate"))
    duration = _positive_float(video.get("duration")) or _positive_float(container.get("duration"))
    frames = _positive_int(video.get("nb_frames"))
    warnings: list[dict[str, str]] = []
    if frames is None and duration is None:
        warnings.append({
            "code": "source.frame_count.unavailable",
            "message": "Frame count and duration are unavailable; render estimates may be incomplete.",
        })
    if not _clean_string(video.get("color_primaries")) or not _clean_string(video.get("color_transfer")):
        warnings.append({
            "code": "source.color.metadata_missing",
            "message": "Source color metadata is incomplete; auvide will use its documented SDR assumptions.",
        })

    field_order = _clean_string(video.get("field_order"))
    interlaced = None if field_order is None else field_order not in {"progressive", "unknown"}
    variable_frame_rate = None
    if native_rate is not None:
        variable_frame_rate = native_rate != fps

    return MediaInspection(
        path=str(source.resolve()),
        width=_required_positive_int(video.get("width"), "video width"),
        height=_required_positive_int(video.get("height"), "video height"),
        fps=fps,
        frames=frames,
        duration_seconds=duration,
        codec=_clean_string(video.get("codec_name")),
        pixel_format=_clean_string(video.get("pix_fmt")),
        bit_depth=_bit_depth(video),
        color_primaries=_clean_string(video.get("color_primaries")),
        transfer=_clean_string(video.get("color_transfer")),
        color_space=_clean_string(video.get("color_space")),
        interlaced=interlaced,
        variable_frame_rate=variable_frame_rate,
        has_audio=isinstance(audio, dict),
        audio_codec=_clean_string(audio.get("codec_name")) if isinstance(audio, dict) else None,
        audio_channels=_positive_int(audio.get("channels")) if isinstance(audio, dict) else None,
        container_format=_clean_string(container.get("format_name")),
        size_bytes=_positive_int(container.get("size")),
        warnings=tuple(warnings),
    )


def format_human(inspection: MediaInspection) -> str:
    """Concise human view for the CLI without compromising JSON consumers."""
    data = inspection.to_dict()
    video = data["video"]
    audio = data["audio"]
    lines = [
        f"Source: {data['path']}",
        (
            f"Video: {video['width']}x{video['height']}  {inspection.fps.value:.3f} fps  "
            f"{video['codec'] or 'unknown codec'}  {video['pixel_format'] or 'unknown format'}"
        ),
        (
            f"Duration: {video['duration_seconds'] if video['duration_seconds'] is not None else 'unknown'} s  "
            f"Frames: {video['frames'] if video['frames'] is not None else 'unknown'}"
        ),
        f"Audio: {'yes' if audio['present'] else 'no'}"
        + (f" ({audio['codec']})" if audio['codec'] else ""),
    ]
    lines.extend(f"Warning [{warning['code']}]: {warning['message']}" for warning in data["warnings"])
    return "\n".join(lines)


def _parse_rate(value: Any) -> Rational:
    text = _clean_string(value)
    if not text or "/" not in text:
        return Rational(24, 1)
    numerator, denominator = text.split("/", 1)
    try:
        num = int(numerator)
        den = int(denominator)
    except ValueError:
        return Rational(24, 1)
    if num <= 0 or den <= 0:
        return Rational(24, 1)
    return Rational(num, den)


def _bit_depth(video: dict[str, Any]) -> int | None:
    explicit = _positive_int(video.get("bits_per_raw_sample"))
    if explicit is not None:
        return explicit
    pixel_format = _clean_string(video.get("pix_fmt")) or ""
    for token in pixel_format.split("p"):
        if token.endswith(("le", "be")):
            candidate = token[:-2]
            if candidate.isdigit():
                return int(candidate)
    return 8 if pixel_format else None


def _clean_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _required_positive_int(value: Any, label: str) -> int:
    parsed = _positive_int(value)
    if parsed is None:
        raise MediaError(f"input has no valid {label}")
    return parsed


def _positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
