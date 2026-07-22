# Repository Guidelines

## Project Structure & Module Organization

This repository combines a Python video-processing engine with a Tauri desktop app.
The engine is a single installable package at `../engine/src/auvide/` (modules:
`cli.py`, `recipe.py`, `stages.py`, `grade.py`, `tools.py`) — it is the **only**
copy of the engine source; do not duplicate it. `legacy/gui.py` is the legacy
Tkinter interface, kept for reference, and imports the engine as `from auvide
import ...` (installed via `pip install -e ../engine` or `uv run --with
../engine`). The Vite/TypeScript frontend lives in `src/`, while Rust commands
and Tauri configuration live in `src-tauri/`. Tauri does **not** keep its own
engine copy: `scripts/stage-engine.mjs` copies `../engine` into the gitignored
`src-tauri/engine/` before every dev run and build (wired into
`beforeDevCommand`/`beforeBuildCommand` in `tauri.conf.json`) — edit the engine
only under `../engine/src/auvide/`, never under `src-tauri/engine/`.
`input/`, `output/`, `dist/`, `.venv/`, and `node_modules/` are generated or
local-only content, not source.

## Build, Test, and Development Commands

- `bun install` installs frontend and Tauri dependencies.
- `bun run stage-engine` copies `../engine` into `src-tauri/engine/` (runs
  automatically before `dev`/`tauri build`; run it manually after editing the
  engine if you're only doing `cargo check`).
- `bun run tauri dev` launches the desktop app with Vite hot reload.
- `bun run build` type-checks TypeScript and builds frontend assets into `dist/`.
- `bun run tauri build` creates a distributable desktop bundle.
- `cargo check --manifest-path src-tauri/Cargo.toml` validates the Rust backend quickly.
- `pip install -e ../engine[dev]` (or `uv sync` from `../engine`) sets up the
  Python engine for development.
- `pytest` (run from `../engine`) runs the Python test suite.
- `ruff check .` / `ruff format --check .` (from `../engine`) lints and checks
  formatting; `mypy src` type-checks.
- `uv run --project ../engine --python 3.12 -m auvide.cli --dump-config`
  smoke-tests Python imports and recipe serialization without a full install.
- `powershell -ExecutionPolicy Bypass -File .\setup.ps1` provisions external
  tools such as FFmpeg and Real-ESRGAN on Windows.

## Coding Style & Naming Conventions

Use four spaces and PEP 8 conventions for Python: `snake_case` functions,
`PascalCase` classes, and uppercase constants. Preserve type hints and concise
docstrings for pipeline behavior. Engine modules import each other with
relative imports (`from . import grade`), never bare (`import grade`) — bare
imports only work by accident when a script's directory is on `sys.path` and
will break the installed package. TypeScript uses two spaces, semicolons,
`camelCase` identifiers, and `PascalCase` types/classes. Format Rust with
`cargo fmt --manifest-path src-tauri/Cargo.toml`; use standard `snake_case`
Rust names. Keep recipe/config behavior centralized in the Python engine
rather than duplicating pipeline logic in the UI.

## Testing Guidelines

Python: pytest, run from `../engine` (`pytest`, or `pytest --cov=auvide` for
coverage). Unit tests cover `recipe.py`/`grade.py`/`tools.py`/`stages.py`
plan-construction logic without needing a GPU; an integration test renders a
synthetic `ffmpeg testsrc2` clip through the full pipeline with a stubbed
upscaler and asserts HDR10 metadata via ffprobe. Use `tests/test_<feature>.py`
naming. Frontend/Rust: no automated tests yet — before submitting, run the
TypeScript build and `cargo check`. For pipeline changes, also render a short
trimmed clip and verify output video, audio retention, progress events, and
cancellation.

## Commit & Pull Request Guidelines

History follows Conventional Commit-style subjects such as `feat: ...` and
`refactor: ...`; use an imperative, scoped summary and keep each commit
focused. Pull requests should explain user-visible behavior, list validation
commands, link relevant issues, and include screenshots for UI changes. Call
out new binaries, model requirements, or recipe-schema changes explicitly;
never commit source videos, rendered output, credentials, or local tool caches.
