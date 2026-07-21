# auvide desktop (Tauri) — work in progress

A native desktop front-end for auvide. The Python CLI (`upscale_hdr.py`) stays
the engine; this app builds a **recipe** and streams the render — nothing in the
pipeline is reimplemented.

## Status
Foundation written, **not yet built** (was blocked on local disk). In place:
- **Rust backend** (`src-tauri/src/lib.rs`): `config` (reads the engine's
  `--dump-config`), `run_render` (spawns the engine, streams stdout/stderr as
  `render:log` events + `render:done` on exit), `cancel_render`.
- **Frontend** (`src/main.ts`): style chips from the engine config, options,
  8 grade sliders, an interactive **curves editor**, run/progress/log.

## Prerequisites
- Rust, bun (or npm), WebView2 (Windows).
- The auvide engine prereqs on PATH — ffmpeg, realesrgan-ncnn-vulkan,
  rife-ncnn-vulkan, and `uv` (run `../setup.ps1`).
- **~5 GB free local disk** for the first build (Rust `target/` + `node_modules`).

## Build & run
```bash
cd desktop
bun install
bun run tauri dev      # dev window with hot reload
bun run tauri build    # bundle a standalone app
```
The Python engine is bundled in `src-tauri/engine/` and invoked via
`uv run --no-project --python 3.12 upscale_hdr.py --recipe <tmp.json>`.

## TODO (next build session)
- Live grade + scope preview panel (the Tkinter GUI's headline feature).
- Full option parity (trim, batch, LUT picker, restore/stabilize, notify/sleep).
- Recipe Save/Load, accent themes, delivery-target preview.
