# auvide GUI Masterplan

Status: reconciled child plan of `docs/MASTERPLAN.md`

Date: 2026-07-24

Scope: Tauri desktop app, the Python CLI contracts that support it, and shared
job/recipe behavior

Primary objective: turn the current thin render form into a trustworthy visual
video-enhancement workstation without duplicating the Python engine in the GUI

Document ownership:

- [`docs/MASTERPLAN.md`](docs/MASTERPLAN.md) owns portfolio scope, workstream
  IDs, release trains, and release gates.
- This document owns detailed GUI/CLI experience requirements and product
  acceptance.
- [`docs/MASTERPLAN_IMPLEMENTATION.md`](docs/MASTERPLAN_IMPLEMENTATION.md) owns
  executable packets, file boundaries, dependencies, tests, and small-agent
  handoffs.
- Current source and tests remain the evidence of implemented behavior.

## 1. Executive Summary

The engine already has most of the processing vocabulary needed for a strong
desktop product: upscale models, HDR/SDR output, restoration, interpolation,
delivery targets, LUTs, curves, trim, recipes, previews, resumable chunks, and a
versioned progress protocol. The next level is therefore not primarily “more
sliders.” It is a better product surface around the engine:

1. Make setup, source analysis, and safe defaults effortless.
2. Make the visual result inspectable before a long render.
3. Make a user-selected project folder the persistent home for imported-media
   records, settings, timeline edits, conversion state, and job history.
4. Add a focused clip-assembly timeline: external audio, detachable audio/video,
   cuts/trims, and rearrangement.
5. Replace the single transient render with a persistent queue and history.
6. Expose simple controls first and reveal expert controls progressively.
7. Make every GUI operation available through a stable, machine-readable CLI
   contract so the desktop app, scripts, and future integrations behave alike.

The recommended desktop information architecture is:

```text
Setup / Home
    -> Default project chooser modal
         recent workspaces | New Project | Open Folder
    -> Import and source analysis
    -> Edit and Enhance workspace
         Media | Timeline | Preview | Restore | Upscale | Motion | Color
    -> Export
         format | quality | target | destination
    -> Queue
         progress | pause/cancel | resume | logs
    -> History
         inspect | reveal | rerun | duplicate recipe
```

The editor remains intentionally smaller than a full nonlinear editor. The
first editing milestone covers project persistence, a media bin, video/audio
tracks, external audio import, detach, split/trim, and rearrangement. It does
not include transitions, titles, effect keyframes, or a mixing console.

### 1.1 Alignment with the portfolio roadmap

This plan uses the general masterplan's workstream IDs:

| GUI plan concern | General workstream | Target train |
|---|---|---|
| Typed render state and cancellation | C1, D1–D2 | 0.3 |
| Setup and clean-machine readiness | B1–B6, X8 | 0.3 |
| Application shell and full recipe editor | X1, X3 | 0.4 |
| Source inspection | C2, X2 | 0.4 |
| Recipe schema and client types | C3, X3 | 0.4 |
| Real preview | C5, D5, X4 | 0.4 |
| Plan, capabilities, preflight | C4, C6, X5 | 0.4 |
| Durable jobs, queue, and history | C7, D3–D4, D6, X6–X7 | 0.5 |
| Project folders and basic timeline editing | C10, D8, X9 | 0.5 |
| Advanced progress and creative tools | C9, X10 | 0.5+ |
| Updates, signing, and distribution | R1–R6, X8 | 0.3–1.0 |

The phases in Section 8 are experience increments, not a second independent
release schedule. Packet IDs and merge order are canonical only in the
implementation guide.

## 2. Current-State Audit

### 2.1 What is already strong

- `engine/src/auvide/` is the canonical engine. Both GUI and CLI can share the
  same recipe and processing logic.
- `Recipe` already represents upscale, grade, HDR, encode, trim, audio,
  interpolation, restoration, LUT, target, and curve settings.
- `--dump-config` already exposes styles, targets, grade knobs, and models to
  clients.
- `--progress-json` already emits versioned NDJSON events, with human logs kept
  on stderr.
- Rust has a typed protocol parser in `desktop/src-tauri/src/protocol.rs`.
- TypeScript has a reducer and tests in `desktop/src/render-state.ts`.
- Rendering is chunked and resumable.
- The desktop app already has native input/output dialogs, dynamic styles,
  grade sliders, and a curves control.
- Runtime and dependency bootstrap work is already underway in the Tauri
  backend.

These are valuable foundations. The masterplan should extend them instead of
introducing a second processing model in TypeScript or Rust.

### 2.2 Current experience gaps

The active Tauri UI currently behaves like a compact parameter form:

- It exposes only scale, model, HDR, interpolation, target, denoise, grade
  knobs, and curves.
- Recipe fields such as encoder, CRF, encoder preset, HDR gain, trim, audio,
  slow motion, deinterlace, stabilize, and LUT are not controllable.
- It has no source thumbnail, playback, frame scrubber, before/after view,
  scopes, metadata summary, output estimate, or preview-render workflow.
- It does not currently offer recipe save/load, named custom presets, drag and
  drop, recent files, batch import, a job queue, or render history.
- The interface disables itself around one running process and does not persist
  job state across app restarts.
- The desktop now consumes typed progress and terminal events through the
  existing reducer; human logs are diagnostics only. Durable queue/history
  state remains a later job-service milestone.
- Advanced errors are mostly “see log”; there is no guided recovery for missing
  tools, VRAM failures, unsupported codecs, disk pressure, or interrupted jobs.
- The fixed 1080 × 820 form has only limited layout adaptation and no explicit
  keyboard, focus, reduced-motion, or high-contrast design.

### 2.3 CLI gaps that constrain the GUI

The CLI has broad render flags, but most non-render operations are modes on one
large `argparse` parser. The desktop app needs additional stable contracts:

- Structured source probing now exists as `auvide.media` and is used by the
  desktop metadata summary; richer import, thumbnail, and workspace flows
  remain pending.
- Structured effective-plan output, including resolved dimensions, frame rate,
  output color mode, stages, warnings, disk estimate, and capability checks.
- A versioned schema for recipe/config fields so TypeScript does not mirror the
  Python dataclass by hand.
- A first-class preview operation with machine-readable output paths.
- Device, encoder, model, and dependency discovery.
- Batch input from arbitrary paths or manifests rather than only `./input`.
- Consistent error codes and recovery hints.
- Progress events with overall weighted progress, throughput, ETA, and job
  identity rather than only per-stage counters.

## 3. Product Principles

### 3.1 Simple first, powerful on demand

The default view should answer four questions:

1. What did I import?
2. What improvement am I asking for?
3. What will the result look like and cost?
4. Where is the job now?

Advanced encoding, GPU, chunk, scratch, and color controls belong in expandable
sections. Hiding complexity must never hide an active non-default setting; the
collapsed section should show a summary badge such as `QSV · CRF 20 · audio`.

### 3.2 Preview before commitment

Video enhancement is expensive and subjective. Any setting with a meaningful
quality or time trade-off should be previewable on a representative frame or a
short loop before the full render.

### 3.3 Explain outcomes, not implementation vocabulary

Prefer “Preserve original frame rate” and “Smooth motion” over exposing only
`slowmo=false`. Prefer model recommendations such as “Best for live action” with
the internal model name in secondary text.

### 3.4 One job model everywhere

The GUI must serialize the same versioned job recipe the CLI accepts. The
engine owns defaults, validation, compatibility, capability decisions, and
effective plans. The GUI owns presentation and interaction.

### 3.5 Never lose expensive work

Every accepted job receives a durable ID, immutable source recipe, work
directory, progress record, and result record. Cancellation should clearly
distinguish:

- Stop and keep resumable work.
- Stop and discard temporary work.
- Remove a queued job that has not started.

### 3.6 The project folder is the workspace

A project is a user-selected folder, not transient application state. Opening
that folder must restore its imported-media registry, edit timeline, overall
settings, preview context, queue, completed/failed/interrupted conversion
status, and history. Portable project data is versioned and atomically saved;
regenerable thumbnails, waveforms, proxies, and previews are clearly separated
from durable state.

### 3.7 Editing stays focused

The timeline exists to prepare clips for enhancement and delivery. Its first
contract is deliberately finite: add media, add external audio, detach linked
audio/video, split or trim clips, delete them, and rearrange them on video/audio
tracks. These operations must share undo/redo and preview/render semantics.

## 4. Target User Experience

### 4.1 First launch and environment health

Show a dedicated setup experience instead of allowing the first render to
discover every dependency problem:

- Check managed Python, FFmpeg/FFprobe, Real-ESRGAN, Vulkan/GPU, models, writable
  app-data paths, and free disk space.
- Display each component as `Ready`, `Downloading`, `Needs attention`, or
  `Optional`.
- Offer one primary action: **Install required components** or **Repair**.
- Show download sizes, licenses, checksums, and installation location.
- Allow advanced users to use detected system tools.
- Keep setup accessible later under Settings > Components.

Acceptance criteria:

- A new user can reach an import-ready screen without opening a terminal.
- A failed component names the failed check and gives a retry or path-selection
  action.
- The app never starts an expensive job with a known missing hard dependency.

### 4.2 Home and import

When no project is open, the GUI defaults to a project chooser modal rather
than an empty editor. Its main pane presents **New Project** and **Open
Folder**. A side pane lists recently opened project workspaces, most recent
first, with project name, folder path, last-opened time, and missing/offline
state. Selecting a valid recent entry opens it directly.

The modal:

- Appears on first launch, normal launch with no restorable project, and after
  **Close Project**.
- **New Project** asks for a new or empty folder and initializes the versioned
  workspace only after confirmation. **Open Folder** validates an existing
  `auvide.project.json`; an ordinary folder is never modified unless the user
  explicitly chooses to initialize it as a project.
- Keeps the recent-workspace list visible at the side on desktop widths and
  collapses it into an accessible secondary pane at the minimum width.
- Supports keyboard navigation, Enter to open, and context actions to reveal,
  locate a moved folder, or remove an entry from recents without deleting it.
- Does not treat dismissing the modal as a usable empty workspace. If global
  Settings/About remain reachable behind it, project actions stay disabled.
- May offer **Reopen last project** after an unclean shutdown, but must first
  perform normal workspace and conversion-state reconciliation.

After a project opens, its workspace shows a large import drop zone, project
jobs, and environment health in a small status area. Dropping a recognized
project folder while another project is open requests a save/close transition;
dropping media imports it into the current project.

After import, asynchronously display:

- Thumbnail and duration.
- Resolution, frame rate, codec, bit depth, color space/HDR status, audio, and
  file size.
- Detected content hints where deterministic: interlaced, portrait/landscape,
  variable frame rate, very low resolution, or no audio.
- Source warnings: unsupported stream, corrupt timestamps, insufficient disk,
  or an output path that would overwrite the input.

Support:

- Drag/drop one or many files.
- Import common standalone audio, including MP3, AAC/M4A, WAV, and FLAC.
- Open-with/file-association flow.
- Recent project folders, with missing/moved entries removable or locatable.
- Duplicate detection in the current queue.
- Keyboard paste of a local file path.

### 4.3 Edit and enhance workspace

Use a three-region layout:

```text
┌──────────────────────────────────────────────────────────────────────┐
│ App bar: project folder | saved/saving | undo/redo | help           │
├──────────────┬───────────────────────────────────┬───────────────────┤
│ Media bin /  │ Preview                           │ Inspector         │
│ Tool rail    │ before/after / split / zoom       │ Clip or enhance   │
│              │                                   │ controls          │
│ Edit         │ V1 [video clips..............]    │ + Advanced        │
│ Enhance      │ A1 [linked audio....][MP3....]    │                   │
│ Export       │ time ruler / playhead / zoom      │                   │
├──────────────┴───────────────────────────────────┴───────────────────┤
│ Job summary: output · estimate · warnings             Add to Queue  │
└──────────────────────────────────────────────────────────────────────┘
```

The layout should collapse to preview + a slide-over inspector at narrower
window sizes. It must remain usable at the configured minimum window size.

#### Media bin and timeline

- Every imported video or audio asset appears in the project media bin with
  online/offline, linked/managed, duration, format, and usage state.
- Dropping a video on the timeline creates linked video and audio clips when
  the source contains audio. Linked selection and movement preserve sync.
- **Detach audio** converts that pair into independently selectable audio and
  video clips at the same timeline position without transcoding the source.
- Standalone audio such as MP3 can be placed on an audio track, moved, trimmed,
  split, deleted, and rearranged like detached source audio.
- Split at the playhead, trim handles, delete, drag-to-reorder, snapping, and
  keyboard-accessible equivalents form the minimum edit toolset.
- Edits are non-destructive references to source time ranges. A cut never
  modifies or overwrites imported media.
- Preview, preflight, resume compatibility, and final render consume the same
  saved timeline revision. A queued job records an immutable snapshot so later
  edits cannot change a running conversion.
- Overlapping video clips, transitions, titles, keyframed effects, nested
  sequences, and advanced mixing are explicitly outside the first editor.

#### Preview modes

- Original.
- Processed.
- Draggable split wipe.
- Side by side.
- Flash original while holding a key.
- 1:1 pixel view and fit-to-window.
- Optional difference view for diagnosing sharpening or denoise.
- Sample at current time, plus automatic samples at 20%, 50%, and 80%.
- Short preview loop, initially 2–5 seconds and proxy-resolution by default.

The preview must label what it represents:

- `Fast preview` when using proxy/bicubic approximations.
- `AI preview` when Real-ESRGAN was actually run.
- `Display-mapped HDR preview` when an SDR monitor cannot show the HDR signal
  directly.

Never imply that an SDR canvas is a color-accurate HDR monitor.

#### Recommended simple controls

- **Enhancement strength**: 2× / 3× / 4×.
- **Content type**: Auto / Live action / Animation / Detail.
- **Look**: style cards with thumbnails and active-state indication.
- **Output**: Keep source / YouTube / Web / Vertical / Square.
- **Motion**: Original / Smooth 2× / Slow motion.
- **Restore**: Off / Light / Strong, with a details expander.

These controls translate into an engine recipe; they are not a separate
high-level pipeline.

#### Expert controls

- Exact model and GPU.
- Tile size and chunk size.
- Deinterlace, denoise level, stabilization.
- Interpolation factor and slow-motion behavior.
- Exposure, saturation, vibrance, contrast, midtones, warmth, tint, sharpen.
- Curves with add, move, delete, reset, numeric point entry, and keyboard
  operation.
- LUT picker, LUT clear action, and LUT status.
- HDR gain.
- Encoder, quality, speed preset, and output audio.
- Trim in/out with timecode input.
- Scratch directory, keep intermediates, and resume behavior.

Every numeric control should support:

- Drag/range input.
- Direct numeric entry.
- Double-click or explicit button to reset.
- Accessible name and current value.
- Optional fine adjustment with keyboard modifiers.

### 4.4 Project workspace persistence

The user can choose any writable folder as a project workspace. A valid folder
contains:

```text
project-folder/
  auvide.project.json       project identity, schema, settings, status index
  media.json                imported-media records and fingerprints
  timeline.json             tracks, clips, links, source ranges, ordering
  media/                    optional project-managed source copies
  exports/                  default output destination
  .auvide/
    autosave/               recoverable pending edits
    cache/                  disposable thumbnails/waveforms/proxies/previews
    jobs/<job-id>/          immutable submissions, state, events, logs
```

Import offers or remembers two explicit modes: **Link in place** and **Copy
into project**. Linked paths may be absolute, but retain fingerprints and
relative hints for relinking. Managed media uses relative paths so the project
folder can be moved as a unit. The app never copies large media silently.

Autosave durable edits after a short debounce and show `Saving`, `Saved`, or
`Save failed`. Use atomic replacement plus recovery copies. On open:

- Validate and migrate supported schema versions without losing unknown fields.
- Reconcile any job marked running with actual process/checkpoint state.
- Mark unavailable linked assets offline and offer Locate/Relink.
- Detect a concurrent writer and open read-only or offer an explicit recovery
  flow.
- Restore the last playhead, selection, panel layout, and preview target as
  convenience state without confusing it with render settings.

The recent-project side list is an app-level index of workspace pointers and
display metadata only. The project folder remains authoritative; removing a
recent entry never removes the project or any media.

### 4.5 Preflight and export

Before queueing, show an effective plan generated by the engine:

- Source -> output dimensions and frame rate.
- HDR/SDR, codec, quality, and audio result.
- Ordered stages.
- Expected crop/pad with a safe-area overlay for social formats.
- Estimated render time as a range, based on a short benchmark when possible.
- Peak scratch disk estimate and current free space.
- Known compatibility changes, for example “slow motion removes source audio.”
- Warnings with severity and a direct action to the responsible setting.

The primary action should say **Add to Queue** once queueing exists. A secondary
**Render now** is useful when the queue is empty.

### 4.6 Queue and active render

Each job card should show:

- Thumbnail, source name, output target, and recipe summary.
- Overall progress and current stage.
- Stage progress, processed frames/chunks, throughput, elapsed time, and ETA.
- Queued/running/paused-cancelled/completed/failed state.
- Actions appropriate to state: move, start next, cancel, resume, retry,
  duplicate, reveal source/output, or view log.

Keep detailed logs collapsed by default. A concise activity feed should
translate engine events into readable messages. Raw logs remain copyable and
exportable for support.

Initial concurrency should be one GPU render at a time. The queue architecture
may later permit CPU-only probes and previews concurrently, but must avoid
multiple uncoordinated Real-ESRGAN jobs exhausting VRAM.

### 4.7 Completion and history

On completion:

- Show output path, file size, dimensions, color mode, duration, and render
  time.
- Offer **Play**, **Reveal in folder**, **Copy path**, **Render another
  version**, and **Open comparison**.
- Persist the effective recipe and engine/app versions used.
- Add a non-blocking system notification if enabled.

History must survive restart and distinguish a completed result from a missing
or externally moved output. It should allow rerunning with current engine
defaults or reproducing the exact historical recipe.

## 5. Visual and Interaction Direction

### 5.1 Visual language

Retain the dark, focused character of the current app, but introduce a small
token system rather than one-off CSS values:

- Background, surface, elevated surface, field, and overlay layers.
- Primary text, secondary text, disabled text.
- Accent, success, warning, danger, and info roles.
- 4/8 px spacing rhythm.
- 6/10/14 px radius tiers.
- Consistent focus ring and selected-card treatment.
- Type scale for app title, section title, body, label, and metadata.

Use color to reinforce state, never as the only signal. HDR/SDR, model, and
warning badges need text or icons as well.

### 5.2 Feedback and micro-interactions

- Preview refreshes should use a short debounce and show stale/updating state.
- Expensive AI previews require an explicit action or an idle delay, not one
  render per slider pixel.
- Style changes may crossfade between cached preview images.
- Queue reordering should provide both drag and keyboard buttons.
- All destructive actions need precise wording and, when work would be lost, a
  confirmation.
- Respect `prefers-reduced-motion`.

### 5.3 Accessibility baseline

- WCAG 2.2 AA contrast for text and controls.
- Full keyboard navigation in logical visual order.
- Visible focus on every interactive control.
- Semantic buttons, labels, groups, headings, progress elements, and live
  regions.
- No hover-only functionality.
- Curves editor has numeric/keyboard fallback.
- Minimum 40 × 40 px practical pointer targets for primary actions.
- Screen-reader announcements are rate-limited; do not announce every frame.
- UI zoom from 80–200% remains usable without clipped actions.

### 5.4 Undo and unsaved state

Within a workspace, keep a bounded undo/redo stack spanning timeline, media-bin,
and recipe edits. Project autosave persists the current revision; explicit
**Save Recipe As** remains available for portable presets. Closing during a
failed/pending save must offer Retry, Save elsewhere, or Discard. No state
label should imply that non-destructive timeline edits changed source media.

## 6. CLI and Engine Expansion

The CLI should evolve into a stable application interface while preserving
today’s commands. Existing usage such as `auvide input.mp4 --scale 2` remains a
supported alias for `auvide render input.mp4 --scale 2`.

### 6.1 Proposed command surface

```text
auvide render INPUT [options]
auvide preview INPUT [options]
auvide inspect INPUT [--json]
auvide plan INPUT [options] [--json]
auvide batch INPUT... [options]
auvide jobs inspect WORK_DIR [--json]
auvide config show [--json]
auvide config schema [--json]
auvide capabilities [--json]
auvide doctor [--json] [--benchmark]
auvide presets list [--json]
auvide models list [--json]
auvide project inspect PROJECT_DIR [--json]
auvide project validate PROJECT_DIR [--json]
auvide project render PROJECT_DIR [--sequence main]
```

Migration approach:

1. Keep the current top-level parser and behavior.
2. Extract parser builders and validation into testable modules.
3. Add subcommands without removing legacy flags.
4. Emit a one-time warning only if a future breaking migration is actually
   scheduled; do not deprecate the convenient legacy render syntax merely for
   aesthetic reasons.

### 6.2 `inspect`: source metadata contract

`auvide inspect INPUT --json` should return a versioned object owned by the
engine:

```json
{
  "schema": "auvide.media",
  "version": 1,
  "path": "C:/video/input.mp4",
  "video": {
    "width": 1920,
    "height": 1080,
    "fps": {"numerator": 30000, "denominator": 1001},
    "frames": 18000,
    "duration_seconds": 600.6,
    "codec": "h264",
    "pixel_format": "yuv420p",
    "bit_depth": 8,
    "color_primaries": "bt709",
    "transfer": "bt709",
    "interlaced": false,
    "variable_frame_rate": false
  },
  "audio": {"present": true, "codec": "aac", "channels": 2},
  "container": {"format": "mov,mp4", "size_bytes": 123456789},
  "warnings": []
}
```

Requirements:

- Preserve exact rational frame rate in addition to a display value.
- Normalize missing values to `null`; do not invent metadata.
- Include stable warning codes and human messages.
- Add unit and real-FFprobe fixture tests.

### 6.3 `plan`: resolved job contract

`auvide plan` replaces GUI-side inference and extends `--dry-run`:

- Accept the same recipe/overrides as render.
- Perform validation and capability checks without modifying media.
- Resolve automatic output paths, dimensions, target transforms, frame rate,
  audio behavior, model/native scale, stages, and scratch directory.
- Return structured warnings/errors.
- Estimate frame count and scratch bytes.
- Optionally include a benchmark-derived ETA range.

`--dry-run` can remain human-readable, while `plan --json` is the client
contract.

### 6.4 Recipe schema and forward compatibility

Add a versioned recipe envelope:

```json
{
  "schema": "auvide.recipe",
  "version": 1,
  "engine_min": "0.3.0",
  "recipe": {
    "scale": 2,
    "model": "animevideo",
    "hdr": "on"
  }
}
```

The current unwrapped JSON remains readable. On load:

- Fill missing fields from engine defaults.
- Ignore additive unknown fields only when safe and report them as warnings.
- Reject incompatible schema versions with an actionable message.
- Preserve explicit versus default values in the effective plan where useful.

`auvide config schema --json` should expose field type, enum values, range,
step, default, label, help, section, dependencies, and visibility conditions.
The GUI can then render most controls from engine-owned metadata. Keep bespoke
components for curves, file pickers, and other rich fields.

This eliminates the current hand-maintained Recipe shape as the only guard
against Python/TypeScript drift. Generated TypeScript types or runtime schema
validation should be produced from the same schema in CI.

### 6.5 Project and timeline contracts

Add versioned `auvide.project` and `auvide.timeline` schemas. The project
contract owns workspace identity, settings, media registry references, active
timeline revision, and a conversion-status index. The timeline contract owns
tracks, stable clip IDs, media IDs, source in/out ranges, timeline position,
ordering, link groups, and enabled/muted state.

Timeline resolution is engine-owned and deterministic. `project validate`
checks schemas, paths, fingerprints, media compatibility, edit ranges, and
status consistency without modifying sources. `project render` snapshots the
resolved project/timeline/recipe into an immutable job before processing.

Migrations preserve unknown additive fields where safe. A newer unsupported
major version opens read-only with an actionable message rather than being
silently rewritten.

### 6.6 Preview command

Promote preview from render flags to a first-class command:

```text
auvide preview INPUT
  --recipe look.json
  --at 120.5
  --duration 3
  --mode frame|loop
  --quality fast|ai
  --max-width 1280
  --output-dir PATH
  --json
```

The JSON result should identify every artifact, its timestamp, dimensions,
preview fidelity, color-display transform, and cache key. A cache key derived
from source fingerprint + relevant recipe subset allows the GUI to reuse
previews safely.

Preview cancellation must use the same run ID and cancel mechanism as renders.

### 6.7 Batch and manifest input

Replace the fixed `./input` limitation with:

```text
auvide batch clip1.mp4 clip2.mov
auvide batch --from job-list.json
auvide batch --glob "D:/captures/*.mkv"
```

The manifest may specify a shared recipe plus per-item output/overrides.
Machine-readable batch progress includes `job_id`, `item_index`, and
`item_count`. Default behavior continues after an item failure and returns a
summary with a nonzero partial-failure exit code.

### 6.8 Capabilities and doctor

`capabilities --json` should answer what is available, not mutate the machine:

- Tool paths and versions.
- Models and model files.
- GPUs/devices visible to Real-ESRGAN.
- Encoders available in FFmpeg.
- Filters required for stabilization, LUTs, and color conversion.
- HDR encode support.
- Writable/free storage.
- Engine/version/schema information.

`doctor` runs deeper checks and may optionally perform a tiny benchmark. Stable
codes should map to GUI recovery:

```text
tool.ffmpeg.missing
tool.realesrgan.models_missing
gpu.vulkan.unavailable
encoder.qsv.unavailable
storage.scratch.insufficient
source.color.metadata_missing
job.output.same_as_input
```

### 6.9 Progress protocol v2

Finish wiring protocol v1 before extending it. The GUI should consume typed
events from Rust, never parse human text.

Then add v2 fields or additive v1 fields where compatible:

- `job_id`, `run_id`, and optional `parent_batch_id`.
- Overall `current`, `total`, and percent based on weighted stages.
- Stage-local progress.
- `elapsed_seconds`, `eta_seconds`, and measured units/second.
- Source/output summary in the plan.
- Recoverable warning/error code, affected setting, and suggested actions.
- Artifact events for previews, logs, and completed outputs.
- Resumability metadata and checkpoint size.

Progress weighting must be engine-owned because only the engine knows the
active stage plan. The frontend should display it, not guess that each stage
costs the same.

### 6.10 Exit codes

Document stable categories:

- `0`: completed.
- `2`: invalid arguments or recipe.
- `3`: dependency/capability unavailable.
- `4`: source inspection/decoding failure.
- `5`: processing/encoding failure.
- `6`: output/storage failure.
- `7`: partial batch failure.
- `130`: user cancellation.

Detailed machine consumers use event/error codes; exit codes remain broad and
shell-friendly.

## 7. Desktop Architecture

### 7.1 Responsibility boundaries

```text
TypeScript UI
  interaction, media bin/timeline, forms, preview, queue views
        |
        | typed Tauri commands/events
        v
Rust application service
  project workspace I/O, process supervision, durable jobs,
  filesystem/dialog access, tool bootstrap, protocol parsing, OS integration
        |
        | versioned recipe + CLI JSON/NDJSON
        v
Python engine
  schemas, validation, timeline resolution, source inspection,
  effective plan, preview/render execution, progress, processing
```

Do not put FFmpeg filter construction, style resolution, target transforms, or
model selection rules in the frontend.

### 7.2 Frontend structure

Split `desktop/src/main.ts` before adding major features:

```text
desktop/src/
  app/
    app.ts
    router.ts
    store.ts
  api/
    tauri.ts
    generated-contracts.ts
  features/
    setup/
    import/
    project/
    media-bin/
    timeline/
    workspace/
    preview/
    export/
    queue/
    history/
    settings/
  components/
    button.ts
    field.ts
    disclosure.ts
    progress.ts
    dialog.ts
    toast.ts
  state/
    render-state.ts
    project-state.ts
    timeline-state.ts
    recipe-state.ts
    queue-state.ts
  styles/
    tokens.css
    base.css
    components.css
    workspace.css
```

A framework is optional. The current product can remain in TypeScript with
small view modules, but state transitions and DOM ownership must be explicit.
Adopt a framework only if it demonstrably reduces complexity for routing,
forms, and queue updates; do not combine a framework migration with protocol
or processing changes.

### 7.3 Tauri command surface

Proposed commands:

```text
get_app_health
repair_component
create_project
open_project
save_project
close_project
import_project_media
relink_project_media
inspect_media
get_recipe_schema
plan_job
create_preview
cancel_preview
enqueue_job
list_jobs
reorder_jobs
cancel_job
resume_job
retry_job
remove_job
reveal_path
open_output
export_support_bundle
```

Commands should return typed serializable structs, not arbitrary JSON once the
contract stabilizes.

### 7.4 Persistent job store

Use `<project>/.auvide/jobs/<job-id>/` as the durable unit:

```text
job.json              immutable submitted recipe and source
state.json            atomically updated current state
effective-plan.json   resolved engine plan
events.ndjson         bounded or rotated event history
render.log            human diagnostics
cancel.requested      cooperative cancellation signal
```

Start with atomic files because the queue is single-process and job-centered.
Move to SQLite only when search, large history, multi-process coordination, or
data migration makes it worthwhile. Do not add a database merely to store a
small queue.

On app startup, reconcile `running` jobs:

- If no owned child process remains, mark as interrupted.
- If resumable work exists, offer Resume.
- Never silently restart an expensive job.

App data stores recent-project pointers and global setup/settings only.
Project-specific jobs, history, cache policy, media registry, recipe, timeline,
and conversion status remain with the project folder.

### 7.5 Process supervision and cancellation

- Replace “PID only” state with a job record and child handle/process-group
  strategy.
- Launch the engine with `--progress-json`, `--run-id`, and an absolute
  `--cancel-file`.
- Parse stdout using `protocol.rs`; forward stderr as logs.
- Prefer cooperative cancellation through the cancel file.
- After a grace period, terminate the process tree and preserve resumable work.
- Record the final state before notifying the frontend.
- Ensure app exit prompts when a render is active and offers background
  behavior only if the platform implementation truly supports it.

### 7.6 Preview transport

Do not stream unbounded frame data through events. The engine writes preview
artifacts into an app cache; Rust returns approved local asset URLs or byte
responses. Cache entries include source fingerprint and recipe cache key.

Limit cache size and expose **Clear preview cache** in Settings. Never place
preview artifacts next to the source unless the user explicitly exports them.

### 7.7 Security and privacy

- Retain a non-null CSP and add only the asset/media sources actually required.
- Validate paths in Rust and treat media metadata as untrusted text.
- Avoid inserting engine/model names through unsanitized `innerHTML`.
- Do not send source media, metadata, or thumbnails over the network.
- Telemetry, if ever added, is opt-in and contains no paths or media-derived
  images.
- Support bundles redact user directory prefixes where possible and require a
  preview before export.

## 8. Delivery Roadmap

Each phase should be implemented as small, independently testable slices.
Behavioral changes update tests and user documentation in the same slice.

### Phase 0 — Reconcile the existing foundation (C1, D1–D2; train 0.3)

Goal: make the current app reliable before redesigning it.

Deliverables:

- Wire `run_render` to `--progress-json --run-id --cancel-file`.
- Use `protocol.rs` and emit typed `render:progress` events.
- Connect `render-state.ts` to the visible UI and remove log-regex state
  inference.
- Separate stdout progress from stderr logs.
- Add cooperative cancellation and explicit resumable cancellation state.
- Add frontend tests for start, warning, failure, cancel, stale run IDs, and
  completion.
- Add Rust integration-style tests for process output routing and job cleanup.

Exit criteria:

- No frontend render state depends on matching `[1/3]` or `chunk N/M`.
- Cancellation produces a known final state and tells the user whether Resume
  is possible.
- A successful child exit without a completion event is shown as a failure.

### Phase 1 — Complete and organize the single-job form (X1, X3; train 0.4)

Goal: expose the engine honestly with progressive disclosure.

Deliverables:

- New application shell and responsive workspace layout.
- Default New Project/Open Folder modal with a side list of recent workspaces.
- Drag/drop input and metadata inspection.
- Full Recipe coverage: restore, motion, grade, LUT, HDR gain, encode, trim,
  audio, target, and advanced processing controls.
- Save/load recipe and custom named presets.
- Active style state, reset-to-default, dirty state, and undo/redo.
- Engine-generated effective pipeline summary and inline validation.
- Accessible control primitives and design tokens.

Exit criteria:

- Every public Recipe field is visible or intentionally documented as
  engine-only.
- Loading then saving a recipe is lossless for known fields.
- Simple mode can configure a good default render without opening Advanced.
- Expert mode can reproduce an equivalent CLI render.

### Phase 2 — Source inspection and real preview (C2–C3, C5, D5, X2, X4; train 0.4)

Goal: let users make visual decisions before a full job.

Engine/CLI:

- Add `inspect --json`, `plan --json`, and first-class `preview`.
- Add recipe schema metadata and generated/validated client types.
- Add preview cache keys and artifact events.

Desktop:

- Thumbnail, metadata, warnings, timeline sampling, and timecode entry.
- Original/processed/split/side-by-side preview.
- Fit, 1:1 zoom, pan, and fast/AI preview labels.
- Debounced preview invalidation and explicit AI-preview action.
- Optional waveform and vectorscope after core preview correctness.

Exit criteria:

- A user can compare a source frame with the actual AI/grade result.
- Stale previews are visibly marked and never presented as current.
- The same recipe produces the preview and full render filter settings.
- HDR preview limitations are clearly labeled.

### Phase 3 — Preflight, estimates, and guided recovery (C4, C6, X5; train 0.4)

Goal: prevent avoidable long-job failures.

Deliverables:

- `capabilities --json` and `doctor --json`.
- Effective output dimensions/FPS/color/audio plan.
- Scratch disk estimate and free-space check.
- Hardware encoder and GPU/model availability.
- Optional short benchmark and ETA range.
- Error-code-to-recovery-action mapping.
- Preflight screen and setting-linked warnings.

Exit criteria:

- Known missing tools/models fail before queueing.
- Unsupported QSV selection offers x265 or setup guidance.
- Insufficient storage shows required/available values.
- Estimates state their uncertainty and improve from observed history.

### Phase 4 — Project workspaces, basic editing, queue, and history (0.5)

Workstreams: C7, C10, D3–D4, D6, D8, and X6–X9.

Goal: make auvide useful for persistent projects and real overnight workloads.

Deliverables:

- Persistent job folders and queue scheduler.
- Create/open normal workspace folders with atomic autosave and schema
  migration.
- Make the no-project launch state the project chooser modal and maintain its
  recent-workspace side list without copying project state into app storage.
- Persist project settings, imported-media registry, timeline, conversion
  status, job history, and disposable cache boundaries.
- Media bin with linked or project-managed imports and offline relinking.
- Video/audio timeline with MP3 import, detach audio/video, split/trim, delete,
  snapping, undo/redo, and drag-to-rearrange.
- Multi-file import and arbitrary-path batch manifests.
- Reorder, cancel, resume, retry, duplicate, and remove.
- Restart recovery and interrupted-job reconciliation.
- Completion notifications and reveal/open actions.
- Search/filter history and missing-output detection.
- Per-job compact activity and expandable raw logs.

Exit criteria:

- Queue state and completed history survive app restart.
- Reopening or moving a managed-media project restores its edits and statuses.
- Linked missing media is reported as offline and can be relinked.
- Preview and render match the saved timeline revision, and running jobs remain
  immutable when the project is edited.
- Exactly one GPU-heavy render runs by default.
- A failed job does not erase the remaining queue.
- Resume reuses only compatible checkpoints.

### Phase 5 — First-run polish and distribution experience (B, R, X8; trains 0.3–1.0)

Goal: make the app installable and understandable by a stranger.

Deliverables:

- Setup/repair center integrated with managed dependency bootstrap.
- Download progress, cancel/retry, license notices, and checksum failures.
- Welcome tour limited to import, preview, and queue.
- Settings for components, cache, scratch path, notifications, theme, and
  accessibility.
- Signed installers, updates, file associations, and release screenshots.
- In-app diagnostics/support bundle.

Exit criteria:

- Clean-machine usability passes on every advertised OS.
- No system Python, `uv`, FFmpeg, or Real-ESRGAN installation is required for
  the desktop happy path.
- Update failure leaves the previous version runnable.

### Phase 6 — Advanced creative possibilities (C9, X10; post-0.5)

Only begin after preview, preflight, and queue reliability:

- RGB curves and per-channel scopes.
- Multiple preview snapshots and A/B recipe variants.
- Crop/reframe editor with target safe areas.
- Keyframes for grade values.
- Region/face-specific restoration when supported by the engine.
- Pluggable model downloads with provenance and license display.
- Watch folders and automation hooks.
- Export recipe/command as a reproducible shell script.

These features increase creative range but should not delay the trustworthy
single-clip workflow.

## 9. Prioritization

| Priority | Capability | User value | Dependency |
|---|---|---:|---|
| P0 | Typed progress wired end to end | High | Existing protocol code |
| P0 | Cooperative cancel/resume state | High | Typed progress + job ID |
| P0 | Full Recipe controls | High | Current config/recipe |
| P0 | Source inspect and validation | High | New `inspect --json` |
| P0 | Effective plan/preflight | High | New `plan --json` |
| P1 | Real frame preview + wipe | Very high | Preview command/cache |
| P1 | Recipe save/load and custom presets | High | Versioned recipe |
| P1 | Responsive/accessibility pass | High | New app shell |
| P1 | Persistent queue/history | High | Durable job service |
| P1 | Project workspace folders + autosave | Very high | Project schemas + workspace service |
| P1 | Media bin + basic video/audio timeline | High | Project workspace + timeline contract |
| P1 | MP3 import, detach, split/trim, rearrange | High | Timeline + preview/render resolution |
| P1 | Setup/repair center | High | Bootstrap completion |
| P2 | Short loop previews | Medium/high | Preview pipeline |
| P2 | Scopes | Medium | Preview frames |
| P2 | Benchmark-derived ETA | Medium | Doctor/history data |
| P2 | Crop/reframe editor | Medium | Plan + preview overlay |
| P3 | Keyframes and variants | Specialist | Stable workspace model |

P0 means necessary for a credible GUI, not necessarily one monolithic release.

## 10. Testing and Verification Strategy

### 10.1 Engine

- Golden tests for inspect/plan JSON schemas.
- Recipe schema migration and unknown-field tests.
- Preview cache-key tests.
- CLI backward-compatibility tests for current render syntax.
- Exit code and error code tests.
- Batch partial-failure tests.
- Project/timeline schema migration, deterministic edit resolution, and
  immutable job-snapshot tests.
- Existing synthetic FFmpeg integration test extended to compare planned and
  actual output properties.

### 10.2 Rust

- Protocol parser coverage for additive and unknown events.
- Child stdout/stderr routing tests.
- Cooperative cancel then forced-termination tests.
- Atomic job-state persistence and crash-recovery tests.
- Workspace atomic-save/recovery, lock contention, traversal/path validation,
  managed-media move, and offline relink tests.
- Recent-project index tests for ordering, moved/missing folders, removal
  without deletion, and crash-safe reopen.
- Path validation and local preview asset tests.
- Bootstrap health/repair state tests.

### 10.3 Frontend

- Reducer tests for every job transition.
- Recipe form round-trip tests.
- Dependency/visibility tests, such as HDR gain hidden or disabled in SDR.
- Preview stale/cache state tests.
- Queue reorder and restart reconciliation tests.
- Media-bin persistence plus timeline detach, split, trim, delete, snapping,
  rearrangement, linking, and undo/redo tests.
- Project chooser modal tests for default launch, keyboard operation, recent
  selection, missing-folder recovery, and no-project action gating.
- Keyboard navigation and automated accessibility checks.
- Visual regression screenshots at minimum, default, and wide window sizes.

### 10.4 End-to-end stories

Automate or manually certify:

1. Clean first launch -> setup -> import -> preview -> render -> open output.
2. Import HDR, SDR, portrait, silent, and variable-frame-rate examples.
3. Cancel during extraction/upscale/encode -> restart -> resume.
4. Queue three jobs where the middle job fails.
5. Load an older recipe and save it in the current schema.
6. Run with unavailable QSV and recover to x265.
7. Run out of planned scratch space before, not halfway through, a render.
8. Use the entire primary flow with keyboard only.
9. Create a project, import linked video and managed MP3 audio, detach source
   audio, cut/rearrange clips, render, restart, and reopen with state intact.
10. Move a managed-media project, relink one missing external asset, and verify
    that an already queued job still uses its immutable timeline snapshot.

## 11. Product Metrics

Collect locally by default; any transmitted telemetry requires explicit future
consent.

Useful measures:

- Time from launch to valid import.
- Time from import to first preview.
- Preview cache hit rate.
- Preflight warnings resolved before render.
- Render completion, cancellation, resume, and failure rates by stable code.
- Median error recovery time.
- Percentage of jobs using simple versus expert controls.
- Queue restart recovery success.
- Difference between estimated and actual duration.

The quality target is fewer surprising failed renders, not merely more settings
used.

## 12. Risks and Guardrails

### Scope creep into a full editor

Guardrail: auvide enhances and exports clips. Unbounded track layouts,
transitions, titles, effect automation, nested timelines, and advanced audio
mixing are out of scope. The supported preparation editor is limited to media
import, basic video/audio tracks, detach, split/trim, delete, and rearrangement.

### Project portability and corruption

Guardrail: versioned manifests, atomic saves, recovery copies, explicit
linked-versus-managed media, fingerprints/relinking, and startup reconciliation.

### Preview/render mismatch

Guardrail: previews and renders consume the same versioned recipe and engine
filter builders. Approximate previews are labeled.

### Schema drift

Guardrail: engine-owned schema, generated or validated TypeScript contracts,
and CI round-trip tests.

### GPU and disk failures

Guardrail: capability discovery, preflight estimates, conservative defaults,
cooperative cancellation, and resumable checkpoints.

### UI overload

Guardrail: simple presets, progressive disclosure, setting summaries, and a
single obvious next action.

### Platform-specific process behavior

Guardrail: test cancellation/process-tree cleanup on Windows, macOS, and Linux;
do not treat PID termination alone as a complete job model.

### HDR expectation mismatch

Guardrail: explain SDR-to-HDR remapping, monitor limitations, and display-mapped
previews in context.

## 13. Suggested First Implementation Slices

Canonical leaf definitions and file boundaries are in Sections 7–8 of
`docs/MASTERPLAN_IMPLEMENTATION.md`. Recommended feature order:

1. **Typed render events** — P3F.2 connects engine progress, the Rust parser,
   and the existing frontend reducer.
2. **Cooperative desktop cancellation** — P3H.2 adds per-job cancel marker,
   grace period, terminal mapping, and resumable UX state.
3. **Parallel contract foundations** — C2.1 media, C3.1 recipe envelope, C5.1
   preview cache key, and X1.1 design tokens can proceed independently.
4. **Media inspection vertical** — C2.2–C2.4, DQ.1–DQ.2, X2.1–X2.3.
5. **Recipe/schema vertical** — C3.2–C3.5, X3.1–X3.7.
6. **Application shell** — X1.2–X1.4 before multiple agents add feature views.
7. **Plan/preflight vertical** — C4, C6, X5.
8. **Frame preview vertical** — C5.2–C5.5, D5, X4.1–X4.4.
9. **Durable single job** — D3 plus restart reconciliation.
10. **Project workspace vertical** — C10 project/timeline schemas, D8
    create/open/save/relink, and X9 project browser/media bin.
11. **Basic editing vertical** — timeline preview/render resolution plus
    detach, split/trim, delete, and rearrangement with undo/redo.
12. **Queue/history vertical** — C7/C9, D4/D6, X6/X7.

Avoid combining steps 1–2 with a framework migration or visual redesign.
Contract producers, bridges, reducers, and views are separate leaf packets so
small agents can work in parallel without designing one another's layers.

## 14. Definition of “GUI Elevated to the Next Level”

The objective is met when a first-time user can:

- Install or repair all required components inside the app.
- Drag in one or more videos and understand their source properties.
- Create or open a project folder and recover its media, settings, edits,
  conversion status, and history after restart.
- Start in a clear New Project/Open Folder modal and reopen a recent workspace
  from the list at its side.
- Add MP3 audio, detach a video's audio, cut/trim clips, and rearrange audio and
  video non-destructively.
- Choose a good result using plain-language presets.
- Inspect a representative real AI before/after preview.
- Refine every supported recipe setting without using the terminal.
- See exact output consequences, warnings, disk needs, and a useful time range
  before starting.
- Queue work, close/reopen the app, cancel safely, resume, and recover failures.
- Find completed outputs and reproduce their settings later.

At the same time, a power user can:

- Produce the same job through a documented CLI.
- Inspect, plan, preview, render, batch, and diagnose with versioned JSON.
- Save a portable recipe and know how compatibility is handled.
- Consume stable progress and error events without parsing human logs.

That combination—visual confidence for new users and reproducible contracts for
power users—is the right definition of a next-level auvide GUI.
