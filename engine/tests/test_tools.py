"""Tests for auvide.tools: PATH-based binary/model discovery.

No real ffmpeg/realesrgan install is required — shutil.which and the
filesystem are mocked/monkeypatched.
"""
from __future__ import annotations

from auvide import tools


def _clear_overrides(monkeypatch):
    for name in (
        tools.ENV_FFMPEG, tools.ENV_FFPROBE, tools.ENV_REALESRGAN,
        tools.ENV_REALESRGAN_MODELS, tools.ENV_RIFE, tools.ENV_RIFE_MODELS,
    ):
        monkeypatch.delenv(name, raising=False)


def test_which_returns_first_match(monkeypatch):
    _clear_overrides(monkeypatch)
    calls = []

    def fake_which(name):
        calls.append(name)
        return "/usr/bin/found" if name == "second" else None

    monkeypatch.setattr(tools.shutil, "which", fake_which)
    assert tools._which("first", "second", "third") == "/usr/bin/found"
    assert calls == ["first", "second"]  # stops at the first hit


def test_which_returns_none_when_nothing_found(monkeypatch):
    _clear_overrides(monkeypatch)
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)
    assert tools._which("a", "b") is None


def test_ffmpeg_ffprobe_delegate_to_which(monkeypatch):
    _clear_overrides(monkeypatch)
    monkeypatch.setattr(tools, "_which", lambda *names: f"/bin/{names[0]}")
    assert tools.ffmpeg() == "/bin/ffmpeg"
    assert tools.ffprobe() == "/bin/ffprobe"


def test_realesrgan_tries_both_names(monkeypatch):
    _clear_overrides(monkeypatch)
    seen = {}
    monkeypatch.setattr(tools, "_which", lambda *names: seen.setdefault("names", names) and None)
    tools.realesrgan()
    assert seen["names"] == ("realesrgan-ncnn-vulkan", "realesrgan")


def test_missing_reports_each_unresolved_prerequisite(monkeypatch):
    _clear_overrides(monkeypatch)
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
    _clear_overrides(monkeypatch)
    monkeypatch.setattr(tools, "ffmpeg", lambda: "/bin/ffmpeg")
    monkeypatch.setattr(tools, "ffprobe", lambda: "/bin/ffprobe")
    monkeypatch.setattr(tools, "realesrgan", lambda: "/bin/realesrgan")
    monkeypatch.setattr(tools, "models_dir", lambda: "/models")
    assert tools.missing() == []


def test_models_dir_prefers_dir_beside_exe(monkeypatch, tmp_path):
    _clear_overrides(monkeypatch)
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
    _clear_overrides(monkeypatch)
    monkeypatch.setattr(tools, "realesrgan", lambda: None)
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "y.param").write_text("")
    monkeypatch.setattr(tools, "MODELS_CACHE", cache)
    assert tools.models_dir() == cache


def test_models_dir_none_when_nothing_found(monkeypatch, tmp_path):
    _clear_overrides(monkeypatch)
    monkeypatch.setattr(tools, "realesrgan", lambda: None)
    monkeypatch.setattr(tools, "MODELS_CACHE", tmp_path / "does-not-exist")
    assert tools.models_dir() is None


def test_rife_model_finds_dir_beside_exe(monkeypatch, tmp_path):
    _clear_overrides(monkeypatch)
    exe_dir = tmp_path / "bin"
    exe_dir.mkdir()
    exe = exe_dir / "rife-ncnn-vulkan"
    exe.write_text("")
    (exe_dir / "rife-v4.6").mkdir()

    monkeypatch.setattr(tools, "rife", lambda: str(exe))
    assert tools.rife_model("rife-v4.6") == exe_dir / "rife-v4.6"


def test_rife_model_none_when_unresolved(monkeypatch, tmp_path):
    _clear_overrides(monkeypatch)


def test_explicit_binary_override_wins_over_path(monkeypatch, tmp_path):
    _clear_overrides(monkeypatch)
    tool_dir = tmp_path / "managed tools"
    tool_dir.mkdir()
    binary = tool_dir / "ffmpeg.exe"
    binary.write_text("")

    monkeypatch.setenv(tools.ENV_FFMPEG, str(binary))
    monkeypatch.setattr(tools, "_which", lambda *names: "/system/ffmpeg")

    assert tools.ffmpeg() == str(binary)
    assert tools.override_error(tools.ENV_FFMPEG) is None


def test_invalid_binary_override_never_falls_back_to_path(monkeypatch, tmp_path):
    _clear_overrides(monkeypatch)
    missing = tmp_path / "not-installed" / "ffmpeg"
    monkeypatch.setenv(tools.ENV_FFMPEG, str(missing))
    monkeypatch.setattr(tools, "_which", lambda *names: "/system/ffmpeg")

    assert tools.ffmpeg() is None
    assert "AUVIDE_FFMPEG" in tools.override_error(tools.ENV_FFMPEG)
    assert any("AUVIDE_FFMPEG" in item for item in tools.missing())


def test_relative_override_is_actionable(monkeypatch):
    _clear_overrides(monkeypatch)
    monkeypatch.setenv(tools.ENV_FFPROBE, "tools/ffprobe")

    assert tools.ffprobe() is None
    assert "absolute path" in tools.override_error(tools.ENV_FFPROBE)


def test_model_directory_override_requires_model_files(monkeypatch, tmp_path):
    _clear_overrides(monkeypatch)
    models = tmp_path / "models"
    models.mkdir()
    monkeypatch.setenv(tools.ENV_REALESRGAN_MODELS, str(models))

    assert tools.models_dir() is None
    assert "no .param" in tools.override_error(tools.ENV_REALESRGAN_MODELS)

    (models / "realesr-animevideov3.param").write_text("")
    assert tools.models_dir() == str(models)
    assert tools.override_error(tools.ENV_REALESRGAN_MODELS) is None
    monkeypatch.setattr(tools, "rife", lambda: None)
    monkeypatch.setattr(tools, "RIFE_MODELS_CACHE", tmp_path / "nope")
    assert tools.rife_model() is None
