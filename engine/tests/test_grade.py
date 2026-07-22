"""Tests for auvide.grade: the ffmpeg filter-chain builder.

These assert on the actual filter strings ffmpeg receives — a golden-string
style test. If a knob's mapping to an ffmpeg filter parameter changes, these
tests catch it (intentionally: any change here should be a deliberate,
reviewed diff, since it changes the pixels every user's render produces).
"""
from __future__ import annotations

import pytest

from auvide import grade


def test_default_grade_dataclass_values():
    g = grade.Grade()
    assert g.saturation == 1.16
    assert g.vibrance == 0.28
    assert g.contrast == 0.30
    assert g.gamma == 1.05
    assert g.warmth == -0.55
    assert g.sharpen == 0.50
    assert g.exposure == 0.0
    assert g.tint == 0.0


def test_clamp():
    assert grade.clamp(5, 0, 1) == 1
    assert grade.clamp(-5, 0, 1) == 0
    assert grade.clamp(0.5, 0, 1) == 0.5


class TestBuildChain:
    def test_none_preset_is_near_identity(self):
        chain = grade.build_chain(grade.PRESETS["none"], out_format="yuv420p10le")
        # saturation/gamma always present via `eq=`; no curves/colorbalance/vibrance
        assert "curves=" not in chain
        assert "colorbalance=" not in chain
        assert "vibrance=" not in chain
        assert "eq=saturation=1.000:gamma=1.000:brightness=0.0000" in chain
        assert chain.endswith("format=yuv420p10le")

    def test_working_space_is_first_filter(self):
        chain = grade.build_chain(grade.Grade(), working="gbrpf32le")
        assert chain.split(",")[0] == "format=gbrpf32le"

    def test_out_format_none_omits_trailing_format(self):
        chain = grade.build_chain(grade.Grade(), out_format=None, working="gbrpf32le")
        # only the working-space format at the start, none at the end
        assert chain.count("format=gbrpf32le") == 1
        assert not chain.endswith("format=")

    def test_no_working_space_omits_leading_format(self):
        chain = grade.build_chain(grade.Grade(), working=None, out_format=None)
        assert "format=" not in chain or "gbrpf32le" not in chain.split(",")[0]

    def test_contrast_emits_scurve(self):
        chain = grade.build_chain(grade.Grade(contrast=0.5, warmth=0, tint=0,
                                              vibrance=0, sharpen=0))
        assert "curves=master=0/0 0.25/0.170 0.5/0.5 0.75/0.830 1/1" in chain

    def test_zero_contrast_omits_curves(self):
        chain = grade.build_chain(grade.Grade(contrast=0.0, warmth=0, tint=0,
                                              vibrance=0, sharpen=0))
        assert "curves=" not in chain

    def test_explicit_curve_overrides_contrast_scurve(self):
        custom = "0/0 0.3/0.2 1/1"
        chain = grade.build_chain(grade.Grade(contrast=0.9), curve=custom)
        assert f"curves=master={custom}" in chain
        # only one curves= filter, not both
        assert chain.count("curves=") == 1

    def test_warmth_and_tint_emit_colorbalance(self):
        chain = grade.build_chain(grade.Grade(warmth=1.0, tint=-1.0, contrast=0,
                                              vibrance=0, sharpen=0))
        assert "colorbalance=rm=0.090:gm=0.060:bm=-0.073:rs=0.055:bs=-0.055" in chain

    def test_zero_warmth_and_tint_omit_colorbalance(self):
        chain = grade.build_chain(grade.Grade(warmth=0.0, tint=0.0, contrast=0,
                                              vibrance=0, sharpen=0))
        assert "colorbalance=" not in chain

    def test_vibrance_above_threshold_emits_filter(self):
        chain = grade.build_chain(grade.Grade(vibrance=0.5, contrast=0, warmth=0,
                                              tint=0, sharpen=0))
        assert "vibrance=intensity=0.500" in chain

    def test_sharpen_above_threshold_emits_unsharp(self):
        chain = grade.build_chain(grade.Grade(sharpen=1.0, contrast=0, warmth=0,
                                              tint=0, vibrance=0))
        assert "unsharp=5:5:1.000:3:3:0.200" in chain

    def test_lut_appends_lut3d_filter_with_bare_filename(self):
        chain = grade.build_chain(grade.Grade(), lut="look.cube")
        assert "lut3d=look.cube" in chain
        # lut3d comes before the final format= (caller sets cwd for bare name)
        parts = chain.split(",")
        assert parts.index("lut3d=look.cube") < len(parts) - 1

    def test_eq_values_are_clamped_to_safe_ranges(self):
        wild = grade.Grade(saturation=99, gamma=99, exposure=99, contrast=0,
                           warmth=0, tint=0, vibrance=0, sharpen=0)
        chain = grade.build_chain(wild)
        assert "saturation=3.000" in chain   # clamp(99, 0, 3)
        assert "gamma=3.000" in chain        # clamp(99, 0.1, 3)
        assert "brightness=0.1200" in chain  # clamp(99, -1, 1) * 0.12

    def test_filter_order_is_stable(self):
        g = grade.Grade(contrast=0.3, warmth=0.5, tint=0.1, vibrance=0.3, sharpen=0.5)
        chain = grade.build_chain(g, lut="l.cube")
        names = [p.split("=")[0] for p in chain.split(",")]
        assert names == ["format", "curves", "colorbalance", "eq", "vibrance",
                          "unsharp", "lut3d", "format"]


class TestFromOverrides:
    def test_none_values_keep_base(self):
        base = grade.PRESETS["vibrant"]
        result = grade.from_overrides(base, saturation=None, warmth=None)
        assert result == base

    def test_non_none_values_override(self):
        base = grade.PRESETS["vibrant"]
        result = grade.from_overrides(base, saturation=2.5)
        assert result.saturation == 2.5
        assert result.warmth == base.warmth  # unrelated knob untouched

    def test_returns_new_instance(self):
        base = grade.PRESETS["vibrant"]
        result = grade.from_overrides(base, saturation=2.5)
        assert result is not base
        assert base.saturation != 2.5  # original preset unmodified


@pytest.mark.parametrize("name", list(grade.PRESETS))
def test_every_preset_builds_a_valid_chain(name):
    chain = grade.build_chain(grade.PRESETS[name])
    assert chain  # non-empty
    assert chain.startswith("format=")
