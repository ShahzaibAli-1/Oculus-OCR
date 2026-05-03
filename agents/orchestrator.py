"""
Agent Orchestrator
==================
Implements the full agentic loop:

    Observe → Interpret → Decide → Act → Learn

Coordinates all specialist agents and returns a rich result dict that
the GUI uses to display outcomes, metrics, and explainability info.

Agent type: Goal-based + Learning agent
  - Goal:    convert an image to a formatted Word document.
  - Learning: stores processing history in long-term memory and uses
              historical confidence stats to inform future decisions.
"""

import os
import time

from .analysis_agent    import AnalysisAgent
from .document_agent    import DocumentAgent
from .formatting_agent  import FormattingAgent
from .memory_agent      import MemoryAgent
from .perception_agent  import PerceptionAgent
from .vision_agent      import VisionAgent

try:
    import config
except ImportError:
    config = None


class AgentOrchestrator:
    """
    Central coordinator — runs the five-phase agentic loop per document.

    Primary extraction path (handwriting / complex images):
        PerceptionAgent  →  VisionAgent (GPT-4o)  →  FormattingAgent  →  DocumentAgent

    Fallback path (high-confidence typed text):
        PerceptionAgent  →  AnalysisAgent  →  FormattingAgent  →  DocumentAgent
    """

    def __init__(self, logger):
        self.logger = logger

        db_path = config.MEMORY_DB_PATH if config else "data/memory.db"
        self.memory     = MemoryAgent(db_path)
        self.perception = PerceptionAgent(logger)
        self.vision     = VisionAgent(logger, self.memory)
        self.analysis   = AnalysisAgent(logger, self.memory)   # fallback
        self.formatting = FormattingAgent(logger)
        self.document   = DocumentAgent(logger)

        self.logger.log("ORCHESTRATOR", "All agents initialised and ready.")

    # ── Main pipeline ─────────────────────────────────────────────────────────

    def process(self, image_path: str, output_path: str, progress_callback=None) -> dict:
        """
        Run the full Observe→Interpret→Decide→Act→Learn loop.

        Parameters
        ----------
        image_path        : path to the input image.
        output_path       : desired .docx output path.
        progress_callback : optional callable(message: str, pct: float).

        Returns
        -------
        dict with keys: success, output_path, ocr_confidence, ai_confidence,
                        paragraphs, processing_time, analysis, decision_log,
                        [error]
        """
        start      = time.time()
        image_name = os.path.basename(image_path)

        def tick(msg: str, pct: float):
            self.logger.log("ORCHESTRATOR", msg)
            if progress_callback:
                progress_callback(msg, pct)

        try:
            # ── 1. OBSERVE ───────────────────────────────────────────────────
            tick("Perceiving image …", 10)
            perception = self.perception.perceive(image_path)

            ocr_text   = perception["raw_text"]
            confidence = perception["confidence"]
            layout     = perception["layout"]

            self.memory.store_session("current_image",  image_name)
            self.memory.store_session("ocr_confidence", confidence)

            # ── 2. INTERPRET (Vision-first) ───────────────────────────────────
            tick(f"OCR baseline: {confidence:.0f}% confidence. Engaging GPT-4o Vision …", 28)

            try:
                # VisionAgent: extracts text + analyses structure in one call.
                # This is the PRIMARY path — much better than Tesseract for
                # handwriting and complex multi-column layouts.
                analysis = self.vision.extract_and_analyze(image_path)

                # If the Vision agent extracted very little, fall back to
                # the legacy Tesseract + AnalysisAgent path.
                if len(analysis.get("paragraphs", [])) < 2:
                    tick("Vision extraction sparse — falling back to OCR analysis …", 42)
                    analysis = self.analysis.analyze_document(image_path, ocr_text, layout)

            except Exception as vision_exc:
                self.logger.log(
                    "ORCHESTRATOR",
                    f"VisionAgent failed ({vision_exc}). Using fallback analysis.",
                    level="WARNING",
                )
                analysis = self.analysis.analyze_document(image_path, ocr_text, layout)

            tick(
                f"Analysis complete — {len(analysis.get('paragraphs', []))} element(s) detected.",
                62,
            )

            # ── 3. DECIDE ────────────────────────────────────────────────────
            tick("Making formatting decisions …", 74)
            document_plan = self.formatting.plan_document(analysis)
            self.memory.store_session("plan_count", len(document_plan))

            # ── 4. ACT ───────────────────────────────────────────────────────
            tick("Generating Word document …", 87)
            self.document.generate(document_plan, output_path, analysis)

            # ── 5. LEARN ─────────────────────────────────────────────────────
            elapsed = time.time() - start
            fmt_summary = {
                "paragraph_count": len(document_plan),
                "types":           list({p["formatting"]["type"] for p in document_plan}),
                "ai_confidence":   analysis.get("confidence_score", 0),
                "source":          "vision" if analysis.get("confidence_score", 0) > 0.5 else "fallback",
                "multi_column":    analysis.get("has_multiple_columns", False),
            }
            self.memory.store_processing(image_name, confidence, fmt_summary, elapsed)
            tick(f"Complete! {len(document_plan)} paragraphs in {elapsed:.1f}s", 100)

            return {
                "success":          True,
                "output_path":      output_path,
                "ocr_confidence":   confidence,
                "ai_confidence":    analysis.get("confidence_score", 0),
                "paragraphs":       len(document_plan),
                "processing_time":  elapsed,
                "analysis":         analysis,
                "decision_log":     fmt_summary,
            }

        except Exception as exc:
            self.logger.log("ORCHESTRATOR", f"Pipeline error: {exc}", level="ERROR")
            return {
                "success":         False,
                "error":           str(exc),
                "processing_time": time.time() - start,
            }

    # ── Stats / introspection ─────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return aggregate learning statistics."""
        history = self.memory.get_history(20)
        return {
            "total_processed": len(history),
            "avg_confidence":  self.memory.get_avg_confidence(),
            "recent_history":  history,
        }
