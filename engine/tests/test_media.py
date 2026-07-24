"""Tests for the versioned FFprobe normalization contract."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from auvide import media

FIXTURES = Path(__file__).parent / "fixtures" / "contracts"


def sdr_payload() -> dict:
    return {
        "streams": [
            {
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30000/1001",
                "r_frame_rate": "30000/1001",
                "nb_frames": "18000",
                "codec_name": "h264",
                "pix_fmt": "yuv420p",
                "color_primaries": "bt709",
                "color_transfer": "bt709",
                "color_space": "bt709",
                "field_order": "progressive",
            },
            {"codec_type": "audio", "codec_name": "aac", "channels": 2},
        ],
        "format": {
            "duration": "600.6",
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "size": "123456789",
        },
    }


def test_normalize_matches_the_reviewed_sdr_contract(tmp_path):
    source = tmp_path / "source.mp4"
    inspection = media.normalize(source, sdr_payload())
    expected = json.loads((FIXTURES / "media_sdr.json").read_text())
    expected["path"] = str(source.resolve())

    assert inspection.to_dict() == expected
    assert inspection.render_info() == {
        "width": 1920,
        "height": 1080,
        "fps_num": 30000,
        "fps_den": 1001,
        "fps": 30000 / 1001,
        "total": 18000,
        "has_audio": True,
        "duration": 600.6,
    }


def test_normalize_marks_variable_rate_and_incomplete_metadata(tmp_path):
    payload = sdr_payload()
    video = payload["streams"][0]
    video.pop("nb_frames")
    video.pop("color_primaries")
    video.pop("color_transfer")
    video["avg_frame_rate"] = "24/1"
    video["r_frame_rate"] = "30/1"
    video["field_order"] = "tt"
    payload["format"].pop("duration")

    inspection = media.normalize(tmp_path / "vfr.mov", payload)
    data = inspection.to_dict()

    assert data["video"]["frames"] is None
    assert data["video"]["variable_frame_rate"] is True
    assert data["video"]["interlaced"] is True
    assert data["audio"]["present"] is True
    assert {warning["code"] for warning in data["warnings"]} == {
        "source.frame_count.unavailable",
        "source.color.metadata_missing",
    }


def test_normalize_accepts_10_bit_video_and_missing_audio(tmp_path):
    payload = sdr_payload()
    payload["streams"] = [payload["streams"][0]]
    payload["streams"][0]["pix_fmt"] = "yuv420p10le"
    payload["streams"][0]["bits_per_raw_sample"] = "10"

    inspection = media.normalize(tmp_path / "hdr.mkv", payload)

    assert inspection.bit_depth == 10
    assert inspection.has_audio is False
    assert inspection.audio_codec is None


def test_normalize_rejects_sources_without_a_video_stream(tmp_path):
    with pytest.raises(media.MediaError, match="no video stream"):
        media.normalize(tmp_path / "audio.m4a", {"streams": [{"codec_type": "audio"}]})


def test_inspect_reports_invalid_ffprobe_json(monkeypatch, tmp_path):
    source = tmp_path / "source.mp4"
    monkeypatch.setattr(media.tools, "ffprobe", lambda: "ffprobe")

    class Result:
        returncode = 0
        stdout = "not json"
        stderr = ""

    monkeypatch.setattr(media.subprocess, "run", lambda *args, **kwargs: Result())
    with pytest.raises(media.MediaError, match="invalid JSON"):
        media.inspect(source)
