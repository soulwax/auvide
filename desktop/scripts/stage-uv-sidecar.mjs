#!/usr/bin/env node
// Download a reviewed uv release, verify its archive hash, and stage the
// target-named executable required by Tauri's `externalBin` convention.
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { mkdtempSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const desktopRoot = path.resolve(here, "..");
const manifestPath = path.join(desktopRoot, "resources", "uv-sidecar-manifest.json");
const outputDir = path.join(desktopRoot, "src-tauri", "binaries");
const targetKey = `${process.platform}-${process.arch}`;
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
const target = manifest.targets[targetKey];

if (!target) {
  console.error(`[stage-uv-sidecar] unsupported host target: ${targetKey}`);
  process.exit(1);
}
if (!target.url.startsWith("https://") || !/^[a-f0-9]{64}$/.test(target.sha256)) {
  console.error("[stage-uv-sidecar] manifest contains an invalid URL or SHA256");
  process.exit(1);
}

const suffix = process.platform === "win32" ? ".exe" : "";
const sidecarPath = path.join(outputDir, `uv-${target.tauri_target}${suffix}`);
const markerPath = `${sidecarPath}.json`;
const marker = JSON.stringify({ version: manifest.version, sha256: target.sha256 });

if (existsSync(sidecarPath) && existsSync(markerPath) && readFileSync(markerPath, "utf8") === marker) {
  console.log(`[stage-uv-sidecar] verified sidecar already staged: ${sidecarPath}`);
  process.exit(0);
}

const temporary = mkdtempSync(path.join(os.tmpdir(), "auvide-uv-"));
try {
  const archivePath = path.join(temporary, target.archive);
  const response = await fetch(target.url);
  if (!response.ok) throw new Error(`download failed with HTTP ${response.status}`);
  if (new URL(response.url).protocol !== "https:") {
    throw new Error(`download redirected to an unsafe URL: ${response.url}`);
  }
  const archive = Buffer.from(await response.arrayBuffer());
  const actualHash = createHash("sha256").update(archive).digest("hex");
  if (actualHash !== target.sha256) {
    throw new Error(`SHA256 mismatch: expected ${target.sha256}, got ${actualHash}`);
  }
  writeFileSync(archivePath, archive);

  const extractDir = path.join(temporary, "extract");
  mkdirSync(extractDir);
  const extraction = spawnSync("tar", ["-xf", archivePath, "-C", extractDir], { encoding: "utf8" });
  if (extraction.status !== 0) {
    throw new Error(`archive extraction failed: ${extraction.stderr || extraction.error?.message}`);
  }

  const executablePath = findExecutable(extractDir, target.executable);
  if (!executablePath) throw new Error(`archive does not contain ${target.executable}`);
  mkdirSync(outputDir, { recursive: true });
  const stagedPath = `${sidecarPath}.new-${process.pid}`;
  cpSync(executablePath, stagedPath);
  if (process.platform !== "win32") spawnSync("chmod", ["755", stagedPath]);
  renameSync(stagedPath, sidecarPath);
  writeFileSync(markerPath, marker);
  console.log(`[stage-uv-sidecar] staged uv ${manifest.version} for ${target.tauri_target}`);
} finally {
  rmSync(temporary, { recursive: true, force: true });
}

function findExecutable(root, expectedName) {
  const entries = [root];
  while (entries.length) {
    const current = entries.pop();
    for (const entry of readDir(current)) {
      const candidate = path.join(current, entry.name);
      if (entry.isDirectory()) entries.push(candidate);
      else if (entry.isFile() && entry.name === expectedName) return candidate;
    }
  }
  return null;
}

function readDir(directory) {
  return readdirSync(directory, { withFileTypes: true });
}
