"""
Agentic OCR — Main GUI
=======================
Tkinter desktop application that wraps the agentic pipeline.

Layout
------
  Left  : Input / output file pickers, image preview, action buttons,
           progress bar, result summary panel, feedback buttons.
  Right : Live agent activity log (colour-coded per agent).
  Bottom: Collapsible stats window.

Agentic properties surfaced in the UI
--------------------------------------
  - Real-time agent activity log (transparency / explainability).
  - Confidence metrics (OCR + AI) displayed on completion.
  - Human-in-the-loop feedback buttons (👍 / 👎) feed the learning cycle.
  - "View Processing Stats" shows the long-term memory database.
  - "View Log" renders the full explainability report.
"""

import os
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# ── Ensure project root is importable ─────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

import config                                          # noqa: E402
from agents.orchestrator import AgentOrchestrator     # noqa: E402
from utils.logger        import AgentLogger            # noqa: E402


# ── Colour palette (Catppuccin-inspired dark theme) ───────────────────────────
C = {
    "base":    "#1e1e2e",
    "surface": "#313244",
    "overlay": "#45475a",
    "muted":   "#6c7086",
    "subtle":  "#a6adc8",
    "text":    "#cdd6f4",
    "green":   "#a6e3a1",
    "blue":    "#89b4fa",
    "purple":  "#cba6f7",
    "yellow":  "#f9e2af",
    "peach":   "#fab387",
    "teal":    "#94e2d5",
    "red":     "#f38ba8",
    "term":    "#181825",
}

AGENT_COLOURS = {
    "SYSTEM":       C["green"],
    "ORCHESTRATOR": C["blue"],
    "PERCEPTION":   C["peach"],
    "ANALYSIS":     C["purple"],
    "FORMATTING":   C["yellow"],
    "DOCUMENT":     C["teal"],
    "ERROR":        C["red"],
}


class AgenticOCRApp:
    def __init__(self, root: tk.Tk):
        self.root        = root
        self.image_path  = tk.StringVar()
        self.output_path = tk.StringVar()
        self.processing  = False
        self.last_result: dict | None = None

        self._configure_root()
        self._build_ui()
        self._init_agents()

    # ── Window configuration ──────────────────────────────────────────────────

    def _configure_root(self):
        self.root.title("Agentic OCR  ·  Image → Word Converter")
        self.root.geometry("1000x720")
        self.root.minsize(800, 600)
        self.root.configure(bg=C["base"])

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_body()

    def _build_header(self):
        bar = tk.Frame(self.root, bg=C["surface"], pady=14)
        bar.pack(fill=tk.X)
        tk.Label(
            bar, text="Agentic OCR System",
            font=("Segoe UI", 20, "bold"),
            fg=C["purple"], bg=C["surface"],
        ).pack()
        tk.Label(
            bar,
            text="Observe  →  Interpret  →  Decide  →  Act  →  Learn",
            font=("Segoe UI", 9),
            fg=C["subtle"], bg=C["surface"],
        ).pack()

    def _build_body(self):
        body = tk.Frame(self.root, bg=C["base"], padx=18, pady=14)
        body.pack(fill=tk.BOTH, expand=True)

        self._build_left_panel(body)
        self._build_right_panel(body)

    # ── Left panel ────────────────────────────────────────────────────────────

    def _build_left_panel(self, parent):
        left = tk.Frame(parent, bg=C["base"])
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 12))

        # Input file row
        self._section_label(left, "Input Image")
        self._file_row(left, self.image_path,  "Browse…", self._browse_image)

        # Preview
        self.preview_lbl = tk.Label(
            left, text="No image selected",
            bg=C["surface"], fg=C["muted"],
            font=("Segoe UI", 10),
            width=44, height=7,
        )
        self.preview_lbl.pack(fill=tk.X, pady=(0, 10))

        # Output file row
        self._section_label(left, "Output Document")
        self._file_row(left, self.output_path, "Browse…", self._browse_output)

        # Convert button
        self.convert_btn = tk.Button(
            left, text="▶   Convert with AI Agent",
            command=self._start_processing,
            bg=C["green"], fg=C["base"],
            font=("Segoe UI", 12, "bold"),
            relief=tk.FLAT, cursor="hand2", pady=9,
        )
        self.convert_btn.pack(fill=tk.X, pady=(8, 4))

        # Progress bar
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "OCR.Horizontal.TProgressbar",
            troughcolor=C["surface"],
            background=C["green"],
            thickness=8,
        )
        self.progress_var = tk.DoubleVar()
        ttk.Progressbar(
            left, variable=self.progress_var, maximum=100,
            style="OCR.Horizontal.TProgressbar",
        ).pack(fill=tk.X, pady=(0, 2))

        self.status_lbl = tk.Label(
            left, text="Ready",
            bg=C["base"], fg=C["subtle"],
            font=("Segoe UI", 9),
        )
        self.status_lbl.pack(anchor=tk.W)

        # Result area (hidden until first successful run)
        self.result_frame = tk.Frame(left, bg=C["surface"], padx=10, pady=8)
        self.action_frame = tk.Frame(left, bg=C["base"])

    # ── Right panel (agent log) ───────────────────────────────────────────────

    def _build_right_panel(self, parent):
        right = tk.Frame(parent, bg=C["base"], width=330)
        right.pack(side=tk.RIGHT, fill=tk.BOTH)
        right.pack_propagate(False)

        self._section_label(right, "Agent Activity Log")

        self.log_text = scrolledtext.ScrolledText(
            right, wrap=tk.WORD,
            bg=C["term"], fg=C["text"],
            font=("Cascadia Code", 8),
            relief=tk.FLAT, padx=8, pady=8,
            insertbackground=C["text"],
            state=tk.DISABLED,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Register colour tags
        for agent, colour in AGENT_COLOURS.items():
            self.log_text.tag_config(agent, foreground=colour)

        tk.Button(
            right, text="View Processing Stats",
            command=self._show_stats,
            bg=C["surface"], fg=C["subtle"],
            relief=tk.FLAT, font=("Segoe UI", 9),
            cursor="hand2",
        ).pack(fill=tk.X, pady=(5, 0))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _section_label(self, parent, text: str):
        tk.Label(
            parent, text=text.upper(),
            font=("Segoe UI", 8, "bold"),
            fg=C["muted"], bg=C["base"],
        ).pack(anchor=tk.W, pady=(6, 2))

    def _file_row(self, parent, var: tk.StringVar, btn_text: str, cmd):
        frame = tk.Frame(parent, bg=C["surface"])
        frame.pack(fill=tk.X, pady=(0, 8))
        tk.Entry(
            frame, textvariable=var,
            bg=C["overlay"], fg=C["text"],
            insertbackground=C["text"],
            relief=tk.FLAT, font=("Segoe UI", 10),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8, pady=7)
        tk.Button(
            frame, text=btn_text, command=cmd,
            bg=C["blue"], fg=C["base"],
            relief=tk.FLAT, font=("Segoe UI", 9, "bold"),
            cursor="hand2", padx=10,
        ).pack(side=tk.RIGHT, padx=5, pady=5)

    # ── Agent initialisation ──────────────────────────────────────────────────

    def _init_agents(self):
        try:
            log_dir           = os.path.join(os.path.dirname(__file__), "logs")
            self.logger       = AgentLogger(log_dir)
            self.orchestrator = AgentOrchestrator(self.logger)
            self._log("SYSTEM", "All agents ready.")
            self._check_tesseract()
        except Exception as exc:
            messagebox.showerror("Init Error", f"Failed to initialise agents:\n{exc}")

    def _check_tesseract(self):
        """Warn the user if Tesseract OCR is not installed."""
        try:
            import pytesseract
            import config as _cfg
            pytesseract.pytesseract.tesseract_cmd = _cfg.TESSERACT_CMD
            pytesseract.get_tesseract_version()
            self._log("SYSTEM", f"Tesseract found at: {_cfg.TESSERACT_CMD}")
        except Exception:
            self._log("ERROR", "Tesseract OCR engine NOT found.")
            messagebox.showwarning(
                "Tesseract not installed",
                "Tesseract OCR was not found on this system.\n\n"
                "Download and install it from:\n"
                "https://github.com/UB-Mannheim/tesseract/wiki\n\n"
                "After installing, restart the application.\n"
                "The app will still run but OCR will fail without it.",
            )

    # ── Event handlers ────────────────────────────────────────────────────────

    def _browse_image(self):
        path = filedialog.askopenfilename(
            title="Select Image",
            filetypes=[
                ("Images", "*.jpg *.jpeg *.png *.bmp *.tiff *.tif"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        self.image_path.set(path)
        stem = Path(path).stem
        self.output_path.set(
            os.path.join(os.path.dirname(path), f"{stem}_converted.docx")
        )
        self._load_preview(path)

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".docx",
            filetypes=[("Word Document", "*.docx")],
        )
        if path:
            self.output_path.set(path)

    def _load_preview(self, path: str):
        try:
            from PIL import Image, ImageTk
            img = Image.open(path)
            img.thumbnail((380, 160), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.preview_lbl.configure(image=photo, text="")
            self.preview_lbl._photo = photo          # prevent GC
        except Exception:
            self.preview_lbl.configure(
                text=f"[{Path(path).name}]", fg=C["text"]
            )

    def _start_processing(self):
        if self.processing:
            return

        img_path = self.image_path.get().strip()
        out_path = self.output_path.get().strip()

        if not img_path:
            messagebox.showwarning("Input required", "Please select an input image.")
            return
        if not os.path.isfile(img_path):
            messagebox.showerror("File not found", f"Image not found:\n{img_path}")
            return
        if not out_path:
            messagebox.showwarning("Output required", "Please specify an output path.")
            return

        self.processing = True
        self.convert_btn.configure(state=tk.DISABLED, text="Processing …")
        self.progress_var.set(0)
        self._clear_log()

        thread = threading.Thread(
            target=self._run_pipeline,
            args=(img_path, out_path),
            daemon=True,
        )
        thread.start()

    def _run_pipeline(self, img_path: str, out_path: str):
        result = self.orchestrator.process(
            img_path, out_path,
            progress_callback=lambda msg, pct: self.root.after(
                0, self._on_progress, msg, pct
            ),
        )
        self.root.after(0, self._on_complete, result)

    # ── Progress / completion callbacks (run on main thread) ──────────────────

    def _on_progress(self, message: str, pct: float):
        self.progress_var.set(pct)
        self.status_lbl.configure(text=message)

        # Detect which agent the message belongs to
        agent = "ORCHESTRATOR"
        for keyword, tag in (
            ("Perceiving",    "PERCEPTION"),
            ("OCR",           "PERCEPTION"),
            ("Analysing",     "ANALYSIS"),
            ("Interpreting",  "ANALYSIS"),
            ("decision",      "ANALYSIS"),
            ("confidence",    "ANALYSIS"),
            ("Formatting",    "FORMATTING"),
            ("Making",        "FORMATTING"),
            ("Generating",    "DOCUMENT"),
            ("Complete",      "ORCHESTRATOR"),
        ):
            if keyword.lower() in message.lower():
                agent = tag
                break

        self._log(agent, message)
        self.root.update_idletasks()

    def _on_complete(self, result: dict):
        self.processing = False
        self.convert_btn.configure(state=tk.NORMAL, text="▶   Convert with AI Agent")
        self.last_result = result

        if result["success"]:
            self._log(
                "ORCHESTRATOR",
                f"SUCCESS  |  paragraphs: {result['paragraphs']}  "
                f"|  OCR: {result['ocr_confidence']:.0f}%  "
                f"|  AI: {result['ai_confidence']*100:.0f}%  "
                f"|  {result['processing_time']:.1f}s",
            )
            self._show_result_panel(result)
        else:
            err = result.get("error", "Unknown error")
            self._log("ERROR", f"Pipeline failed: {err}")
            messagebox.showerror(
                "Processing failed",
                f"The agent encountered an error:\n\n{err}\n\n"
                "See the activity log for details.",
            )

    # ── Result panel ──────────────────────────────────────────────────────────

    def _show_result_panel(self, result: dict):
        for w in self.result_frame.winfo_children():
            w.destroy()
        self.result_frame.pack(fill=tk.X, pady=(8, 0))

        tk.Label(
            self.result_frame,
            text="✓  Document created successfully",
            fg=C["green"], bg=C["surface"],
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor=tk.W)
        tk.Label(
            self.result_frame,
            text=(
                f"OCR confidence: {result['ocr_confidence']:.1f}%   "
                f"AI analysis: {result['ai_confidence']*100:.0f}%   "
                f"Paragraphs: {result['paragraphs']}"
            ),
            fg=C["subtle"], bg=C["surface"],
            font=("Segoe UI", 8),
        ).pack(anchor=tk.W)

        for w in self.action_frame.winfo_children():
            w.destroy()
        self.action_frame.pack(fill=tk.X, pady=(6, 0))

        self._action_btn("Open Document", C["blue"],
                         lambda: os.startfile(result["output_path"]))
        self._action_btn("View Log",      C["surface"], self._show_log)
        tk.Label(
            self.action_frame, text="Feedback:",
            fg=C["muted"], bg=C["base"], font=("Segoe UI", 9),
        ).pack(side=tk.LEFT, padx=(10, 4))
        self._action_btn("👍", C["surface"],
                         lambda: self._give_feedback("positive"), bold=False)
        self._action_btn("👎", C["surface"],
                         lambda: self._give_feedback("negative"), bold=False)

    def _action_btn(self, text: str, bg: str, cmd, bold: bool = True):
        tk.Button(
            self.action_frame, text=text, command=cmd,
            bg=bg, fg=C["base"] if bg != C["surface"] else C["subtle"],
            relief=tk.FLAT,
            font=("Segoe UI", 9, "bold") if bold else ("Segoe UI", 10),
            cursor="hand2", padx=10, pady=5,
        ).pack(side=tk.LEFT, padx=(0, 4))

    def _give_feedback(self, feedback: str):
        if self.last_result and self.last_result.get("success"):
            name = os.path.basename(self.image_path.get())
            self.orchestrator.memory.store_feedback(name, feedback)
            self._log("SYSTEM", f"Feedback '{feedback}' recorded — agent will learn from this.")
            messagebox.showinfo("Feedback", "Thank you! The agent recorded your feedback.")

    # ── Log helpers ───────────────────────────────────────────────────────────

    def _log(self, agent: str, message: str):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{agent}] ", agent)
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    # ── Pop-up windows ────────────────────────────────────────────────────────

    def _show_log(self):
        if not hasattr(self, "logger"):
            return
        win = self._popup("Agent Explainability Report", "700x520")
        tk.Label(
            win, text="Agent Decision Explainability Report",
            font=("Segoe UI", 12, "bold"),
            fg=C["purple"], bg=C["base"],
        ).pack(pady=10)
        txt = scrolledtext.ScrolledText(
            win, wrap=tk.WORD,
            bg=C["term"], fg=C["text"],
            font=("Cascadia Code", 9),
            relief=tk.FLAT, padx=10, pady=10,
        )
        txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        txt.insert(tk.END, self.logger.get_explainability_report())
        txt.configure(state=tk.DISABLED)

    def _show_stats(self):
        if not hasattr(self, "orchestrator"):
            return
        import json
        stats = self.orchestrator.get_stats()
        win   = self._popup("Processing Statistics", "620x450")
        tk.Label(
            win, text="Agent Learning Statistics",
            font=("Segoe UI", 12, "bold"),
            fg=C["purple"], bg=C["base"],
        ).pack(pady=10)

        info = tk.Frame(win, bg=C["surface"], padx=14, pady=12)
        info.pack(fill=tk.X, padx=14, pady=(0, 8))
        tk.Label(
            info,
            text=f"Total documents processed : {stats['total_processed']}",
            fg=C["text"], bg=C["surface"], font=("Segoe UI", 10),
        ).pack(anchor=tk.W)
        tk.Label(
            info,
            text=f"Average OCR confidence    : {stats['avg_confidence']:.1f}%",
            fg=C["text"], bg=C["surface"], font=("Segoe UI", 10),
        ).pack(anchor=tk.W)

        if stats["recent_history"]:
            tk.Label(
                win, text="RECENT HISTORY",
                font=("Segoe UI", 8, "bold"),
                fg=C["muted"], bg=C["base"],
            ).pack(anchor=tk.W, padx=14)
            txt = scrolledtext.ScrolledText(
                win, wrap=tk.WORD,
                bg=C["term"], fg=C["text"],
                font=("Cascadia Code", 8),
                relief=tk.FLAT, padx=8, pady=8,
            )
            txt.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 14))
            for ts, name, conf, fmt_json, feedback in stats["recent_history"]:
                txt.insert(tk.END, f"[{ts[:10]}]  {name}\n")
                txt.insert(tk.END, f"  OCR: {conf:.1f}%  |  feedback: {feedback or 'none'}\n")
                try:
                    d = json.loads(fmt_json)
                    txt.insert(tk.END, f"  types: {', '.join(d.get('types', []))}\n\n")
                except Exception:
                    txt.insert(tk.END, "\n")
            txt.configure(state=tk.DISABLED)

    def _popup(self, title: str, geometry: str) -> tk.Toplevel:
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry(geometry)
        win.configure(bg=C["base"])
        return win


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    AgenticOCRApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
