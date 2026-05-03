"""
Agentic OCR — Flask Web Application
=====================================
Replaces the Tkinter GUI with a modern web interface.

Routes
------
  GET  /                     → serve index.html
  POST /upload               → receive image, start background processing
  GET  /stream/<job_id>      → SSE stream of real-time agent progress
  GET  /download/<job_id>    → serve the generated .docx
  GET  /history              → JSON processing statistics
  GET  /log/<job_id>         → JSON explainability report for a job

Run
---
  python app.py
  Then open http://localhost:5000
"""

import json
import os
import sys
import threading
import uuid
from pathlib import Path
from queue import Empty, Queue

from flask import Flask, Response, jsonify, render_template, request, send_file, stream_with_context
from werkzeug.utils import secure_filename

# ── Project root on path ──────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

import config
from agents.orchestrator import AgentOrchestrator
from utils.logger import AgentLogger

# ── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024   # 20 MB

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
ALLOWED    = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}

# ── Global singletons ─────────────────────────────────────────────────────────
_logger       = AgentLogger(str(Path("logs")))
_orchestrator = AgentOrchestrator(_logger)

_job_queues:  dict[str, Queue] = {}
_job_results: dict[str, dict]  = {}
_job_logs:    dict[str, str]   = {}
_lock = threading.Lock()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _allowed(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"error": "No file selected"}), 400

    filename = secure_filename(file.filename)
    if not _allowed(filename):
        return jsonify({"error": "Unsupported file type. Use JPG, PNG, BMP or TIFF."}), 400

    ext     = Path(filename).suffix.lower()
    job_id  = str(uuid.uuid4())

    img_dir = UPLOAD_DIR / job_id
    out_dir = OUTPUT_DIR / job_id
    img_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    image_path  = img_dir / f"input{ext}"
    output_path = out_dir / "output.docx"

    file.save(str(image_path))

    with _lock:
        _job_queues[job_id] = Queue()

    thread = threading.Thread(
        target=_process_task,
        args=(job_id, str(image_path), str(output_path)),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id, "filename": filename})


def _process_task(job_id: str, image_path: str, output_path: str):
    """Background worker: runs the agent pipeline and pushes SSE events."""
    q = _job_queues.get(job_id)
    if not q:
        return

    def progress_cb(msg: str, pct: float):
        q.put({"type": "progress", "message": msg, "percent": round(pct, 1)})

    result = _orchestrator.process(image_path, output_path, progress_cb)
    _job_results[job_id] = result
    _job_logs[job_id]    = _logger.get_explainability_report()

    if result["success"]:
        q.put({
            "type":             "complete",
            "paragraphs":       result.get("paragraphs", 0),
            "ocr_confidence":   round(result.get("ocr_confidence", 0), 1),
            "ai_confidence":    round(result.get("ai_confidence", 0) * 100, 1),
            "processing_time":  round(result.get("processing_time", 0), 2),
            "multi_column":     result.get("analysis", {}).get("has_multiple_columns", False),
            "has_diagrams":     result.get("analysis", {}).get("has_diagrams", False),
            "structure":        result.get("analysis", {}).get("overall_structure", ""),
            "notes":            result.get("analysis", {}).get("formatting_notes", ""),
        })
    else:
        q.put({"type": "error", "message": result.get("error", "Processing failed")})


@app.route("/stream/<job_id>")
def stream(job_id: str):
    @stream_with_context
    def generate():
        q = _job_queues.get(job_id)
        if not q:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Job not found'})}\n\n"
            return

        while True:
            try:
                event = q.get(timeout=120)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("complete", "error"):
                    with _lock:
                        _job_queues.pop(job_id, None)
                    break
            except Empty:
                yield 'data: {"type":"ping"}\n\n'

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":    "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )


@app.route("/download/<job_id>")
def download(job_id: str):
    result = _job_results.get(job_id)
    if not result or not result.get("success"):
        return jsonify({"error": "Result not found or processing failed"}), 404

    out_path = result.get("output_path", "")
    if not out_path or not os.path.isfile(out_path):
        return jsonify({"error": "Output file missing"}), 404

    return send_file(
        out_path,
        as_attachment=True,
        download_name="converted_document.docx",
        mimetype=(
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        ),
    )


@app.route("/history")
def history():
    stats = _orchestrator.get_stats()
    # Convert tuples to dicts for JSON
    history_rows = []
    for row in stats.get("recent_history", []):
        ts, name, conf, fmt_json, feedback = row
        try:
            fmt = json.loads(fmt_json) if fmt_json else {}
        except Exception:
            fmt = {}
        history_rows.append({
            "timestamp":    ts,
            "image_name":   name,
            "confidence":   round(conf or 0, 1),
            "types":        fmt.get("types", []),
            "ai_confidence": round((fmt.get("ai_confidence") or 0) * 100, 1),
            "feedback":     feedback or "none",
            "multi_column": fmt.get("multi_column", False),
        })
    return jsonify({
        "total":          stats["total_processed"],
        "avg_confidence": round(stats["avg_confidence"], 1),
        "history":        history_rows,
    })


@app.route("/log/<job_id>")
def get_log(job_id: str):
    report = _job_logs.get(job_id, _logger.get_explainability_report())
    return jsonify({"report": report})


@app.route("/feedback/<job_id>", methods=["POST"])
def feedback(job_id: str):
    data = request.get_json(silent=True) or {}
    fb   = data.get("feedback", "")
    if fb not in ("positive", "negative"):
        return jsonify({"error": "Invalid feedback value"}), 400

    result = _job_results.get(job_id)
    if result and result.get("success"):
        from pathlib import Path as _P
        name = _P(result.get("output_path", job_id)).stem
        _orchestrator.memory.store_feedback(name, fb)
        _logger.log("MEMORY", f"User feedback '{fb}' stored for job {job_id[:8]}.")
        return jsonify({"ok": True})

    return jsonify({"error": "Job not found"}), 404


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    UPLOAD_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    print("\n  Agentic OCR System  —  http://localhost:5000\n")
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
