import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { open, save } from "@tauri-apps/plugin-dialog";

// --- types -----------------------------------------------------------------
// Mirrors engine/src/auvide/recipe.py's Recipe dataclass field-for-field (as
// emitted by `auvide --dump-config`). Keep in sync by hand when recipe.py's
// fields change — it's a small, stable, flat shape.
interface GradeKnobs {
  saturation: number;
  vibrance: number;
  contrast: number;
  gamma: number;
  warmth: number;
  sharpen: number;
  exposure: number;
  tint: number;
  [key: string]: number; // grade_knobs is data-driven from Config, not a fixed union
}

interface Recipe {
  scale: number;
  model: string;
  hdr: "on" | "off";
  encoder: "x265" | "qsv";
  crf: number;
  preset: string;
  hdr_gain: number;
  grade: GradeKnobs;
  trim_start: number;
  trim_dur: number;
  audio: boolean;
  interpolate: number;
  slowmo: boolean;
  deinterlace: boolean;
  denoise: "off" | "light" | "medium" | "strong";
  stabilize: boolean;
  lut: string;
  target: string;
  curve: string;
}

interface Config {
  styles: Record<string, Recipe>;
  targets: string[];
  grade_knobs: string[];
  models: string[];
}

const GRADE_META: Record<string, [number, number, string]> = {
  exposure: [-1, 1, "Exposure"], saturation: [0.5, 2, "Saturation"],
  vibrance: [0, 1, "Vibrance"], contrast: [0, 1, "Contrast"],
  gamma: [0.8, 1.3, "Midtones"], warmth: [-1, 1, "Warmth"],
  tint: [-1, 1, "Tint"], sharpen: [0, 1.5, "Sharpen"],
};

let cfg: Config;
let recipe: Recipe;
const $ = (id: string) => document.getElementById(id)!;
const CHUNK_RE = /chunk\s+(\d+)\/(\d+)/;

// --- curves editor ---------------------------------------------------------
class Curves {
  pts: [number, number][] = [[0, 0], [1, 1]]; // normalized, y-up
  drag = -1;
  constructor(private cv: HTMLCanvasElement, private onChange: () => void) {
    cv.addEventListener("mousedown", (e) => this.down(e));
    cv.addEventListener("mousemove", (e) => this.move(e));
    window.addEventListener("mouseup", () => (this.drag = -1));
    this.draw();
  }
  private xy(e: MouseEvent): [number, number] {
    const r = this.cv.getBoundingClientRect();
    return [(e.clientX - r.left) / r.width, 1 - (e.clientY - r.top) / r.height];
  }
  private down(e: MouseEvent) {
    const [x, y] = this.xy(e);
    const hit = this.pts.findIndex((p) => Math.hypot(p[0] - x, p[1] - y) < 0.05);
    if (hit >= 0) { this.drag = hit; return; }
    this.pts.push([x, y]); this.pts.sort((a, b) => a[0] - b[0]);
    this.drag = this.pts.findIndex((p) => p[0] === x);
    this.draw(); this.onChange();
  }
  private move(e: MouseEvent) {
    if (this.drag < 0) return;
    let [x, y] = this.xy(e);
    x = Math.max(0, Math.min(1, x)); y = Math.max(0, Math.min(1, y));
    const first = this.drag === 0, last = this.drag === this.pts.length - 1;
    if (first) x = 0; if (last) x = 1;               // pin ends horizontally
    this.pts[this.drag] = [x, y];
    this.pts.sort((a, b) => a[0] - b[0]);
    this.drag = this.pts.findIndex((p) => p[0] === x && p[1] === y);
    this.draw(); this.onChange();
  }
  reset() { this.pts = [[0, 0], [1, 1]]; this.draw(); this.onChange(); }
  isIdentity() { return this.pts.length === 2 && this.pts[0][1] === 0 && this.pts[1][1] === 1; }
  points() { return this.pts.map(([x, y]) => `${x.toFixed(3)}/${y.toFixed(3)}`).join(" "); }
  private draw() {
    const c = this.cv.getContext("2d")!, w = this.cv.width, h = this.cv.height;
    c.clearRect(0, 0, w, h);
    c.strokeStyle = "#2a2d3a"; c.lineWidth = 1;
    for (let i = 1; i < 4; i++) {
      c.beginPath(); c.moveTo((i / 4) * w, 0); c.lineTo((i / 4) * w, h); c.stroke();
      c.beginPath(); c.moveTo(0, (i / 4) * h); c.lineTo(w, (i / 4) * h); c.stroke();
    }
    c.strokeStyle = "#6c8cff"; c.lineWidth = 2; c.beginPath();
    this.pts.forEach(([x, y], i) => {
      const px = x * w, py = (1 - y) * h;
      i ? c.lineTo(px, py) : c.moveTo(px, py);
    });
    c.stroke();
    c.fillStyle = "#8aa2ff";
    this.pts.forEach(([x, y]) => {
      c.beginPath(); c.arc(x * w, (1 - y) * h, 4, 0, 7); c.fill();
    });
  }
}
let curves: Curves;

// --- recipe <-> UI ---------------------------------------------------------
function applyRecipeToUI(r: Recipe) {
  recipe = structuredClone(r);
  (($("scale") as HTMLSelectElement).value = String(r.scale));
  (($("model") as HTMLSelectElement).value = r.model);
  (($("hdr") as HTMLSelectElement).value = r.hdr);
  (($("interp") as HTMLSelectElement).value = String(r.interpolate || 0));
  (($("target") as HTMLSelectElement).value = r.target || "source");
  (($("denoise") as HTMLSelectElement).value = r.denoise || "off");
  for (const k of cfg.grade_knobs) {
    const el = document.getElementById(`g-${k}`) as HTMLInputElement | null;
    if (el && r.grade[k] !== undefined) { el.value = String(r.grade[k]); el.dispatchEvent(new Event("input")); }
  }
  refreshPipeline();
}

function collectRecipe(): Recipe {
  const r = structuredClone(recipe);
  r.scale = +($("scale") as HTMLSelectElement).value;
  r.model = ($("model") as HTMLSelectElement).value;
  r.hdr = ($("hdr") as HTMLSelectElement).value as Recipe["hdr"]; // <select> options are exactly "on"/"off", see index.html
  r.interpolate = +($("interp") as HTMLSelectElement).value;
  r.target = ($("target") as HTMLSelectElement).value;
  r.denoise = ($("denoise") as HTMLSelectElement).value as Recipe["denoise"]; // <select> options match Recipe["denoise"] exactly, see index.html
  r.grade = Object.fromEntries(
    cfg.grade_knobs.map((k) => [k, +(document.getElementById(`g-${k}`) as HTMLInputElement).value]),
  ) as GradeKnobs;
  r.curve = curves.isIdentity() ? "" : curves.points();
  return r;
}

function refreshPipeline() {
  const r = collectRecipe();
  const parts: string[] = [];
  const rest: string[] = [];
  if (r.deinterlace) rest.push("deint");
  if (r.denoise !== "off") rest.push(`denoise:${r.denoise}`);
  if (r.stabilize) rest.push("stabilize");
  if (rest.length) parts.push(`restore(${rest.join("+")})`);
  parts.push(`upscale ${r.scale}× ${r.model}`);
  if (r.interpolate) parts.push(`interp ${r.interpolate}×`);
  parts.push(`grade ${r.hdr === "on" ? "HDR10" : "SDR"}`);
  if (r.curve) parts.push("curve");
  if (r.lut) parts.push("LUT");
  if (r.target !== "source") parts.push(`deliver ${r.target}`);
  $("pipeline").textContent = "Pipeline:   " + parts.join("   →   ");
}

// --- build the dynamic UI --------------------------------------------------
function buildSliders() {
  const box = $("sliders");
  for (const k of cfg.grade_knobs) {
    const [lo, hi, label] = GRADE_META[k] || [0, 1, k];
    const row = document.createElement("div");
    row.className = "slider";
    row.innerHTML = `<label>${label}</label>
      <input id="g-${k}" type="range" min="${lo}" max="${hi}" step="0.01" />
      <span class="val" id="v-${k}"></span>`;
    box.appendChild(row);
    const inp = row.querySelector("input")!;
    const val = row.querySelector(".val")!;
    inp.addEventListener("input", () => { val.textContent = Number(inp.value).toFixed(2); refreshPipeline(); });
  }
}

function buildStyleChips() {
  const box = $("styles");
  box.innerHTML = `<span class="lab">Styles</span>`;
  for (const name of Object.keys(cfg.styles)) {
    const b = document.createElement("button");
    b.className = "chip"; b.textContent = name;
    b.onclick = () => applyRecipeToUI(cfg.styles[name]);
    box.appendChild(b);
  }
}

// --- run -------------------------------------------------------------------
async function start() {
  const input = ($("input") as HTMLInputElement).value.trim();
  const output = ($("output") as HTMLInputElement).value.trim();
  if (!input) { setStatus("Pick an input video first.", "err"); return; }
  if (!output) { setStatus("Set an output path.", "err"); return; }
  ($("start") as HTMLButtonElement).disabled = true;
  ($("cancel") as HTMLButtonElement).disabled = false;
  ($("fill") as HTMLElement).style.width = "0";
  $("log").textContent = "";
  setStatus("Starting…");
  try {
    await invoke("run_render", { input, output, recipe: collectRecipe() });
  } catch (e) {
    setStatus(String(e), "err");
    ($("start") as HTMLButtonElement).disabled = false;
    ($("cancel") as HTMLButtonElement).disabled = true;
  }
}

function setStatus(t: string, kind: "" | "ok" | "err" = "") {
  const el = $("status"); el.textContent = t; el.className = "status " + kind;
}

async function init() {
  cfg = await invoke<Config>("config");
  ($("model") as HTMLSelectElement).innerHTML =
    cfg.models.map((m) => `<option>${m}</option>`).join("");
  ($("target") as HTMLSelectElement).innerHTML =
    cfg.targets.map((t) => `<option>${t}</option>`).join("");
  buildSliders();
  buildStyleChips();
  curves = new Curves($("curve") as HTMLCanvasElement, refreshPipeline);
  applyRecipeToUI(cfg.styles["Vibrant HDR"]);

  $("pick-input").onclick = async () => {
    const f = await open({ filters: [{ name: "Video", extensions: ["mp4", "mkv", "mov", "avi", "webm", "m4v"] }] });
    if (typeof f === "string") {
      ($("input") as HTMLInputElement).value = f;
      const out = f.replace(/\.[^.]+$/, "") + "_auvide.mp4";
      ($("output") as HTMLInputElement).value = out;
    }
  };
  $("pick-output").onclick = async () => {
    const f = await save({ defaultPath: "output.mp4", filters: [{ name: "Video", extensions: ["mp4"] }] });
    if (f) ($("output") as HTMLInputElement).value = f;
  };
  $("curve-reset").onclick = () => curves.reset();
  $("start").onclick = start;
  $("cancel").onclick = () => invoke("cancel_render");
  for (const id of ["scale", "model", "hdr", "interp", "target", "denoise"])
    $(id).addEventListener("change", refreshPipeline);

  await listen<string>("render:log", (e) => {
    const log = $("log"); log.textContent += e.payload + "\n"; log.scrollTop = log.scrollHeight;
    const m = CHUNK_RE.exec(e.payload);
    if (m) {
      const pct = Math.round((+m[1] / +m[2]) * 100);
      ($("fill") as HTMLElement).style.width = pct + "%";
      setStatus(`Rendering — chunk ${m[1]}/${m[2]}`);
    } else if (e.payload.includes("[1/3]")) setStatus("Extracting frames…");
    else if (e.payload.includes("[3/3]")) setStatus("Muxing…");
  });
  await listen<number>("render:done", (e) => {
    ($("start") as HTMLButtonElement).disabled = false;
    ($("cancel") as HTMLButtonElement).disabled = true;
    if (e.payload === 0) { ($("fill") as HTMLElement).style.width = "100%"; setStatus("Done ✔", "ok"); }
    else setStatus(`Failed (exit ${e.payload}) — see log`, "err");
  });
  setStatus("Ready.");
}

window.addEventListener("DOMContentLoaded", () => { init().catch((e) => setStatus(String(e), "err")); });
