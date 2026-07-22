"""Tests for auvide.stages: frame-op stage planning (no subprocess execution)."""
from __future__ import annotations

import argparse

import pytest

from auvide import stages


def _args(**overrides):
    ns = argparse.Namespace(model="animevideo", scale=2, gpu=0, tile=0, interpolate=0)
    for k, v in overrides.items():
        setattr(ns, k, v)
    return ns


class TestBuildFrameStages:
    def test_native_scale_model_uses_requested_scale(self):
        planned = stages.build_frame_stages(_args(model="animevideo", scale=2))
        assert len(planned) == 1
        assert isinstance(planned[0], stages.UpscaleStage)
        assert planned[0].scale == 2

    def test_fixed_4x_model_overscales_when_a_smaller_factor_is_requested(self):
        # x4plus is a native-4x-only model; asking for 2x still runs realesrgan
        # at 4x (cli.py rescales down afterward with a lanczos filter).
        planned = stages.build_frame_stages(_args(model="x4plus", scale=2))
        assert planned[0].scale == 4

    def test_fixed_4x_model_at_4x_does_not_overscale(self):
        planned = stages.build_frame_stages(_args(model="x4plus", scale=4))
        assert planned[0].scale == 4

    def test_no_interpolate_by_default(self):
        planned = stages.build_frame_stages(_args(interpolate=0))
        assert len(planned) == 1

    def test_interpolate_appends_stage(self):
        planned = stages.build_frame_stages(_args(interpolate=2))
        assert len(planned) == 2
        assert isinstance(planned[1], stages.InterpolateStage)
        assert planned[1].factor == 2

    def test_interpolate_one_is_a_no_op(self):
        # factor 1 means "no change" — must not append a stage
        planned = stages.build_frame_stages(_args(interpolate=1))
        assert len(planned) == 1

    def test_missing_interpolate_attr_is_tolerated(self):
        ns = argparse.Namespace(model="animevideo", scale=2, gpu=0, tile=0)
        planned = stages.build_frame_stages(ns)
        assert len(planned) == 1


class TestTotalFrameMultiplier:
    def test_upscale_only_multiplier_is_one(self):
        planned = stages.build_frame_stages(_args())
        assert stages.total_frame_multiplier(planned) == 1

    def test_interpolate_multiplies_frame_count(self):
        planned = stages.build_frame_stages(_args(interpolate=3))
        assert stages.total_frame_multiplier(planned) == 3

    def test_empty_stage_list_multiplier_is_one(self):
        assert stages.total_frame_multiplier([]) == 1


class TestStageErrorWiring:
    def test_upscale_stage_raises_when_tools_unresolved(self, monkeypatch):
        monkeypatch.setattr(stages.tools, "realesrgan", lambda: None)
        monkeypatch.setattr(stages.tools, "models_dir", lambda: None)
        stage = stages.UpscaleStage("realesr-animevideov3", 2)
        with pytest.raises(stages.StageError):
            stage.process("in", "out")

    def test_interpolate_stage_raises_when_tools_unresolved(self, monkeypatch):
        monkeypatch.setattr(stages.tools, "rife", lambda: None)
        monkeypatch.setattr(stages.tools, "rife_model", lambda name="rife-v4.6": None)
        stage = stages.InterpolateStage(2)
        with pytest.raises(stages.StageError):
            stage.process("in", "out")
