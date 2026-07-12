#!/usr/bin/env python3
"""auvide GUI - a desktop front-end over upscale_hdr.py.

The CLI stays the engine: this window collects options, launches
`python upscale_hdr.py ...` as a subprocess, streams its output into a log,
and turns the "chunk k/N" progress lines into a progress bar. It also probes
the chosen file (via bundled ffprobe) to show source/target resolution and a
rough time estimate.

Run:  uv run --python 3.12 gui.py       (or double-click run-gui.bat)
"""
from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

HERE = Path(__file__).resolve().parent
CLI = HERE / "upscale_hdr.py"
FFPROBE = HERE / "bin" / "ffprobe.exe"
CONFIG = Path(os.environ.get("LOCALAPPDATA", HERE)) / "auvide" / "gui.json"

SCALES = ["2", "3", "4"]
MODELS = ["animevideo", "x4plus", "x4plus-anime"]
VIBRANCE = ["none", "subtle", "vibrant", "max"]
HDR = ["on", "off"]
ENCODERS = ["x265", "qsv"]
VIDEO_TYPES = [("Video files", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v"), ("All files", "*.*")]

MODEL_HELP = {
    "animevideo": "Fast, denoises — best for real video footage.",
    "x4plus": "Sharper photographic detail. 4× native, slower, more VRAM.",
    "x4plus-anime": "Tuned for illustration / anime line art.",
}
VIB_HELP = {
    "none": "No color change — pure upscale + HDR container.",
    "subtle": "Gentle lift, stays close to the original grade.",
    "vibrant": "Balanced saturation + contrast punch (recommended).",
    "max": "Aggressive saturation and highlight expansion.",
}

CHUNK_RE = re.compile(r"chunk\s+(\d+)/(\d+)")
ETA_RE = re.compile(r"ETA\s+(\S+)")
FPS_RE = re.compile(r"([\d.]+)\s*fps")
DONE_RE = re.compile(r"done\s+->")
NOWINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# ---- palette (dark) -----------------------------------------------------
BG = "#14151b"
PANEL = "#1d1f28"
FIELD = "#2a2d3a"
LINE = "#33364a"
TEXT = "#e7e8f0"
MUTED = "#8b8fa6"
ACCENT = "#6c8cff"
ACCENT_HI = "#8aa2ff"
OK = "#5ec98a"
ERR = "#e06c75"
FONT = ("Segoe UI", 10)
FONT_SM = ("Segoe UI", 9)
FONT_H = ("Segoe UI Semibold", 17)
FONT_MONO = ("Consolas", 9)


def apply_theme(root: tk.Tk):
    root.configure(bg=BG)
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=PANEL, foreground=TEXT, font=FONT,
                fieldbackground=FIELD, bordercolor=LINE, lightcolor=PANEL, darkcolor=PANEL)
    s.configure("TFrame", background=PANEL)
    s.configure("Bg.TFrame", background=BG)
    s.configure("TLabel", background=PANEL, foreground=TEXT)
    s.configure("Bg.TLabel", background=BG, foreground=TEXT)
    s.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=FONT_SM)
    s.configure("MutedBg.TLabel", background=BG, foreground=MUTED, font=FONT_SM)
    s.configure("Head.TLabel", background=BG, foreground=TEXT, font=FONT_H)
    s.configure("Info.TLabel", background=FIELD, foreground=TEXT, font=FONT_SM)
    s.configure("OK.TLabel", background=PANEL, foreground=OK)
    s.configure("Err.TLabel", background=PANEL, foreground=ERR)
    s.configure("TLabelframe", background=PANEL, bordercolor=LINE, relief="solid", borderwidth=1)
    s.configure("TLabelframe.Label", background=PANEL, foreground=ACCENT_HI, font=FONT_SM)
    s.configure("TButton", background=FIELD, foreground=TEXT, bordercolor=LINE,
                focuscolor=PANEL, padding=(10, 5))
    s.map("TButton", background=[("active", LINE), ("disabled", PANEL)],
          foreground=[("disabled", MUTED)])
    s.configure("Accent.TButton", background=ACCENT, foreground="#0f1016",
                font=("Segoe UI Semibold", 10), padding=(16, 6))
    s.map("Accent.TButton", background=[("active", ACCENT_HI), ("disabled", LINE)],
          foreground=[("disabled", MUTED)])
    s.configure("Chip.TButton", background=PANEL, foreground=MUTED, bordercolor=LINE,
                padding=(9, 3), font=FONT_SM)
    s.map("Chip.TButton", background=[("active", FIELD)], foreground=[("active", TEXT)])
    s.configure("TCombobox", fieldbackground=FIELD, background=FIELD, foreground=TEXT,
                arrowcolor=TEXT, bordercolor=LINE, padding=3)
    s.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", TEXT)],
          selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", TEXT)])
    s.configure("TSpinbox", fieldbackground=FIELD, background=FIELD, foreground=TEXT,
                arrowcolor=TEXT, bordercolor=LINE, padding=3)
    s.configure("TCheckbutton", background=PANEL, foreground=TEXT, focuscolor=PANEL)
    s.map("TCheckbutton", background=[("active", PANEL)],
          indicatorcolor=[("selected", ACCENT), ("!selected", FIELD)])
    s.configure("TEntry", fieldbackground=FIELD, foreground=TEXT, bordercolor=LINE, padding=4)
    s.configure("Accent.Horizontal.TProgressbar", background=ACCENT, troughcolor=FIELD,
                bordercolor=LINE, lightcolor=ACCENT, darkcolor=ACCENT)
    s.configure("Horizontal.TScale", background=PANEL, troughcolor=FIELD)
    # combobox dropdown list colors
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", "#0f1016")
    root.option_add("*TCombobox*Listbox.font", FONT_SM)


class Tooltip:
    def __init__(self, widget, text):
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, background="#0c0d12", foreground=TEXT,
                 font=FONT_SM, justify="left", padx=8, pady=4,
                 highlightbackground=LINE, highlightthickness=1).pack()

    def _hide(self, _=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class App:
    def __init__(self, root: tk.Tk, self_test: bool = False):
        self.root = root
        self.proc: subprocess.Popen | None = None
        self.q: queue.Queue = queue.Queue()
        self.out_edited = False
        self.info: dict | None = None
        self.start_ts = 0.0
        self.cancelling = False
        root.title("auvide  ·  AI upscale + vibrant HDR10")
        root.minsize(760, 640)
        apply_theme(root)

        self._build_vars()
        self._build_ui()
        self._load_config()
        self._poll()
        self._tick_elapsed()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._center()

        if self_test:
            root.after(300, root.destroy)

    # ---- state ----------------------------------------------------------
    def _build_vars(self):
        self.v_in = tk.StringVar()
        self.v_out = tk.StringVar()
        self.v_scale = tk.StringVar(value="2")
        self.v_model = tk.StringVar(value="animevideo")
        self.v_vib = tk.StringVar(value="vibrant")
        self.v_hdr = tk.StringVar(value="on")
        self.v_enc = tk.StringVar(value="x265")
        self.v_crf = tk.IntVar(value=19)
        self.v_chunk = tk.IntVar(value=300)
        self.v_gpu = tk.IntVar(value=0)
        self.v_tile = tk.IntVar(value=0)
        self.v_resume = tk.BooleanVar(value=True)
        self.v_keep = tk.BooleanVar(value=False)
        self.v_status = tk.StringVar(value="Ready — choose a video to begin.")
        self.v_elapsed = tk.StringVar(value="")
        self.v_plan = tk.StringVar(value="No file selected.")
        self.v_modelhelp = tk.StringVar(value=MODEL_HELP["animevideo"])
        self.v_vibhelp = tk.StringVar(value=VIB_HELP["vibrant"])
        self.v_crflabel = tk.StringVar(value="19")
        self.v_in.trace_add("write", lambda *_: (self._suggest_output(), self._on_input_change()))
        self.v_scale.trace_add("write", lambda *_: (self._suggest_output(), self._refresh_plan()))
        self.v_hdr.trace_add("write", lambda *_: self._suggest_output())
        self.v_model.trace_add("write", lambda *_: (
            self.v_modelhelp.set(MODEL_HELP[self.v_model.get()]), self._refresh_plan()))
        self.v_vib.trace_add("write", lambda *_: self.v_vibhelp.set(VIB_HELP[self.v_vib.get()]))
        self.v_crf.trace_add("write", lambda *_: self.v_crflabel.set(str(self.v_crf.get())))

    # ---- layout ---------------------------------------------------------
    def _build_ui(self):
        root = self.root
        # header
        head = ttk.Frame(root, style="Bg.TFrame", padding=(18, 14, 18, 6))
        head.pack(fill="x")
        ttk.Label(head, text="auvide", style="Head.TLabel").pack(side="left")
        ttk.Label(head, text="AI upscale  →  vibrant HDR10", style="MutedBg.TLabel").pack(
            side="left", padx=12, pady=(8, 0))

        body = ttk.Frame(root, padding=(16, 8, 16, 12))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        pad = dict(padx=6, pady=5)

        # --- file row ---
        files = ttk.Frame(body)
        files.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        files.columnconfigure(1, weight=1)
        ttk.Label(files, text="Input").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(files, textvariable=self.v_in).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(files, text="Browse…", command=self._browse_in).grid(row=0, column=2, **pad)
        ttk.Label(files, text="Output").grid(row=1, column=0, sticky="w", **pad)
        e_out = ttk.Entry(files, textvariable=self.v_out)
        e_out.grid(row=1, column=1, sticky="ew", **pad)
        e_out.bind("<Key>", lambda *_: setattr(self, "out_edited", True))
        ttk.Button(files, text="Browse…", command=self._browse_out).grid(row=1, column=2, **pad)

        # --- media info strip ---
        info = ttk.Frame(body, style="TFrame")
        info.grid(row=1, column=0, sticky="ew", pady=(2, 8))
        strip = tk.Frame(info, background=FIELD, highlightbackground=LINE, highlightthickness=1)
        strip.pack(fill="x")
        ttk.Label(strip, textvariable=self.v_plan, style="Info.TLabel",
                  background=FIELD, padding=(10, 7)).pack(side="left")

        # --- presets ---
        pre = ttk.Frame(body)
        pre.grid(row=2, column=0, sticky="w", pady=(0, 4))
        ttk.Label(pre, text="Presets", style="Muted.TLabel").pack(side="left", padx=(6, 8))
        for name, cfg in (
            ("Vibrant 2× HDR", dict(scale="2", model="animevideo", vib="vibrant", hdr="on")),
            ("Cinematic", dict(scale="2", model="animevideo", vib="subtle", hdr="on")),
            ("Max punch", dict(scale="2", model="animevideo", vib="max", hdr="on")),
            ("Sharp photo 2×", dict(scale="2", model="x4plus", vib="vibrant", hdr="on")),
            ("SDR upscale", dict(scale="2", model="animevideo", vib="subtle", hdr="off")),
        ):
            ttk.Button(pre, text=name, style="Chip.TButton",
                       command=lambda c=cfg: self._apply_preset(c)).pack(side="left", padx=3)

        # --- options ---
        opt = ttk.LabelFrame(body, text="Options", padding=(10, 6))
        opt.grid(row=3, column=0, sticky="ew", pady=4)
        for c in (1, 3):
            opt.columnconfigure(c, weight=1)

        def combo(r, c, label, var, values, tip=""):
            ttk.Label(opt, text=label).grid(row=r, column=c * 2, sticky="w", padx=6, pady=5)
            cb = ttk.Combobox(opt, textvariable=var, values=values, state="readonly", width=13)
            cb.grid(row=r, column=c * 2 + 1, sticky="ew", padx=6, pady=5)
            if tip:
                Tooltip(cb, tip)
            return cb

        combo(0, 0, "Scale", self.v_scale, SCALES, "Upscale factor (2× recommended).")
        combo(0, 1, "Model", self.v_model, MODELS)
        ttk.Label(opt, textvariable=self.v_modelhelp, style="Muted.TLabel").grid(
            row=1, column=0, columnspan=4, sticky="w", padx=6)
        combo(2, 0, "Vibrance", self.v_vib, VIBRANCE)
        combo(2, 1, "HDR", self.v_hdr, HDR, "HDR10 remap (on) or stay SDR BT.709 (off).")
        ttk.Label(opt, textvariable=self.v_vibhelp, style="Muted.TLabel").grid(
            row=3, column=0, columnspan=4, sticky="w", padx=6)

        combo(4, 0, "Encoder", self.v_enc, ENCODERS,
              "x265 = software (best HDR fidelity). qsv = Intel GPU (faster).")
        # CRF slider
        ttk.Label(opt, text="Quality (CRF)").grid(row=4, column=2, sticky="w", padx=6, pady=5)
        crf = ttk.Frame(opt)
        crf.grid(row=4, column=3, sticky="ew", padx=6, pady=5)
        crf.columnconfigure(0, weight=1)
        ttk.Scale(crf, from_=12, to=30, orient="horizontal", variable=self.v_crf,
                  command=lambda v: self.v_crf.set(round(float(v)))).grid(row=0, column=0, sticky="ew")
        ttk.Label(crf, textvariable=self.v_crflabel, style="Muted.TLabel", width=3).grid(
            row=0, column=1, padx=(6, 0))

        # numeric row
        num = ttk.Frame(opt)
        num.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(6, 2))
        def spin(label, var, lo, hi, step=1, tip=""):
            f = ttk.Frame(num)
            f.pack(side="left", padx=(6, 14))
            ttk.Label(f, text=label, style="Muted.TLabel").pack(side="left", padx=(0, 5))
            sp = ttk.Spinbox(f, from_=lo, to=hi, increment=step, textvariable=var, width=6)
            sp.pack(side="left")
            if tip:
                Tooltip(sp, tip)
        spin("Chunk", self.v_chunk, 30, 4000, 30, "Frames per encode chunk. Bounds disk use.")
        spin("GPU id", self.v_gpu, -1, 8, 1, "Real-ESRGAN GPU (-1 = CPU).")
        spin("Tile", self.v_tile, 0, 1024, 32, "0 = auto. Lower it if you hit VRAM OOM.")
        ttk.Checkbutton(num, text="Resume", variable=self.v_resume).pack(side="left", padx=8)
        ttk.Checkbutton(num, text="Keep scratch", variable=self.v_keep).pack(side="left", padx=8)

        # --- actions ---
        bar = ttk.Frame(body)
        bar.grid(row=4, column=0, sticky="ew", pady=(8, 4))
        self.btn_start = ttk.Button(bar, text="▶  Start", style="Accent.TButton", command=self._start)
        self.btn_start.pack(side="left")
        self.btn_cancel = ttk.Button(bar, text="Cancel", command=self._cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=6)
        ttk.Button(bar, text="Show command", command=self._show_cmd).pack(side="left", padx=6)
        self.btn_open = ttk.Button(bar, text="Open folder", command=self._open_out, state="disabled")
        self.btn_open.pack(side="left", padx=6)
        ttk.Label(bar, textvariable=self.v_elapsed, style="Muted.TLabel").pack(side="right", padx=6)

        # --- progress + status ---
        self.pbar = ttk.Progressbar(body, mode="determinate", maximum=100,
                                    style="Accent.Horizontal.TProgressbar")
        self.pbar.grid(row=5, column=0, sticky="ew", pady=(4, 3))
        self.lbl_status = ttk.Label(body, textvariable=self.v_status, style="Muted.TLabel")
        self.lbl_status.grid(row=6, column=0, sticky="w", padx=6)

        # --- log ---
        logf = ttk.LabelFrame(body, text="Log", padding=4)
        logf.grid(row=7, column=0, sticky="nsew", pady=(6, 0))
        body.rowconfigure(7, weight=1)
        self.log = tk.Text(logf, height=11, wrap="none", state="disabled", font=FONT_MONO,
                           background="#0e0f14", foreground="#c8ccd8", insertbackground=TEXT,
                           relief="flat", borderwidth=0, highlightthickness=0)
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(logf, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=sb.set)
        self.log.tag_configure("err", foreground=ERR)
        self.log.tag_configure("ok", foreground=OK)
        self.log.tag_configure("cmd", foreground=MUTED)

    # ---- helpers --------------------------------------------------------
    def _center(self):
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = max(0, (self.root.winfo_screenheight() - h) // 3)
        self.root.geometry(f"+{x}+{y}")

    def _apply_preset(self, c):
        self.v_scale.set(c["scale"])
        self.v_model.set(c["model"])
        self.v_vib.set(c["vib"])
        self.v_hdr.set(c["hdr"])

    def _suggest_output(self):
        if self.out_edited:
            return
        src = self.v_in.get().strip()
        if not src:
            return
        p = Path(src)
        tag = "hdr" if self.v_hdr.get() == "on" else "sdr"
        self.v_out.set(str(p.with_name(f"{p.stem}_{self.v_scale.get()}x_{tag}.mp4")))

    def _browse_in(self):
        f = filedialog.askopenfilename(title="Choose a video", filetypes=VIDEO_TYPES)
        if f:
            self.out_edited = False
            self.v_in.set(f)

    def _browse_out(self):
        f = filedialog.asksaveasfilename(title="Save as", defaultextension=".mp4",
                                         filetypes=VIDEO_TYPES)
        if f:
            self.out_edited = True
            self.v_out.set(f)

    def _on_input_change(self):
        p = self.v_in.get().strip()
        if p and Path(p).exists() and FFPROBE.exists():
            self.v_plan.set("Reading media…")
            threading.Thread(target=self._probe, args=(p,), daemon=True).start()
        else:
            self.info = None
            self.v_plan.set("No file selected." if not p else "File not found.")

    def _probe(self, path):
        try:
            out = subprocess.run(
                [str(FFPROBE), "-v", "error", "-select_streams", "v:0", "-show_entries",
                 "stream=width,height,r_frame_rate,nb_frames,duration",
                 "-of", "json", path],
                capture_output=True, text=True, creationflags=NOWINDOW, timeout=30)
            st = json.loads(out.stdout)["streams"][0]
            num, den = (st.get("r_frame_rate", "24/1").split("/") + ["1"])[:2]
            fps = int(num) / max(1, int(den or 1))
            nb = st.get("nb_frames")
            dur = float(st.get("duration") or 0)
            frames = int(nb) if (nb and nb.isdigit()) else int(dur * fps)
            self.q.put(("info", dict(w=int(st["width"]), h=int(st["height"]),
                                     fps=fps, frames=frames, dur=dur)))
        except Exception as e:
            self.q.put(("info", None))
            self.q.put(f"[probe] could not read media: {e}\n")

    def _refresh_plan(self):
        if not self.info:
            return
        w, h, fps, frames, dur = (self.info[k] for k in ("w", "h", "fps", "frames", "dur"))
        scale = int(self.v_scale.get())
        tw, th = w * scale, h * scale
        model = self.v_model.get()
        per = 5.6 if model != "animevideo" else 1.4 * (scale / 2) ** 2
        est = frames * per
        mm, ss = divmod(int(dur), 60)
        self.v_plan.set(
            f"Source {w}×{h} · {fps:.2f} fps · {mm}:{ss:02d} · {frames} frames"
            f"     →     Target {tw}×{th} · ~{self._hms(est)} to render")

    @staticmethod
    def _hms(sec):
        sec = int(sec)
        h, r = divmod(sec, 3600)
        m, s = divmod(r, 60)
        return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"

    def _build_command(self):
        cmd = [sys.executable, "-u", str(CLI), self.v_in.get(), "-o", self.v_out.get(),
               "--scale", self.v_scale.get(), "--model", self.v_model.get(),
               "--vibrance", self.v_vib.get(), "--hdr", self.v_hdr.get(),
               "--encoder", self.v_enc.get(), "--crf", str(self.v_crf.get()),
               "--chunk", str(self.v_chunk.get()), "--gpu", str(self.v_gpu.get())]
        if self.v_tile.get() > 0:
            cmd += ["--tile", str(self.v_tile.get())]
        if self.v_resume.get():
            cmd.append("--resume")
        if self.v_keep.get():
            cmd.append("--keep")
        return cmd

    def _show_cmd(self):
        if not self.v_in.get().strip():
            messagebox.showwarning("auvide", "Pick an input video first.")
            return
        pretty = " ".join(f'"{c}"' if " " in c else c for c in self._build_command())
        messagebox.showinfo("Equivalent command", pretty)

    def _append(self, text, tag=None):
        self.log.configure(state="normal")
        self.log.insert("end", text, tag or ())
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_status(self, text, kind="muted"):
        self.v_status.set(text)
        self.lbl_status.configure(style={"ok": "OK.TLabel", "err": "Err.TLabel"}.get(kind, "Muted.TLabel"))

    # ---- run / cancel ---------------------------------------------------
    def _start(self):
        if self.proc is not None:
            return
        if not self.v_in.get().strip() or not Path(self.v_in.get()).exists():
            messagebox.showerror("auvide", "Input video not found.")
            return
        if not CLI.exists():
            messagebox.showerror("auvide", f"Cannot find upscale_hdr.py at {CLI}")
            return
        cmd = self._build_command()
        self._append("$ " + " ".join(cmd) + "\n\n", "cmd")
        self.pbar.configure(value=0)
        self._set_status("Starting…")
        self.btn_start.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.btn_open.configure(state="disabled")
        self.start_ts = time.time()
        env = dict(os.environ, PYTHONUNBUFFERED="1")
        try:
            self.proc = subprocess.Popen(
                cmd, cwd=str(HERE), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=env, creationflags=NOWINDOW)
        except Exception as e:
            messagebox.showerror("auvide", f"Failed to launch:\n{e}")
            self._reset_buttons()
            return
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()

    def _reader(self, proc):
        for line in proc.stdout:
            self.q.put(line)
        proc.wait()
        self.q.put(("exit", proc.returncode))

    def _cancel(self):
        if self.proc and self.proc.poll() is None:
            self.cancelling = True
            self._set_status("Cancelling…")
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                                   creationflags=NOWINDOW, capture_output=True)
                else:
                    self.proc.terminate()
            except Exception:
                pass

    def _reset_buttons(self):
        self.btn_start.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        self.proc = None
        self.start_ts = 0.0

    def _open_out(self):
        out = Path(self.v_out.get())
        folder = out.parent if out.parent.exists() else HERE
        try:
            if sys.platform == "win32":
                os.startfile(str(folder))  # noqa: S606
            else:
                subprocess.run(["xdg-open", str(folder)])
        except Exception:
            pass

    # ---- pumps ----------------------------------------------------------
    def _tick_elapsed(self):
        if self.start_ts:
            self.v_elapsed.set("elapsed " + self._hms(time.time() - self.start_ts))
        self.root.after(1000, self._tick_elapsed)

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if isinstance(msg, tuple):
                    kind, payload = msg
                    if kind == "info":
                        self.info = payload
                        if payload:
                            self._refresh_plan()
                        elif self.v_in.get().strip():
                            self.v_plan.set("Could not read media info.")
                    elif kind == "exit":
                        self._on_exit(payload)
                    continue
                # log line
                low_tag = "err" if "[error]" in msg else ("ok" if DONE_RE.search(msg) else None)
                self._append(msg, low_tag)
                m = CHUNK_RE.search(msg)
                if m:
                    k, n = int(m.group(1)), int(m.group(2))
                    self.pbar.configure(value=max(1, round(k / n * 100)))
                    eta = ETA_RE.search(msg)
                    fps = FPS_RE.search(msg)
                    extra = []
                    if fps:
                        extra.append(f"{fps.group(1)} fps")
                    if eta:
                        extra.append(f"ETA {eta.group(1)}")
                    tail = ("  ·  " + "  ·  ".join(extra)) if extra else ""
                    self._set_status(f"Upscaling + encoding — chunk {k}/{n}{tail}")
                elif "[1/3]" in msg:
                    self._set_status("Extracting frames…")
                elif "[3/3]" in msg:
                    self._set_status("Concatenating + muxing audio…")
        except queue.Empty:
            pass
        self.root.after(120, self._poll)

    def _on_exit(self, code):
        if self.cancelling:
            self._set_status("Cancelled — re-run with Resume to continue.", "muted")
            self.pbar.configure(value=0)
        elif code == 0:
            self.pbar.configure(value=100)
            self._set_status("Done ✔  —  output ready", "ok")
            self.btn_open.configure(state="normal")
        else:
            self._set_status(f"Failed (exit {code}) — see log", "err")
        self.cancelling = False
        self._reset_buttons()

    # ---- config ---------------------------------------------------------
    def _load_config(self):
        try:
            d = json.loads(CONFIG.read_text())
            for k, var in self._cfg_map().items():
                if k in d:
                    var.set(d[k])
        except Exception:
            pass

    def _save_config(self):
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps({k: v.get() for k, v in self._cfg_map().items()}, indent=2))
        except Exception:
            pass

    def _cfg_map(self):
        return dict(scale=self.v_scale, model=self.v_model, vibrance=self.v_vib, hdr=self.v_hdr,
                    encoder=self.v_enc, crf=self.v_crf, chunk=self.v_chunk, gpu=self.v_gpu,
                    tile=self.v_tile, resume=self.v_resume, keep=self.v_keep)

    def _on_close(self):
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("auvide", "A render is running. Cancel and quit?"):
                return
            self._cancel()
        self._save_config()
        self.root.destroy()


def main():
    self_test = "--self-test" in sys.argv
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.25)
    except tk.TclError:
        pass
    App(root, self_test=self_test)
    root.mainloop()
    if self_test:
        print("self-test OK: GUI constructed and destroyed cleanly")


if __name__ == "__main__":
    main()
