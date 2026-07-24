# Contributing to auvide

Thanks for helping improve auvide. The project has one Python engine source at
`engine/src/auvide/`; the desktop app stages that package for Tauri builds.
Do not edit `desktop/src-tauri/engine/`, because it is generated.

## Development setup

Install the engine development dependencies from `engine/`:

```powershell
pip install -e .[dev]
pytest
ruff check .
mypy src
```

Install desktop dependencies from `desktop/`:

```powershell
bun install
bun run stage-engine
bun run build
cargo fmt --manifest-path src-tauri/Cargo.toml -- --check
cargo check --manifest-path src-tauri/Cargo.toml
cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets -- -D warnings
```

The FFmpeg-backed integration test needs `ffmpeg` and `ffprobe` on PATH. The
real upscaler is replaced with a test fixture, so a GPU is not required.

## Changes and pull requests

- Keep engine behavior in the Python package rather than duplicating it in a UI.
- Add focused tests for behavior changes. Render a short clip for pipeline work.
- Keep commits narrow and use Conventional Commit-style subjects such as
  `feat: add doctor report` or `fix: preserve audio on resume`.
- Do not commit media, output, downloaded runtimes, tool archives, model files,
  credentials, or generated `desktop/src-tauri/engine/` files.
- Explain user-visible behavior and validation commands in the pull request.
- Include a screenshot for desktop UI changes.

## Reporting problems

Use the bug-report form and include the OS, GPU, input characteristics, and
`auvide --doctor` output once that command is available. Never include private
media or credentials in a public issue.
