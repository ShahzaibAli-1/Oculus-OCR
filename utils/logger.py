"""
Agent Logger
============
Structured, multi-handler logger that writes to both a rotating log file
and stdout.  Maintains an in-memory list of entries so the GUI can render
an explainability report without re-reading the file.
"""

import logging
import os
from datetime import datetime


class AgentLogger:
    """Structured logger with in-memory audit trail for explainability."""

    def __init__(self, log_dir: str):
        os.makedirs(log_dir, exist_ok=True)
        stamp    = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"agent_{stamp}.log")

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)-7s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[
                logging.FileHandler(log_file, encoding="utf-8"),
                logging.StreamHandler(),
            ],
        )
        self._logger  = logging.getLogger("AgenticOCR")
        self._entries: list[dict] = []
        self.log_file = log_file

    # ── Core log method ───────────────────────────────────────────────────────

    def log(self, agent: str, message: str, level: str = "INFO"):
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "agent":     agent,
            "message":   message,
            "level":     level,
        }
        self._entries.append(entry)

        text = f"[{agent}] {message}"
        if level == "ERROR":
            self._logger.error(text)
        elif level == "WARNING":
            self._logger.warning(text)
        else:
            self._logger.info(text)

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get_log(self) -> list[dict]:
        return list(self._entries)

    def get_explainability_report(self) -> str:
        """
        Human-readable, timestamped explanation of every agent decision
        recorded in this session.
        """
        lines = [
            "╔══════════════════════════════════════════════════════════╗",
            "║         AGENT DECISION EXPLAINABILITY REPORT            ║",
            "╚══════════════════════════════════════════════════════════╝",
            "",
        ]
        for e in self._entries:
            lines.append(f"[{e['timestamp']}]  {e['agent']:14s}  {e['message']}")

        lines += [
            "",
            "── Agent Architecture ───────────────────────────────────────",
            "  PERCEPTION   → preprocess image, run Tesseract OCR",
            "  ANALYSIS     → GPT-4o Vision: detect document structure",
            "  FORMATTING   → map structure to Word paragraph styles",
            "  DOCUMENT     → write .docx with full formatting",
            "  MEMORY       → store result, enable cross-session learning",
            "  ORCHESTRATOR → coordinate loop: Observe→Interpret→Decide→Act→Learn",
        ]
        return "\n".join(lines)
