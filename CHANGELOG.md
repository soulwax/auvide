# Changelog

All notable changes to auvide are documented in this file.

The project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

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

### Changed

- Desktop product identity is `auvide` with the stable identifier
  `com.soulwax.auvide`.
- Tool discovery now supports managed desktop runtime and model overrides.

## 0.2.0

### Added

- Consolidated Python engine package under `engine/src/auvide/`.
- Tauri desktop frontend and legacy Tkinter compatibility interface.
- Python tests, linting, type checks, and cross-platform CI.
