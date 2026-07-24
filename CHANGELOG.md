# Changelog

All notable changes to auvide are documented in this file.

The project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- `auvide --inspect` and `auvide --inspect-json` expose normalized source
  metadata for desktop and automation clients.
- Saved recipes now use the versioned `auvide.recipe` v1 envelope while
  continuing to load legacy flat JSON recipes. `--dump-config` now includes
  engine-owned `auvide.recipe-schema` metadata for every recipe field.
- A version synchronization check for Python, npm, Cargo, and Tauri metadata.
- Cooperative, resumable render cancellation and versioned NDJSON progress
  events for engine consumers.
- Desktop runtime path and persisted runtime-state foundations.
- Typed Rust parsing for versioned engine progress events, including safe
  handling of additive fields and future event types.
- Typed frontend render state and reducer tests for progress, cancellation,
  unrelated-run isolation, and terminal exit handling.
- Manual, protected PyPI and TestPyPI trusted-publishing workflow with OIDC
  setup documentation.
- A pinned, SHA256-verified `uv` sidecar staging path for supported desktop
  targets.
- Atomic, recoverable desktop runtime state persistence with installed-package
  metadata.
- A one-command modern desktop launcher with development prerequisite checks.
- Desktop engine commands now use the verified bundled `uv` sidecar instead
  of requiring a globally installed `uv` executable.
- The desktop now provisions a serialized, app-data-owned Python 3.12 venv and
  invokes the engine directly from that venv on later requests.
- Strict typed validation for the desktop bootstrap manifest before downloads
  or archive extraction are introduced.
- A reviewed Windows x64 bootstrap manifest with immutable FFmpeg,
  Real-ESRGAN, model, and uv pins.

### Changed

- Desktop product identity is `auvide` with the stable identifier
  `com.soulwax.auvide`.
- Tool discovery now supports managed desktop runtime and model overrides.
- Desktop renders now consume typed NDJSON progress and terminal events instead
  of parsing human log text. Each run stores its recipe and cooperative cancel
  marker under app data; cancellation waits for an engine checkpoint before a
  forced process stop.

## 0.2.0

### Added

- Consolidated Python engine package under `engine/src/auvide/`.
- Tauri desktop frontend and legacy Tkinter compatibility interface.
- Python tests, linting, type checks, and cross-platform CI.
