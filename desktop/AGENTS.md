# Repository Guidelines

## Project Structure & Module Organization

This repository combines a Python video-processing engine with a Tauri desktop app. The top-level Python modules (`upscale_hdr.py`, `recipe.py`, `stages.py`, `grade.py`, and `tools.py`) implement the CLI pipeline; `gui.py` is the legacy Tkinter interface. The Vite/TypeScript frontend lives in `src/`, while Rust commands and Tauri configuration live in `src-tauri/`. Tauri bundles a synchronized copy of the Python engine from `src-tauri/engine/`; update both copies when engine code changes. Treat `legacy/` as reference material. `input/`, `output/`, `dist/`, `.venv/`, and `node_modules/` are generated or local-only content, not source.

## Build, Test, and Development Commands

- `bun install` installs frontend and Tauri dependencies.
- `bun run tauri dev` launches the desktop app with Vite hot reload.
- `bun run build` type-checks TypeScript and builds frontend assets into `dist/`.
- `bun run tauri build` creates a distributable desktop bundle.
- `cargo check --manifest-path src-tauri/Cargo.toml` validates the Rust backend quickly.
- `uv run --python 3.12 --with pillow upscale_hdr.py --dump-config` smoke-tests Python imports and recipe serialization.
- `powershell -ExecutionPolicy Bypass -File .\setup.ps1` provisions external tools such as FFmpeg and Real-ESRGAN on Windows.

## Coding Style & Naming Conventions

Use four spaces and PEP 8 conventions for Python: `snake_case` functions, `PascalCase` classes, and uppercase constants. Preserve type hints and concise docstrings for pipeline behavior. TypeScript uses two spaces, semicolons, `camelCase` identifiers, and `PascalCase` types/classes. Format Rust with `cargo fmt --manifest-path src-tauri/Cargo.toml`; use standard `snake_case` Rust names. Keep recipe/config behavior centralized in Python rather than duplicating pipeline logic in the UI.

## Testing Guidelines

No automated test framework or coverage threshold is configured. Before submitting, run the TypeScript build, `cargo check`, and the Python config smoke test above. For pipeline changes, render a short trimmed clip and verify output video, audio retention, progress events, and cancellation. If adding tests, use `tests/test_<feature>.py` for Python and colocated `*.test.ts` files for frontend behavior.

## Commit & Pull Request Guidelines

History follows Conventional Commit-style subjects such as `feat: ...` and `refactor: ...`; use an imperative, scoped summary and keep each commit focused. Pull requests should explain user-visible behavior, list validation commands, link relevant issues, and include screenshots for UI changes. Call out new binaries, model requirements, or recipe-schema changes explicitly; never commit source videos, rendered output, credentials, or local tool caches.
