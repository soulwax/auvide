# auvide — Technical Masterplan: from working prototype to a respectable package

Status: Phase 1 done, Phase 2 done · Date: 2026-07-22 · Scope: whole repository (Python engine, Tauri desktop app, legacy Tkinter GUI)

**Progress so far** (see git history from 2026-07-22 onward):
- ✅ **Phase 1** — engine consolidated to `engine/src/auvide/` (one copy, was three); root/desktop
  duplicates of `gui.py` and `README.md` removed; `LICENSE` (MIT) added; standardized on bun
  (removed `pnpm-lock.yaml`/`pnpm-workspace.yaml`); desktop app now stages the engine at
  build time (`desktop/scripts/stage-engine.mjs`) instead of keeping a second tracked copy;
  version drift fixed (0.2.0 everywhere); `AGENTS.md`/`README.md` updated to match.
- ✅ **Phase 2** — pytest suite added (80 tests: unit tests for `recipe`/`grade`/`tools`/`stages`,
  plus a real ffmpeg-based integration test that renders a synthetic clip through the full
  pipeline with a stubbed upscaler and verifies HDR10 output via ffprobe); ruff + mypy clean;
  `cargo fmt`/`clippy -D warnings`/`cargo check` clean; CI workflow added
  (`.github/workflows/ci.yml`, matrix across ubuntu/windows/macos); `main.ts`'s `type Recipe =
  any` replaced with a hand-written `Recipe`/`GradeKnobs` interface mirroring
  `recipe.py`'s `Recipe` dataclass field-for-field, `tsc --noEmit` and `bun run build` both
  clean. Not enforced: `ruff format` (the codebase's existing dense/aligned style predates it
  and a mass reformat wasn't in scope — a deliberate call, revisit if it becomes a pain point).
  The integration test caught and fixed a **real pre-existing bug**: the HDR filter chain's
  `zscale=...t=linear` step failed with "no path between colorspaces" on some ffmpeg/zimg
  builds because the extracted-frame PNG input carried no colorspace tags — fixed by tagging
  the ffmpeg input as BT.709 before the filter graph (`engine/src/auvide/cli.py`,
  `encode_cmd()`).
- ⬜ **Phase 3–5** — not started (PyPI publish, bundled runtime, first-run tool bootstrap,
  release engineering, distribution channels).

## Where we started

The product works: a Python pipeline (`upscale_hdr.py` + `grade.py` / `recipe.py` / `stages.py` / `tools.py`)
orchestrates ffmpeg and realesrgan-ncnn-vulkan, and a Tauri 2 desktop app (`desktop/`) drives it as a
subprocess with live log/progress events. What kept it from being shippable to strangers:

| Gap | Evidence |
|---|---|
| Engine source triplicated | Identical copies at repo root, `desktop/`, and `desktop/src-tauri/engine/` (git hashes match today, will drift) |
| Hard runtime prerequisites | Users must pre-install `uv`, `ffmpeg`, `ffprobe`, `realesrgan-ncnn-vulkan` on PATH before anything runs |
| No LICENSE file | `pyproject.toml` declares MIT, but no `LICENSE` exists — legally the repo is "all rights reserved" |
| No tests, no CI, no releases | No `tests/`, no `.github/`, no tagged versions on GitHub |
| Two package managers | `bun.lock` **and** `pnpm-lock.yaml` both committed; AGENTS.md says bun, latest commit added pnpm |
| Version drift | `pyproject.toml` = 0.2.0; `tauri.conf.json` + `package.json` = 0.1.0 |
| Loose ends | `csp: null`, `type Recipe = any` in `main.ts`, fixed-name temp file `auvide_recipe.json` (collision/race), Python engine is a flat module list, root `bin/` contradicts the PATH-based README |

## Target state

Three deliverables from one codebase, one engine source of truth:

1. **`pip install auvide` / `uv tool install auvide`** — the CLI on PyPI, for power users and scripting.
2. **Signed desktop installers** (Windows NSIS/MSI, macOS DMG, Linux AppImage/deb) on GitHub Releases,
   self-updating, that bootstrap their own runtime dependencies on first run.
3. **A repo people trust at a glance**: LICENSE, tests, CI badges, screenshots, CONTRIBUTING, changelog, tagged releases.

---

## Phase 0 — Decisions (half a day)

Lock these before touching code; everything downstream depends on them.

- **Name**: `auvide` everywhere. Rename product/identifier from `auvide-desktop` → `auvide` (`com.soulwax.auvide`). Do it **before** the first public release — the Tauri identifier is the update channel identity and painful to change later.
- **License**: MIT (already declared). Add the `LICENSE` file immediately.
- **One JS package manager**: pick **pnpm** (the newer commit direction; workspace file already exists) and delete `bun.lock`, or the reverse. Update AGENTS.md to match.
- **Support matrix**, stated in the README: Windows 10+ / macOS 13+ / mainstream Linux; any Vulkan-capable GPU; Python floor stays 3.9 for the pip CLI, bundled runtime is 3.12.
- **The Tkinter GUI (`gui.py`) is legacy**: it moves to `legacy/`, keeps working, gets no new features. The Tauri app is the GUI going forward. Maintaining two GUIs is how both stay mediocre.

## Delivery Discipline - Every Implementation Slice

- Deliver a completed slice as one focused Conventional Commit made with the
  maintainer's configured signed identity. Before committing, verify
  `git config user.name`, `git config user.email`, and signing configuration;
  use `git commit -S` and verify the resulting signature.
- Push that signed commit to `origin` before beginning the next slice. A slice
  is not complete until the push succeeds; report a signing or push failure as
  a blocker rather than silently continuing locally.
- Maintain the canonical root `VERSION` and `CHANGELOG.md` in the same slice
  whenever a user-visible behavior or release version changes. Use
  `python scripts/sync_version.py --set X.Y.Z` for version changes and run
  `python scripts/sync_version.py --check` before committing.
- Inspect the worktree before staging so unrelated user changes are never
  included. Record the commit and pushed ref in the packet handoff.

## Phase 1 — One source of truth + repo hygiene (1–2 days)

**Restructure to a real monorepo.** The engine becomes a proper installable package; both the CLI and the desktop app consume it from one place:

```
auvide/
├─ engine/                     # THE Python package (only copy)
│  ├─ pyproject.toml           # name = "auvide", console scripts
│  ├─ src/auvide/              # __init__.py, cli.py (ex upscale_hdr), grade.py,
│  │                           # recipe.py, stages.py, tools.py
│  └─ tests/
├─ desktop/                    # Tauri app (src/, src-tauri/) — no .py files
├─ legacy/                     # gui.py (Tkinter), vibrant_upscale.py
├─ docs/                       # this file, screenshots, user guide
├─ .github/workflows/          # ci.yml, release.yml
├─ LICENSE  README.md  CONTRIBUTING.md  CHANGELOG.md
```

- Delete the root-level and `desktop/`-level `.py` copies. `desktop/src-tauri/engine/` becomes a **build-time staging dir** (gitignored): a `beforeBuildCommand`/`beforeDevCommand` script copies `engine/src/auvide/` + a launcher into it (or use Tauri 2's `../` resource mapping directly). AGENTS.md's "update both copies" rule dies here.
- Moving to `src/auvide/` package layout means intra-engine imports change from `import grade` to `from auvide import grade` — mechanical, and the moment the triplication ends.
- Purge junk: root `bin/` (contradicts PATH-based setup), stray `__pycache__`/`.egg-info` dirs, duplicate `uv.lock`s, template SVGs in `desktop/src/assets/`. Tighten `.gitignore`.
- Add `LICENSE`, `CONTRIBUTING.md` (absorb AGENTS.md content — AGENTS.md can stay as a pointer), issue/PR templates.

## Phase 2 — Quality gates: tests, lint, CI (2–4 days)

The pipeline's core logic is highly testable because it's mostly *plan construction* (building ffmpeg filter
graphs and command lines), not video math:

- **Python unit tests (pytest)** — no GPU, no models, milliseconds each:
  - `recipe.py`: JSON round-trip, defaults, unknown-key tolerance, style presets resolve.
  - `grade.py`: slider values → exact ffmpeg filter strings (golden strings).
  - `stages.py` / CLI: flags → planned command sequence (`--dry-run` already exists — make its output machine-readable and assert on it).
  - `tools.py`: binary discovery with a mocked PATH; the "print exactly what's missing" report.
- **Python integration test** (CI-viable, no GPU): generate a 2-second clip with `ffmpeg -f lavfi -i testsrc2` + sine audio, run the full pipeline with a **stub upscaler** (a fake `realesrgan-ncnn-vulkan` script that scales frames with ffmpeg), then assert via ffprobe: resolution doubled, `color_transfer=smpte2084`, `color_primaries=bt2020`, `yuv420p10le`, audio stream intact, frame count preserved. This one test protects the entire product promise.
- **Toolchain**: `ruff` (format + lint) and `mypy` for Python; `tsc --strict` + a few vitest tests (the Curves editor math is pure and untested); `cargo fmt --check` + `cargo clippy -- -D warnings` for Rust. Wire into `pre-commit`.
- **`ci.yml`**: matrix {ubuntu, windows, macos} × {lint, test, `cargo check`, `pnpm build`}. ffmpeg from the system package manager per-OS. Badge in README.
- **Type the frontend against the engine**: `--dump-config` already exports the recipe; extend it to emit a **JSON Schema**, generate `desktop/src/recipe.d.ts` from it at build time (`json-schema-to-typescript`), and delete `type Recipe = any`. One source of truth for the schema, enforced by the compiler.

## Phase 3 — Packaging: kill the prerequisites (1–2 weeks, the heart of the plan)

A "respectable package" means: download → install → click → it works. Today four PATH prerequisites stand in the way. Attack in order of pain:

**3a. PyPI track (cheap, do first).** `engine/` publishes as `auvide` with `[project.scripts] auvide = "auvide.cli:main"`. Build with `uv build`, publish via GitHub Actions **trusted publishing** (no long-lived tokens). CLI users still bring ffmpeg/realesrgan — acceptable for that audience, and `tools.py` already reports what's missing. Effort: ~1 day.

**3b. Bundle the Python runtime (desktop).** The app currently shells out to `uv` — an unreasonable ask for GUI users. Two stages:
  1. **Now**: ship `uv` as a Tauri **sidecar** (single ~35 MB static binary, MIT/Apache — redistribution fine). First run: `uv python install 3.12` into app data. Tiny change to `lib.rs` (`uv_cmd` points at the sidecar path instead of PATH).
  2. **Later (better)**: vendor **python-build-standalone** 3.12 directly as a resource (~25 MB) — fully offline, no first-run download, deterministic. The engine is stdlib + Pillow only, so a pinned wheel can be vendored too.
  
  Skip PyInstaller: gluing a frozen engine into Tauri resources is strictly worse than shipping an interpreter, and antivirus heuristics hate PyInstaller onefile binaries.

**3c. Bootstrap ffmpeg + Real-ESRGAN (desktop).** Don't fatten the installer to 300 MB; ship a **first-run setup screen** in the Tauri app:
  - Downloads pinned-URL, **SHA256-verified** builds of ffmpeg (BtbN/gyan.dev per-OS) and realesrgan-ncnn-vulkan (MIT) + the model files into app data (`%LOCALAPPDATA%\auvide` / `~/.local/share/auvide`). This generalizes what `setup.ps1` already does on Windows — port that logic into the app itself (Rust command emitting progress events, same pattern as `run_render`).
  - "Use system binaries instead" toggle for users who already have them (current behavior becomes the fallback, not the requirement).
  - License note: ffmpeg builds with libx265 are GPL — fine to *download at runtime* or even redistribute as a separate aggregated binary next to MIT code, but downloading keeps the installer lean and the licensing trivially clean. Real-ESRGAN code/weights are BSD-3/MIT — no issue.
- **3d. Engine ↔ app protocol.** Replace log-line scraping (`chunk (\d+)/(\d+)` regex in `main.ts`) with a `--progress-json` flag: engine emits NDJSON events (`{"stage": "upscale", "frame": 1204, "total": 5000}`) on a dedicated stream; human logs stay human. The Tkinter GUI and Tauri app both consume it; tests assert on it.

Also in this phase, fix the small robustness sores in `desktop/src-tauri/src/lib.rs`:
- Unique temp recipe path per run (`auvide_recipe.json` fixed name = collision between two windows/instances).
- Set a real **CSP** in `tauri.conf.json` (currently `null`) and keep `capabilities/default.json` minimal.
- Graceful cancel: ask the engine to stop (it's resumable; SIGTERM/CTRL_BREAK first) before `taskkill /F`, so scratch state stays resumable.

## Phase 4 — Release engineering (2–3 days)

- **Single version source.** One `scripts/bump-version` (or release-please with `extra-files`) that stamps `engine/pyproject.toml`, `desktop/package.json`, `desktop/src-tauri/Cargo.toml`, `tauri.conf.json`. Reconcile 0.2.0 vs 0.1.0 now; first public tag `v0.3.0`.
- **`release.yml`**: on tag push — [tauri-action](https://github.com/tauri-apps/tauri-action) builds Windows (NSIS + MSI), macOS (universal DMG), Linux (AppImage + .deb) on native runners and drafts the GitHub Release; a parallel job publishes the PyPI sdist/wheel. `CHANGELOG.md` generated from the Conventional Commits you already write.
- **Auto-update**: `tauri-plugin-updater` + signing keypair (private key in GH Actions secrets), `latest.json` on the Release. Wire this in the **first** public build — the first release is the only one that can't be auto-updated *to*, don't make it the second.
- **Code signing** (reality check, budget-dependent):
  - *Windows*: unsigned = SmartScreen scare wall. Options: Azure Trusted Signing (cheap, eligibility varies for individuals), an OV/EV cert (~€200–400/yr), or ship unsigned initially with a README note — reputation accrues per-file-hash, so signing is strongly recommended before promoting the app anywhere.
  - *macOS*: Apple Developer Program ($99/yr) + notarization, or Gatekeeper blocks the DMG outright. Without it, macOS users need `xattr -d com.apple.quarantine` instructions — decide whether macOS is a launch target or "builds exist, unsupported".
  - *Linux*: nothing needed; AppImage + .deb covers most.

## Phase 5 — Distribution & presentation (ongoing)

- **README split**: user-facing README (what it does, **screenshots/GIF of the desktop app**, install buttons per OS, 3-line quickstart) vs `docs/` for the full flag table and pipeline internals. The current README is excellent developer docs but leads with `setup.ps1` — a stranger should see the payoff first.
- **Package-manager channels**, in ROI order: `winget` manifest (free, PR to winget-pkgs, needs stable installer URL) → `scoop` bucket (trivial, self-hosted) → Homebrew cask (needs some traction) → AUR (`auvide-bin`). PyPI covers `pipx`/`uv tool` users from Phase 3a.
- **Support surface**: GitHub Issues templates (bug report asks for `auvide --doctor` output — add that flag: OS, GPU, tool versions, model presence), Discussions for looks/recipes sharing. A `--doctor` that prints the environment will cut support burden more than any other single feature.
- **Optional later**: a one-page site (GitHub Pages) with before/after sliders — the product is visual, show it.

---

## Sequencing & effort summary

| Phase | Effort | Outcome |
|---|---|---|
| 0 Decisions | 0.5 d | Name, license, one package manager, support matrix |
| 1 Consolidation | 1–2 d | One engine copy, clean tree, LICENSE, CONTRIBUTING |
| 2 Quality gates | 2–4 d | pytest + integration test, ruff/mypy/clippy/strict-TS, CI matrix, typed Recipe |
| 3 Packaging | 1–2 w | PyPI CLI; desktop app with bundled runtime + first-run tool bootstrap; NDJSON progress protocol |
| 4 Release eng. | 2–3 d | Tagged, changelogged, auto-updating, (ideally signed) installers |
| 5 Distribution | ongoing | winget/scoop/brew/AUR, README with screenshots, `--doctor` |

Phases 1–2 are pure prerequisites and safe to start immediately. Phase 3 is the real product work. 4–5 are mechanical once 3 lands.

## Risk register

- **SmartScreen/Gatekeeper** will scare off exactly the non-technical users the desktop app targets — signing budget is a product decision, not a nice-to-have.
- **GPU variance**: realesrgan-ncnn-vulkan behaves differently across drivers (VRAM OOM → `--tile` exists, good). `--doctor` + a first-run 10-frame self-test render would catch most of it before a 2-hour job fails.
- **Model/tool downloads**: pinned URLs rot. Mirror the model files (and ideally tool archives) as assets on your own GitHub Releases so first-run setup never depends on third-party hosting.
- **OneDrive paths** (already bitten once, per the `uv_cmd` comment): keep all scratch/app data in `%LOCALAPPDATA%`/`XDG` dirs, never under the install or sync dirs; add a test that the default `--work` dir is outside the repo.
- **ffmpeg licensing**: keep the GPL ffmpeg binary a *downloaded, separate* artifact and the repo stays cleanly MIT.
