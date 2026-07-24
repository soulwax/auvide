"""Recipe = the single source of truth for one auvide job.

Both the GUI and the CLI serialize to/from a Recipe, and Styles are named
one-tap Recipes (à la iPhone Photographic Styles). This is the spine of the
pipeline: today it captures upscale + grade + HDR + encode + trim + audio;
the `frame_ops`, `lut`, and `target` fields are reserved for the stage engine
(RIFE interpolation, LUTs, delivery targets) landing next.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from . import grade
from .grade import Grade as _Grade

# whose own `grade: dict` field shadows the `grade` module name in class scope
# for static type-checkers (harmless at runtime; mypy still trips on it).

GRADE_KNOBS = ("saturation", "vibrance", "contrast", "gamma", "warmth",
               "sharpen", "exposure", "tint")
RECIPE_SCHEMA = "auvide.recipe"
RECIPE_VERSION = 1


class RecipeFormatError(ValueError):
    """A recipe document cannot be safely interpreted by this engine."""


def grade_dict(name: str, **over) -> dict:
    """The 8 grade knobs of a built-in grade preset, with optional overrides."""
    return asdict(replace(grade.PRESETS[name], **over))


@dataclass
class Recipe:
    scale: int = 2
    model: str = "animevideo"           # animevideo | x4plus | x4plus-anime
    hdr: str = "on"                     # on | off
    encoder: str = "x265"              # x265 | qsv
    crf: int = 19
    preset: str = "medium"             # encoder speed
    hdr_gain: float = 1.5
    grade: dict = field(default_factory=lambda: grade_dict("vibrant"))
    trim_start: float = 0.0
    trim_dur: float = 0.0              # 0 = to end
    audio: bool = True
    interpolate: int = 0              # RIFE factor (0=off, 2/3/4)
    slowmo: bool = False              # keep fps (slow-motion) vs smoother
    deinterlace: bool = False         # restore: bwdif
    denoise: str = "off"              # restore: off/light/medium/strong
    stabilize: bool = False           # restore: vidstab
    lut: str = ""                                    # .cube LUT path
    target: str = ""                                 # delivery target preset id
    curve: str = ""                                  # master curve "x/y x/y …" (overrides contrast)

    def to_grade(self) -> _Grade:
        return grade.Grade(**{k: self.grade.get(k, getattr(grade.Grade(), k))
                              for k in GRADE_KNOBS})


# --- Styles: one-tap named looks (the iPhone-style front door) ---------------
STYLES: dict[str, Recipe] = {
    "Vibrant HDR": Recipe(hdr="on", grade=grade_dict("vibrant")),
    "Cinematic":   Recipe(hdr="on", grade=grade_dict("subtle", warmth=-0.70, contrast=0.42,
                                                     gamma=1.04)),
    "Natural":     Recipe(hdr="off", grade=grade_dict("subtle")),
    "Punchy SDR":  Recipe(hdr="off", grade=grade_dict("max")),
    "Sharp Photo": Recipe(model="x4plus", hdr="on", grade=grade_dict("vibrant")),
    "Clean":       Recipe(hdr="off", grade=grade_dict("none")),
    "Smooth 60":   Recipe(hdr="on", grade=grade_dict("vibrant"), interpolate=2),
    "Restore":     Recipe(hdr="on", grade=grade_dict("vibrant", sharpen=0.70), denoise="medium"),
}


# --- Delivery targets: one-tap "export for platform" -------------------------
# Each may force SDR and a fixed output size (crop or pad). {} = keep source.
TARGETS: dict[str, dict] = {
    "source":  {},
    "youtube": {},                                                    # keep as-is (HDR ok)
    "web":     {"hdr": "off", "max_h": 1080},                         # cap 1080p, keep aspect
    "reel":    {"hdr": "off", "w": 1080, "h": 1920, "fit": "crop"},   # 9:16 IG/TikTok
    "tiktok":  {"hdr": "off", "w": 1080, "h": 1920, "fit": "crop"},
    "post":    {"hdr": "off", "w": 1080, "h": 1080, "fit": "crop"},   # 1:1 IG post
    "story":   {"hdr": "off", "w": 1080, "h": 1920, "fit": "pad"},    # 9:16 padded
    "x":       {"hdr": "off", "w": 1920, "h": 1080, "fit": "pad"},    # 16:9
}


def target_hdr(name):
    """HDR override a target forces, or None."""
    return (TARGETS.get(name) or {}).get("hdr")


def target_transform(name, src_w, src_h):
    """Return (ffmpeg scale/crop/pad filter or "", (out_w, out_h)) for a target."""
    t = TARGETS.get(name) or {}
    if "w" in t and "h" in t:
        w, h, fit = t["w"], t["h"], t.get("fit", "crop")
        if fit == "pad":
            f = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                 f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2")
        else:
            f = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
        return f, (w, h)
    if "max_h" in t and src_h > t["max_h"]:
        mh = t["max_h"]
        w = round(src_w * mh / src_h / 2) * 2            # keep width even
        return f"scale={w}:{mh}:flags=lanczos", (w, mh)
    return "", (src_w, src_h)


def to_dict(recipe: Recipe) -> dict:
    """Return the stable payload shared by recipe files and GUI contracts."""
    return asdict(recipe)


def envelope(recipe: Recipe) -> dict:
    """Wrap a recipe in a versioned document suitable for persistence."""
    return {
        "schema": RECIPE_SCHEMA,
        "version": RECIPE_VERSION,
        "recipe": to_dict(recipe),
    }


def schema(model_options: Sequence[str] | None = None) -> dict[str, Any]:
    """Describe editable recipe fields for clients without duplicating defaults.

    This is intentionally descriptive rather than a validation substitute: the
    CLI remains the authority that validates values at render time.
    """
    defaults = to_dict(Recipe())
    fields: list[dict[str, Any]] = [
        {"key": "scale", "label": "Scale", "type": "integer", "section": "Enhance",
         "options": [2, 3, 4]},
        {"key": "model", "label": "AI model", "type": "string", "section": "Enhance",
         "options": list(model_options or [])},
        {"key": "hdr", "label": "HDR output", "type": "enum", "section": "Color",
         "options": ["on", "off"]},
        {"key": "encoder", "label": "Encoder", "type": "enum", "section": "Export",
         "options": ["x265", "qsv"]},
        {"key": "crf", "label": "Quality (CRF)", "type": "integer", "section": "Export",
         "minimum": 0, "maximum": 51},
        {"key": "preset", "label": "Encoder preset", "type": "string", "section": "Export"},
        {"key": "hdr_gain", "label": "HDR gain", "type": "number", "section": "Color",
         "minimum": 0.0},
        {"key": "grade", "label": "Grade", "type": "object", "section": "Color"},
        {"key": "trim_start", "label": "Trim start", "type": "number", "section": "Timeline",
         "minimum": 0.0},
        {"key": "trim_dur", "label": "Trim duration", "type": "number", "section": "Timeline",
         "minimum": 0.0},
        {"key": "audio", "label": "Keep audio", "type": "boolean", "section": "Audio"},
        {"key": "interpolate", "label": "Interpolation", "type": "integer", "section": "Enhance",
         "options": [0, 2, 3, 4]},
        {"key": "slowmo", "label": "Slow motion", "type": "boolean", "section": "Enhance"},
        {"key": "deinterlace", "label": "Deinterlace", "type": "boolean", "section": "Restore"},
        {"key": "denoise", "label": "Denoise", "type": "enum", "section": "Restore",
         "options": ["off", "light", "medium", "strong"]},
        {"key": "stabilize", "label": "Stabilize", "type": "boolean", "section": "Restore"},
        {"key": "lut", "label": "LUT", "type": "string", "section": "Color", "advanced": True},
        {"key": "target", "label": "Delivery target", "type": "string", "section": "Export",
         "options": list(TARGETS)},
        {"key": "curve", "label": "Master curve", "type": "string", "section": "Color", "advanced": True},
    ]
    for item in fields:
        item["default"] = defaults[item["key"]]
    return {
        "schema": "auvide.recipe-schema",
        "version": 1,
        "recipe_schema": RECIPE_SCHEMA,
        "recipe_version": RECIPE_VERSION,
        "fields": fields,
    }


def save(recipe: Recipe, path) -> None:
    from pathlib import Path
    Path(path).write_text(json.dumps(envelope(recipe), indent=2))


def load(path) -> Recipe:
    from pathlib import Path
    document = json.loads(Path(path).read_text())
    if not isinstance(document, dict):
        raise RecipeFormatError("recipe document must be a JSON object")
    if "schema" in document or "version" in document or "recipe" in document:
        if document.get("schema") != RECIPE_SCHEMA:
            raise RecipeFormatError(f"unsupported recipe schema: {document.get('schema')!r}")
        if document.get("version") != RECIPE_VERSION:
            raise RecipeFormatError(f"unsupported recipe version: {document.get('version')!r}")
        document = document.get("recipe")
        if not isinstance(document, dict):
            raise RecipeFormatError("recipe envelope requires an object in 'recipe'")
    # Flat objects are the pre-versioned format and remain supported so old
    # saved recipes and hand-authored GUI files keep working.
    return Recipe(**document)


def apply_to_args(recipe: Recipe, args, given: set) -> None:
    """Overlay a recipe onto argparse `args`, but never clobber flags the user
    passed explicitly (names in `given`)."""
    def setg(attr, flag, value):
        if flag not in given:
            setattr(args, attr, value)
    setg("scale", "--scale", recipe.scale)
    setg("model", "--model", recipe.model)
    setg("hdr", "--hdr", recipe.hdr)
    setg("encoder", "--encoder", recipe.encoder)
    setg("crf", "--crf", recipe.crf)
    setg("preset", "--preset", recipe.preset)
    setg("hdr_gain", "--hdr-gain", recipe.hdr_gain)
    setg("start", "--start", recipe.trim_start)
    if recipe.trim_dur:
        setg("duration", "--duration", recipe.trim_dur)
    if not recipe.audio:
        setg("no_audio", "--no-audio", True)
    setg("interpolate", "--interpolate", recipe.interpolate)
    if recipe.slowmo:
        setg("slowmo", "--slowmo", True)
    if recipe.deinterlace:
        setg("deinterlace", "--deinterlace", True)
    setg("denoise", "--denoise", recipe.denoise)
    if recipe.stabilize:
        setg("stabilize", "--stabilize", True)
    if recipe.lut:
        setg("lut", "--lut", recipe.lut)
    if recipe.target:
        setg("target", "--target", recipe.target)
    if recipe.curve:
        setg("curve", "--curve", recipe.curve)
    # grade knobs (only fill those the user didn't override)
    knob_flag = {"saturation": "--saturation", "vibrance": "--vibrance-amt",
                 "contrast": "--contrast", "gamma": "--gamma", "warmth": "--warmth",
                 "sharpen": "--sharpen", "exposure": "--exposure", "tint": "--tint"}
    arg_attr = {"vibrance": "vibrance_amt"}
    for knob, flag in knob_flag.items():
        if flag not in given and knob in recipe.grade:
            setattr(args, arg_attr.get(knob, knob), recipe.grade[knob])


if __name__ == "__main__":
    for name, r in STYLES.items():
        print(f"{name:14s} scale={r.scale} model={r.model} hdr={r.hdr} "
              f"sat={r.grade['saturation']} warmth={r.grade['warmth']}")
