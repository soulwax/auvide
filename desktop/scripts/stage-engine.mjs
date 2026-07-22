#!/usr/bin/env node
// Stages the auvide engine package (../engine) into src-tauri/engine/ so Tauri
// can ship it as a bundled resource and the dev build can find it beside the
// crate. This is a *copy*, not a second source: ../engine/src/auvide/ is the
// only place engine source is edited — run this script (or `bun run dev` /
// `bun run tauri build`, which do it automatically) after changing it.
import { cpSync, rmSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const src = path.resolve(here, "..", "..", "engine");
const dest = path.resolve(here, "..", "src-tauri", "engine");

if (!existsSync(path.join(src, "pyproject.toml"))) {
  console.error(`[stage-engine] engine package not found at ${src}`);
  process.exit(1);
}

rmSync(dest, { recursive: true, force: true });
cpSync(src, dest, {
  recursive: true,
  filter: (p) => !/(__pycache__|\.egg-info|\.pytest_cache|\.mypy_cache|\.ruff_cache|[\\/]tests[\\/])/.test(p),
});
console.log(`[stage-engine] ${src} -> ${dest}`);
