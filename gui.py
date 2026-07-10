#!/usr/bin/env python3
"""auvide GUI - a thin desktop front-end over upscale_hdr.py.

The CLI stays the engine: this window just collects options, launches
`python upscale_hdr.py ...` as a subprocess, streams its output into a log,
and turns the "chunk k/N" progress lines into a progress bar.

Run:  uv run --python 3.12 gui.py       (or double-click run-gui.bat)
"""
from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

HERE = Path(__file__).resolve().parent
CLI = HERE / "upscale_hdr.py"

SCALES = ["2", "3", "4"]
MODELS = ["animevideo", "x4plus", "x4plus-anime"]
VIBRANCE = ["none", "subtle", "vibrant", "max"]
HDR = ["on", "off"]
ENCODERS = ["x265", "qsv"]

VIDEO_TYPES = [("Video files", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v"), ("All files", "*.*")]

CHUNK_RE = re.compile(r"chunk\s+(\d+)/(\d+)")
DONE_RE = re.compile(r"done\s+->")
NOWINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class App:
    def __init__(self, root: tk.Tk, self_test: bool = False):
        self.root = root
        self.proc: subprocess.Popen | None = None
        self.q: queue.Queue[str] = queue.Queue()
        self.out_edited = False
        root.title("auvide - AI upscale + vibrant HDR10")
        root.minsize(720, 560)

        self._build_vars()
        self._build_ui()
        self._poll()

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
        self.v_status = tk.StringVar(value="Ready.")
        for var in (self.v_in, self.v_scale, self.v_hdr):
            var.trace_add("write", lambda *_: self._suggest_output())

    # ---- layout ---------------------------------------------------------
    def _build_ui(self):
        pad = dict(padx=8, pady=4)
        frm = ttk.Frame(self.root, padding=10)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        # input / output
        ttk.Label(frm, text="Input video").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.v_in).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="Browse…", command=self._browse_in).grid(row=0, column=2, **pad)

        ttk.Label(frm, text="Output file").grid(row=1, column=0, sticky="w", **pad)
        e_out = ttk.Entry(frm, textvariable=self.v_out)
        e_out.grid(row=1, column=1, sticky="ew", **pad)
        e_out.bind("<Key>", lambda *_: setattr(self, "out_edited", True))
        ttk.Button(frm, text="Browse…", command=self._browse_out).grid(row=1, column=2, **pad)

        # options grid
        opt = ttk.LabelFrame(frm, text="Options", padding=8)
        opt.grid(row=2, column=0, columnspan=3, sticky="ew", **pad)
        for c in range(4):
            opt.columnconfigure(c, weight=1)

        def combo(parent, r, c, label, var, values):
            ttk.Label(parent, text=label).grid(row=r, column=c * 2, sticky="w", padx=6, pady=4)
            cb = ttk.Combobox(parent, textvariable=var, values=values, state="readonly", width=12)
            cb.grid(row=r, column=c * 2 + 1, sticky="ew", padx=6, pady=4)
            return cb

        combo(opt, 0, 0, "Scale", self.v_scale, SCALES)
        combo(opt, 0, 1, "Model", self.v_model, MODELS)
        combo(opt, 1, 0, "Vibrance", self.v_vib, VIBRANCE)
        combo(opt, 1, 1, "HDR", self.v_hdr, HDR)
        combo(opt, 2, 0, "Encoder", self.v_enc, ENCODERS)

        ttk.Label(opt, text="CRF (quality)").grid(row=2, column=2, sticky="w", padx=6, pady=4)
        ttk.Spinbox(opt, from_=12, to=30, textvariable=self.v_crf, width=6).grid(
            row=2, column=3, sticky="w", padx=6, pady=4)
        ttk.Label(opt, text="Chunk (frames)").grid(row=3, column=0, sticky="w", padx=6, pady=4)
        ttk.Spinbox(opt, from_=30, to=2000, increment=30, textvariable=self.v_chunk, width=6).grid(
            row=3, column=1, sticky="w", padx=6, pady=4)
        ttk.Label(opt, text="GPU id (-1=CPU)").grid(row=3, column=2, sticky="w", padx=6, pady=4)
        ttk.Spinbox(opt, from_=-1, to=8, textvariable=self.v_gpu, width=6).grid(
            row=3, column=3, sticky="w", padx=6, pady=4)
        ttk.Label(opt, text="Tile (0=auto)").grid(row=4, column=0, sticky="w", padx=6, pady=4)
        ttk.Spinbox(opt, from_=0, to=1024, increment=32, textvariable=self.v_tile, width=6).grid(
            row=4, column=1, sticky="w", padx=6, pady=4)
        ttk.Checkbutton(opt, text="Resume", variable=self.v_resume).grid(
            row=4, column=2, sticky="w", padx=6, pady=4)
        ttk.Checkbutton(opt, text="Keep scratch", variable=self.v_keep).grid(
            row=4, column=3, sticky="w", padx=6, pady=4)

        # action buttons
        bar = ttk.Frame(frm)
        bar.grid(row=3, column=0, columnspan=3, sticky="ew", **pad)
        self.btn_start = ttk.Button(bar, text="▶ Start", command=self._start)
        self.btn_start.pack(side="left")
        self.btn_cancel = ttk.Button(bar, text="■ Cancel", command=self._cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=6)
        ttk.Button(bar, text="Show command", command=self._show_cmd).pack(side="left", padx=6)
        self.btn_open = ttk.Button(bar, text="Open output folder", command=self._open_out,
                                   state="disabled")
        self.btn_open.pack(side="left", padx=6)

        # progress + status
        self.pbar = ttk.Progressbar(frm, mode="determinate", maximum=100)
        self.pbar.grid(row=4, column=0, columnspan=3, sticky="ew", **pad)
        ttk.Label(frm, textvariable=self.v_status).grid(
            row=5, column=0, columnspan=3, sticky="w", **pad)

        # log
        logf = ttk.LabelFrame(frm, text="Log", padding=4)
        logf.grid(row=6, column=0, columnspan=3, sticky="nsew", **pad)
        frm.rowconfigure(6, weight=1)
        self.log = tk.Text(logf, height=12, wrap="none", state="disabled",
                           background="#111", foreground="#ddd", insertbackground="#ddd")
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(logf, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=sb.set)

    # ---- helpers --------------------------------------------------------
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

    def _build_command(self) -> list[str]:
        cmd = [sys.executable, "-u", str(CLI), self.v_in.get(),
               "-o", self.v_out.get(),
               "--scale", self.v_scale.get(),
               "--model", self.v_model.get(),
               "--vibrance", self.v_vib.get(),
               "--hdr", self.v_hdr.get(),
               "--encoder", self.v_enc.get(),
               "--crf", str(self.v_crf.get()),
               "--chunk", str(self.v_chunk.get()),
               "--gpu", str(self.v_gpu.get())]
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

    def _append(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

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
        self._append("$ " + " ".join(cmd) + "\n\n")
        self.pbar.configure(value=0)
        self.v_status.set("Starting…")
        self.btn_start.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.btn_open.configure(state="disabled")
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

    def _reader(self, proc: subprocess.Popen):
        for line in proc.stdout:
            self.q.put(line)
        proc.wait()
        self.q.put(f"\x00EXIT:{proc.returncode}")

    def _cancel(self):
        if self.proc and self.proc.poll() is None:
            self.v_status.set("Cancelling…")
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

    def _open_out(self):
        out = Path(self.v_out.get())
        folder = out.parent if out.parent.exists() else HERE
        if sys.platform == "win32":
            os.startfile(str(folder))  # noqa: S606
        else:
            subprocess.run(["xdg-open", str(folder)])

    # ---- pump the queue on the UI thread --------------------------------
    def _poll(self):
        try:
            while True:
                line = self.q.get_nowait()
                if line.startswith("\x00EXIT:"):
                    code = int(line.split(":", 1)[1])
                    if code == 0:
                        self.pbar.configure(value=100)
                        self.v_status.set("Done ✔")
                        self.btn_open.configure(state="normal")
                    else:
                        self.v_status.set(f"Failed (exit {code}) — see log")
                    self._reset_buttons()
                    continue
                self._append(line)
                m = CHUNK_RE.search(line)
                if m:
                    k, n = int(m.group(1)), int(m.group(2))
                    self.pbar.configure(value=max(1, round(k / n * 100)))
                    self.v_status.set(f"Upscaling + encoding — chunk {k}/{n}")
                elif "[1/3]" in line:
                    self.v_status.set("Extracting frames…")
                elif "[3/3]" in line:
                    self.v_status.set("Concatenating + muxing audio…")
                elif DONE_RE.search(line):
                    self.pbar.configure(value=100)
        except queue.Empty:
            pass
        self.root.after(120, self._poll)


def main():
    self_test = "--self-test" in sys.argv
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.2)
    except tk.TclError:
        pass
    App(root, self_test=self_test)
    root.mainloop()
    if self_test:
        print("self-test OK: GUI constructed and destroyed cleanly")


if __name__ == "__main__":
    main()
