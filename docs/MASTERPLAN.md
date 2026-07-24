# auvide Product and Technical Masterplan

Status: foundations complete; runtime/bootstrap, desktop integration, product
UX, and release work in progress

Reconciled: 2026-07-24

Scope: Python engine and CLI, Tauri desktop application, packaging, release,
distribution, and user experience

## 1. Document Hierarchy

This is the canonical portfolio plan. It owns product outcomes, architectural
boundaries, workstream order, and release gates.

- [`../GUI_MASTERPLAN.md`](../GUI_MASTERPLAN.md) owns the detailed desktop and
  CLI user experience.
- [`MASTERPLAN_IMPLEMENTATION.md`](MASTERPLAN_IMPLEMENTATION.md) owns packet
  IDs, dependencies, file ownership, tests, acceptance criteria, and agent
  handoffs.
- `CHANGELOG.md` records behavior already delivered; a plan is not evidence
  that a feature exists.
- The closest `AGENTS.md` owns repository-specific working rules.

When these documents disagree, use this order:

1. Current source and tests describe present behavior.
2. This masterplan decides scope and release order.
3. The GUI masterplan supplies detailed experience requirements.
4. The implementation guide supplies execution mechanics.

The legacy Tkinter GUI remains a compatibility/reference surface. All new
product work targets the Tauri application.

## 2. Product Vision

auvide should be useful at three levels without maintaining three processing
implementations:

1. **Approachable desktop workstation** — import media, inspect it, compare
   real previews, choose a look, understand cost and compatibility, queue work,
   resume interruptions, and find results later.
2. **Reproducible CLI** — inspect, plan, preview, render, batch, diagnose, and
   automate through stable text and JSON contracts.
3. **Reusable engine package** — one installable Python source of truth for
   recipes, validation, FFmpeg plans, stages, capabilities, and progress.

The product promise remains deliberately narrow:

> Improve, restore, upscale, grade, and deliver complete video clips with
> confidence.

auvide is not a nonlinear editor. Multi-track timelines, transitions, titles,
audio mixing, and general compositing are outside the current roadmap.

## 3. Target Deliverables

One repository must produce:

1. `pip install auvide` / `uv tool install auvide` for power users.
2. Signed, self-updating desktop installers for supported platforms.
3. A desktop app requiring no manually installed Python, `uv`, FFmpeg, or
   Real-ESRGAN on its normal path.
4. Stable versioned recipe, inspection, planning, progress, preview, batch, and
   diagnostic contracts.
5. A durable local job model for queue, cancellation, resume, logs, and
   history.
6. Documentation and release material that accurately show limitations,
   dependencies, signing status, and HDR behavior.

## 4. Current Baseline

### 4.1 Complete foundations

- The canonical engine is `engine/src/auvide/`; tracked duplicates were
  removed.
- The desktop build stages that source instead of maintaining another engine
  copy.
- Product identity is `auvide` and the Tauri identifier is
  `com.soulwax.auvide`.
- MIT license, changelog, contribution guide, issue templates, and CI exist.
- Python unit tests and an FFmpeg-backed integration render exist.
- Python lint/type checks, TypeScript build/tests, and Rust checks are present.
- Root `VERSION` and version synchronization checks exist.
- Engine tool overrides support desktop-managed binaries.
- Versioned NDJSON engine progress and cooperative engine cancellation exist.
- Rust has a typed progress parser.
- TypeScript has a tested render-state reducer.
- A verified `uv` sidecar, managed Python 3.12 runtime, and recoverable runtime
  state exist.
- Bootstrap manifest parsing and a reviewed Windows x64 artifact manifest
  exist.
- Protected manual PyPI/TestPyPI trusted-publishing workflow exists.

### 4.2 In-progress integration

- The visible desktop render flow still scrapes human log text instead of
  consuming the typed progress path end to end.
- Rust process state remains PID-centered rather than a durable job
  supervisor.
- Bootstrap downloading, safe extraction, component installation, health
  checks, and setup UI are not complete.
- Cancellation is cooperative in the engine, but the desktop still needs the
  per-job cancel marker, grace period, and resumable terminal UX.

### 4.3 Product experience gaps

- The Tauri GUI exposes only part of `Recipe`.
- Source inspection, real preview, preflight, estimates, queue, restart
  recovery, history, custom presets, and result actions are not present.
- CLI rendering is capable, but source inspection, resolved plan, capabilities,
  first-class preview, arbitrary batch manifests, and versioned recipe schema
  are not yet complete client contracts.
- Release workflow, updater, platform signing, and clean-machine installers
  remain unfinished.

This ledger must be updated when packets land. Historical accomplishments
belong in `CHANGELOG.md`; do not leave completed work described as pending.

## 5. Architecture

### 5.1 Responsibility boundary

```text
TypeScript desktop UI
  interaction, forms, visual state, preview presentation, queue/history views
            |
            | typed Tauri commands and events
            v
Rust application service
  process supervision, durable jobs, app paths, bootstrap, filesystem and OS
            |
            | versioned recipe + CLI JSON/NDJSON
            v
Python engine
  defaults, schema, validation, inspect, plan, preview, render, capabilities
            |
            v
FFmpeg / FFprobe / Real-ESRGAN / optional RIFE
```

Rules:

- Python owns processing truth and effective plans.
- Rust owns trusted operating-system access and process lifetime.
- TypeScript owns presentation; it must not reconstruct FFmpeg/model rules.
- Human logs are diagnostics, never an application state protocol.
- App resources are read-only. Runtime, tools, jobs, logs, downloads, models,
  and scratch data live in platform app-data/cache/temp directories.

### 5.2 Shared domain objects

The following contracts are versioned and engine-owned:

| Contract | Purpose | Primary consumers |
|---|---|---|
| `auvide.recipe` | Portable user intent | CLI, desktop, saved presets |
| `auvide.recipe-schema` | Fields, types, defaults, constraints, UI hints | desktop, docs, validators |
| `auvide.media` | Normalized source inspection | desktop import, scripts |
| `auvide.plan` | Resolved stages, output, warnings, estimates | preflight, dry-run |
| `auvide.progress` | Runtime state and artifacts | Rust bridge, automation |
| `auvide.capabilities` | Tools, devices, models, encoders, storage | setup, doctor, preflight |
| `auvide.batch` | Shared and per-item jobs | CLI batch, desktop queue import |

Backward compatibility:

- Existing `auvide INPUT [flags]` remains a render alias.
- Existing unwrapped recipe JSON remains readable.
- Additive fields are tolerated where safe.
- Schema-version incompatibility fails with a stable code and recovery message.

### 5.3 Durable job unit

Each accepted desktop job owns:

```text
app_data/jobs/<job-id>/
  job.json
  effective-plan.json
  state.json
  events.ndjson
  render.log
  cancel.requested
```

`job.json` is the immutable submission. State updates are atomic. On restart,
orphaned running jobs become interrupted; the app never silently restarts an
expensive render.

### 5.4 Data and privacy

- Media and previews remain local.
- No telemetry exists unless separately designed with explicit consent.
- Support bundles redact paths and secrets and require user review.
- Bootstrap artifacts are pinned, checksum-verified, safely extracted, and
  recorded in third-party notices.
- The frontend receives narrow commands, not arbitrary shell/filesystem access.

## 6. Workstreams

Workstream IDs are stable portfolio identifiers. Individual executable packet
IDs live in the implementation guide.

### F — Foundations

Outcome: one trustworthy codebase with quality gates.

Status: complete.

- F0 product identity, license, support decisions, and package-manager choice.
- F1 one engine source, package layout, repository hygiene.
- F2 tests, lint/type checks, CI, typed baseline, version synchronization.

### B — Bootstrap and Distribution Runtime

Outcome: the desktop works on a clean supported machine.

- B1 publishable PyPI package and trusted publishing.
- B2 verified `uv` sidecar and managed Python runtime.
- B3 secure download/extraction/install for FFmpeg, Real-ESRGAN, and models.
- B4 optional RIFE installation on demand.
- B5 setup/repair center and component health.
- B6 packaged end-to-end clean-machine tests.
- B7 optional fully offline runtime after online bootstrap is stable.

### C — Engine and CLI Contracts

Outcome: GUI and automation consume stable engine-owned truth.

- C1 complete typed progress integration and stable error/exit codes.
- C2 normalized `inspect --json`.
- C3 versioned recipe and recipe-schema contracts.
- C4 resolved `plan --json` with warnings and resource estimates.
- C5 first-class cached `preview`.
- C6 `capabilities` and `doctor`.
- C7 arbitrary-path batch and versioned manifest.
- C8 backward-compatible subcommand organization.
- C9 progress enhancements: weighted overall progress, ETA, throughput, and
  artifacts.

### D — Desktop Application Service

Outcome: reliable process and job behavior behind any GUI.

- D1 typed stdout/stderr bridge and terminal mapping.
- D2 cooperative cancellation, process-tree fallback, and resumability.
- D3 durable job store and restart reconciliation.
- D4 single-GPU queue scheduler.
- D5 preview artifact transport/cache.
- D6 history, result validation, and support bundle.
- D7 updater and safe active-job exclusion.

### X — Desktop Experience

Outcome: an understandable visual workstation.

- X1 responsive accessible application shell and design tokens.
- X2 import, drag/drop, metadata, recent files, and source warnings.
- X3 simple controls, full Recipe editor, custom presets, dirty state, undo.
- X4 real fast/AI preview, timeline samples, compare modes, zoom, and HDR
  labeling.
- X5 engine-owned preflight, estimates, export, and guided recovery.
- X6 queue, active render, cancellation/resume, and concise activity.
- X7 completion, history, rerun/duplicate, reveal/open, notifications.
- X8 setup/repair, settings, cache/storage, diagnostics, and updates.
- X9 scopes and advanced creative work only after core preview/queue quality.

Detailed behavior and acceptance requirements are in
[`../GUI_MASTERPLAN.md`](../GUI_MASTERPLAN.md).

### R — Release and Distribution

Outcome: truthful, repeatable public delivery.

- R1 canonical version/changelog and release gates.
- R2 Tauri updater and updater signing.
- R3 native build matrix, checksums, draft GitHub Release, PyPI promotion.
- R4 Windows/macOS signing and notarization hooks with truthful fallback.
- R5 user documentation, screenshots, troubleshooting, and release smoke test.
- R6 winget, Scoop, Homebrew cask, and AUR only after immutable stable URLs.

## 7. Release Trains

Versions are proposed targets, not promises. A release is defined by gates, not
by a date.

### 0.3 — Installable Alpha

Purpose: prove installation and one reliable render on clean machines.

Required:

- B1–B6 except optional offline runtime.
- C1 typed progress v1 and stable terminal outcomes.
- D1–D2.
- X8 minimal setup/repair states.
- R1, R3–R5; R2 must be present in the first broadly distributed build.
- Existing render form remains usable.

Not required:

- Full preview workstation, persistent multi-job queue, advanced CLI
  subcommands, or scopes.

### 0.4 — Preview Workstation Beta

Purpose: make visual decisions before expensive renders.

Required:

- C2–C6 and C8.
- D5.
- X1–X5.
- Full Recipe round-trip and custom presets.
- Real single-frame AI preview and honest HDR display labeling.
- Preflight with dimensions, stages, audio/color consequences, warnings, and
  disk estimate.

### 0.5 — Workflow Beta

Purpose: support serious repeated and overnight use.

Required:

- C7 and useful C9 metrics.
- D3–D4 and D6.
- X6–X8 complete.
- Durable queue/history, restart recovery, arbitrary-path batch, result
  actions, and support bundle.

### 1.0 — Trustworthy Public Product

Purpose: promote only after product and delivery prove durable.

Required:

- Two successful release/update drills.
- Clean-machine tests on every advertised target.
- Signing/notarization for every platform marketed to nontechnical users, or
  an explicit support decision to exclude that platform.
- Accessibility and keyboard certification for the primary workflow.
- Preview/render parity tests and cancellation/resume tests.
- Documentation and screenshots match the released application.
- No P0/P1 correctness or data-loss issue open.

## 8. Dependency and Parallelism Model

The critical path is:

```text
B runtime/tools
   -> C1 typed protocol
      -> D1 typed bridge -> D2 cancellation
         -> 0.3

C2 inspect ---------> X2 import
C3 recipe schema ---> X3 full editor
C4 plan ------------> X5 preflight
C5 preview ---------> D5 transport -> X4 preview
X1 shell -----------+----------------^

D2 + C4 -> D3 durable jobs -> D4 queue -> X6/X7
C6 ------> X8 setup/diagnostics
C7 ------> X6 batch queue
```

Safe parallel lanes after shared contracts are merged:

- Engine inspect, recipe schema, and preview can proceed in parallel when they
  avoid the same CLI parser hotspot.
- Frontend shell/design tokens can proceed beside engine contracts.
- Bootstrap downloader and archive extraction can proceed in parallel behind
  a fixed manifest/API.
- Release documentation can proceed beside implementation but screenshots and
  behavior claims wait for the actual UI.

Unsafe parallel edits:

- Multiple agents rewriting `engine/src/auvide/cli.py`.
- Multiple agents restructuring `desktop/src/main.ts`.
- Multiple agents editing the Tauri command registration in `lib.rs`.
- Runtime/bootstrap agents independently changing the same manifest schema.

The implementation guide assigns an integration owner to each hotspot and
uses additive modules to maximize parallel work.

## 9. Delivery Discipline

Every implementation packet:

- Has one owner, one bounded outcome, primary files, dependencies, tests,
  acceptance evidence, and explicit non-goals.
- Starts from a clean understanding of current source; packet status is not
  inferred from this plan.
- Preserves unrelated worktree changes.
- Updates tests and user-facing documentation with behavior.
- Uses a focused Conventional Commit, the maintainer's configured signing
  identity, and the repository's push policy.
- Runs `python scripts/sync_version.py --check`; only deliberate releases bump
  versions.
- Never edits generated `desktop/src-tauri/engine/`.
- Records skipped checks and blockers instead of declaring success.

Agent handoffs use the exact template in `MASTERPLAN_IMPLEMENTATION.md`.

## 10. Quality Gates

### Per change

- Relevant Python, Rust, TypeScript, and schema tests.
- Formatting/lint/type/build checks for touched languages.
- No new human-log parsing.
- No engine rule duplicated in Rust/TypeScript.
- No user path, downloaded executable, generated media, or credential committed.

### Per release

- Isolated wheel/sdist installation outside the checkout.
- Native desktop bundles for advertised targets.
- Clean-account setup and restart.
- SDR and HDR synthetic renders verified with FFprobe.
- Cancel after a completed chunk, restart, resume, and prove reuse.
- Spaces, non-ASCII paths, low disk, denied output, offline setup, and corrupt
  artifact cases.
- Update N -> N+1 with no active job and while a job is active.
- Install/uninstall preserves user output.

## 11. Product Risks

| Risk | Guardrail |
|---|---|
| GUI becomes a second engine | Engine-owned contracts and parity tests |
| Preview differs from render | Same recipe/filter builders; fidelity labels |
| GPU/VRAM variance | capabilities, benchmark, tile recovery, preflight |
| Long jobs lose work | chunk checkpoints, durable jobs, cooperative cancel |
| UI overload | presets, progressive disclosure, active-setting summaries |
| Schema drift | versioned schema, generated/validated client types |
| Tool URLs rot | pinned immutable release assets, hashes, repair behavior |
| Archive/download attack | HTTPS, checksum, limits, safe extraction |
| SmartScreen/Gatekeeper | signing budget/support decision before promotion |
| HDR expectations | prominent stylized-remap and monitor-limit explanations |
| Scope expands to editing suite | enhancement/export boundary |

## 12. Definition of Success

The roadmap is successful when:

- A new desktop user reaches a real before/after preview and completed output
  without a terminal.
- A long render can be understood, cancelled, resumed, recovered after restart,
  and reproduced later.
- A power user can perform the same inspect/plan/preview/render/batch workflow
  through documented versioned CLI contracts.
- The same recipe resolves to the same effective pipeline in GUI and CLI.
- Releases are repeatable, verifiable, supportable, and honest about signing,
  platform support, and HDR limitations.
