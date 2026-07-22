"""Tests for auvide.tools: PATH-based binary/model discovery.

No real ffmpeg/realesrgan install is required — shutil.which and the
filesystem are mocked/monkeypatched.
"""
from __future__ import annotations

from auvide import tools


def test_which_returns_first_match(monkeypatch):
    calls = []

    def fake_which(name):
        calls.append(name)
        return "/usr/bin/found" if name == "second" else None

    monkeypatch.setattr(tools.shutil, "which", fake_which)
    assert tools._which("first", "second", "third") == "/usr/bin/found"
    assert calls == ["first", "second"]  # stops at the first hit


def test_which_returns_none_when_nothing_found(monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)
    assert tools._which("a", "b") is None


def test_ffmpeg_ffprobe_delegate_to_which(monkeypatch):
    monkeypatch.setattr(tools, "_which", lambda *names: f"/bin/{names[0]}")
    assert tools.ffmpeg() == "/bin/ffmpeg"
    assert tools.ffprobe() == "/bin/ffprobe"


def test_realesrgan_tries_both_names(monkeypatch):
    seen = {}
    monkeypatch.setattr(tools, "_which", lambda *names: seen.setdefault("names", names) and None)
    tools.realesrgan()
    assert seen["names"] == ("realesrgan-ncnn-vulkan", "realesrgan")


def test_missing_reports_each_unresolved_prerequisite(monkeypatch):
    monkeypatch.setattr(tools, "ffmpeg", lambda: None)
    monkeypatch.setattr(tools, "ffprobe", lambda: "/bin/ffprobe")
    monkeypatch.setattr(tools, "realesrgan", lambda: None)
    monkeypatch.setattr(tools, "models_dir", lambda: None)
    m = tools.missing()
    assert "ffmpeg" in m
    assert "ffprobe" not in m
    assert "realesrgan-ncnn-vulkan" in m
    assert "Real-ESRGAN models" in m


def test_missing_is_empty_when_everything_resolves(monkeypatch):
    monkeypatch.setattr(tools, "ffmpeg", lambda: "/bin/ffmpeg")
    monkeypatch.setattr(tools, "ffprobe", lambda: "/bin/ffprobe")
    monkeypatch.setattr(tools, "realesrgan", lambda: "/bin/realesrgan")
    monkeypatch.setattr(tools, "models_dir", lambda: "/models")
    assert tools.missing() == []


def test_models_dir_prefers_dir_beside_exe(monkeypatch, tmp_path):
    exe_dir = tmp_path / "bin"
    exe_dir.mkdir()
    exe = exe_dir / "realesrgan-ncnn-vulkan"
    exe.write_text("")
    models = exe_dir / "models"
    models.mkdir()
    (models / "x.param").write_text("")

    monkeypatch.setattr(tools, "realesrgan", lambda: str(exe))
    assert tools.models_dir() == models


def test_models_dir_falls_back_to_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "realesrgan", lambda: None)
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "y.param").write_text("")
    monkeypatch.setattr(tools, "MODELS_CACHE", cache)
    assert tools.models_dir() == cache


def test_models_dir_none_when_nothing_found(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "realesrgan", lambda: None)
    monkeypatch.setattr(tools, "MODELS_CACHE", tmp_path / "does-not-exist")
    assert tools.models_dir() is None


def test_rife_model_finds_dir_beside_exe(monkeypatch, tmp_path):
    exe_dir = tmp_path / "bin"
    exe_dir.mkdir()
    exe = exe_dir / "rife-ncnn-vulkan"
    exe.write_text("")
    (exe_dir / "rife-v4.6").mkdir()

    monkeypatch.setattr(tools, "rife", lambda: str(exe))
    assert tools.rife_model("rife-v4.6") == exe_dir / "rife-v4.6"


def test_rife_model_none_when_unresolved(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "rife", lambda: None)
    monkeypatch.setattr(tools, "RIFE_MODELS_CACHE", tmp_path / "nope")
    assert tools.rife_model() is None
