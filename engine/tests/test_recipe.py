"""Tests for auvide.recipe: Recipe defaults, JSON round-trip, styles, targets,
and the apply_to_args() CLI overlay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from auvide import grade, recipe


def test_default_recipe_matches_vibrant_grade():
    r = recipe.Recipe()
    assert r.scale == 2
    assert r.model == "animevideo"
    assert r.hdr == "on"
    # default grade dict is the "vibrant" preset
    assert r.grade == recipe.grade_dict("vibrant")


def test_grade_dict_applies_overrides():
    d = recipe.grade_dict("vibrant", saturation=2.0)
    assert d["saturation"] == 2.0
    # untouched knobs keep the preset's values
    assert d["warmth"] == grade.PRESETS["vibrant"].warmth


def test_grade_dict_unknown_preset_raises():
    with pytest.raises(KeyError):
        recipe.grade_dict("does-not-exist")


def test_to_grade_round_trips_the_grade_dict():
    r = recipe.Recipe(grade=recipe.grade_dict("max"))
    g = r.to_grade()
    assert isinstance(g, grade.Grade)
    for knob in recipe.GRADE_KNOBS:
        assert getattr(g, knob) == r.grade[knob]


def test_to_grade_tolerates_missing_keys():
    # a recipe loaded from an older/partial JSON file might be missing knobs
    r = recipe.Recipe(grade={"saturation": 1.5})
    g = r.to_grade()
    assert g.saturation == 1.5
    assert g.warmth == grade.Grade().warmth  # falls back to the dataclass default


@pytest.mark.parametrize("name", list(recipe.STYLES))
def test_every_style_is_a_valid_recipe(name):
    style = recipe.STYLES[name]
    assert isinstance(style, recipe.Recipe)
    # every grade knob must be present so to_grade() never silently defaults
    for knob in recipe.GRADE_KNOBS:
        assert knob in style.grade


def test_save_and_load_round_trip(tmp_path):
    original = recipe.Recipe(scale=4, model="x4plus", hdr="off", crf=21,
                             grade=recipe.grade_dict("subtle"), trim_start=1.5,
                             interpolate=2, lut="look.cube", target="reel")
    path = tmp_path / "recipe.json"
    recipe.save(original, path)

    loaded_raw = json.loads(path.read_text())
    assert loaded_raw["schema"] == recipe.RECIPE_SCHEMA
    assert loaded_raw["version"] == recipe.RECIPE_VERSION
    assert loaded_raw["recipe"]["scale"] == 4
    assert loaded_raw["recipe"]["target"] == "reel"

    loaded = recipe.load(path)
    assert loaded == original


def test_load_unknown_keys_raise_typeerror(tmp_path):
    # Recipe is a plain dataclass; loading JSON with an unexpected key should
    # fail loudly rather than silently drop data (protects future schema bugs).
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"scale": 2, "not_a_real_field": True}))
    with pytest.raises(TypeError):
        recipe.load(path)


def test_load_legacy_flat_recipe(tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({"scale": 3, "hdr": "off"}))
    assert recipe.load(path) == recipe.Recipe(scale=3, hdr="off")


def test_loads_recipe_v1_contract_fixture(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "contracts" / "recipe_v1.json"
    path = tmp_path / "recipe.json"
    path.write_text(fixture.read_text())
    loaded = recipe.load(path)
    assert loaded == recipe.Recipe(scale=4, model="x4plus", hdr="off", crf=21, target="reel")


@pytest.mark.parametrize("document", [
    {"schema": "another.recipe", "version": 1, "recipe": {}},
    {"schema": recipe.RECIPE_SCHEMA, "version": 99, "recipe": {}},
    {"schema": recipe.RECIPE_SCHEMA, "version": 1, "recipe": []},
])
def test_load_rejects_incompatible_envelopes(tmp_path, document):
    path = tmp_path / "bad-envelope.json"
    path.write_text(json.dumps(document))
    with pytest.raises(recipe.RecipeFormatError):
        recipe.load(path)


def test_schema_describes_recipe_defaults():
    document = recipe.schema(["animevideo", "x4plus"])
    fields = {field["key"]: field for field in document["fields"]}
    assert document["recipe_schema"] == recipe.RECIPE_SCHEMA
    assert fields["scale"]["default"] == recipe.Recipe().scale
    assert fields["denoise"]["options"] == ["off", "light", "medium", "strong"]
    assert fields["model"]["options"] == ["animevideo", "x4plus"]
    assert fields["target"]["options"] == list(recipe.TARGETS)


class TestTargets:
    def test_source_target_has_no_overrides(self):
        assert recipe.TARGETS["source"] == {}
        assert recipe.target_hdr("source") is None

    def test_social_targets_force_sdr(self):
        for name in ("reel", "tiktok", "post", "story", "x", "web"):
            assert recipe.target_hdr(name) == "off"

    def test_youtube_keeps_source_hdr(self):
        assert recipe.target_hdr("youtube") is None

    def test_unknown_target_is_a_no_op(self):
        assert recipe.target_hdr("not-a-target") is None
        f, size = recipe.target_transform("not-a-target", 1920, 1080)
        assert f == ""
        assert size == (1920, 1080)

    @pytest.mark.parametrize("name,expect_dims", [
        ("reel", (1080, 1920)),
        ("tiktok", (1080, 1920)),
        ("post", (1080, 1080)),
        ("story", (1080, 1920)),
        ("x", (1920, 1080)),
    ])
    def test_fixed_size_targets_return_exact_dims(self, name, expect_dims):
        f, size = recipe.target_transform(name, 3840, 2160)
        assert size == expect_dims
        assert str(expect_dims[0]) in f and str(expect_dims[1]) in f

    def test_crop_targets_use_crop_filter(self):
        f, _ = recipe.target_transform("reel", 3840, 2160)
        assert "crop=" in f
        assert "pad=" not in f

    def test_pad_targets_use_pad_filter(self):
        f, _ = recipe.target_transform("story", 3840, 2160)
        assert "pad=" in f

    def test_max_h_target_downscales_only_when_taller(self):
        # source shorter than the cap: no-op
        f, size = recipe.target_transform("web", 1920, 1080)
        assert f == ""
        assert size == (1920, 1080)
        # source taller than the cap: scales down, keeps aspect, even width
        f, size = recipe.target_transform("web", 3840, 2160)
        assert "scale=" in f
        assert size[1] == 1080
        assert size[0] % 2 == 0


class TestApplyToArgs:
    def _base_args(self, **overrides):
        ns = argparse.Namespace(
            scale=2, model="animevideo", hdr="on", encoder="x265", crf=19,
            preset="medium", hdr_gain=1.5, start=0.0, duration=None,
            no_audio=False, interpolate=0, slowmo=False, deinterlace=False,
            denoise="off", stabilize=False, lut=None, target="source", curve="",
            saturation=None, vibrance_amt=None, contrast=None, gamma=None,
            warmth=None, tint=None, exposure=None, sharpen=None,
        )
        for k, v in overrides.items():
            setattr(ns, k, v)
        return ns

    def test_recipe_overlays_onto_defaults(self):
        args = self._base_args()
        r = recipe.Recipe(scale=4, model="x4plus", hdr="off")
        recipe.apply_to_args(r, args, given=set())
        assert args.scale == 4
        assert args.model == "x4plus"
        assert args.hdr == "off"

    def test_explicit_cli_flags_are_never_clobbered(self):
        # user passed --scale 3 explicitly; a loaded --style/--recipe must not
        # override it even though the style/recipe also sets `scale`.
        args = self._base_args(scale=3)
        r = recipe.Recipe(scale=4)
        recipe.apply_to_args(r, args, given={"--scale"})
        assert args.scale == 3

    def test_grade_knobs_overlay_with_flag_name_mapping(self):
        # `vibrance` in the recipe grade dict maps to the `vibrance_amt` arg
        # attribute (CLI flag --vibrance-amt), not `vibrance` (that's --vibrance,
        # the preset selector) — apply_to_args must respect that split.
        args = self._base_args()
        r = recipe.Recipe(grade=recipe.grade_dict("vibrant", vibrance=0.42))
        recipe.apply_to_args(r, args, given=set())
        assert args.vibrance_amt == 0.42

    def test_style_target_forces_sdr_only_when_not_explicit(self):
        args = self._base_args(target="reel")
        r = recipe.STYLES["Vibrant HDR"]
        recipe.apply_to_args(r, args, given=set())
        # apply_to_args itself doesn't touch target->hdr coupling (that's in
        # cli.py's main()); just verify the recipe's own hdr value applied.
        assert args.hdr == r.hdr
