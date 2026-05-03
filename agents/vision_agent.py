"""
Vision Agent
============
GPT-4o Vision — PRIMARY text extractor and document analyser.

Combines full-page text extraction + structure analysis in a single API call.
Specifically designed to handle:
  - Handwritten notes (chemistry, science, etc.)
  - Multi-column layouts (left + right column notes)
  - Mathematical / chemical formulas (ΔH, α/m, Tc, CaCl₂ …)
  - Diagrams with axis labels
  - Partial / cropped pages

Output is a dict compatible with FormattingAgent.plan_document().
"""

import base64
import json
import re
from pathlib import Path

import openai

try:
    import config
except ImportError:
    config = None


_EXTRACTION_PROMPT = """\
You are an expert at reading, transcribing, and structuring handwritten academic notes.

TASK
Analyse this document image. Extract EVERY piece of visible text AND determine
the formatting/structural role of each element.

═══════════════════════════════════════════════════
RULE 1 — MULTI-COLUMN LAYOUT (VERY IMPORTANT)
═══════════════════════════════════════════════════
Many handwritten notes use two columns on the same page.
  • Process the LEFT column from top → bottom first.
  • Then process the RIGHT column from top → bottom.
  • Set "column": "left", "right", or "full" for every paragraph.

═══════════════════════════════════════════════════
RULE 2 — EXTRACT EVERYTHING
═══════════════════════════════════════════════════
Do NOT skip any text, even if:
  • It is faint, small, or partially cut off.
  • It is inside a drawn box or circle.
  • It is a label on a graph/diagram axis.
  • It is a marginal annotation.
  • It is crossed out (mark is_strikethrough: true).

═══════════════════════════════════════════════════
RULE 3 — FORMULAS & SPECIAL SYMBOLS
═══════════════════════════════════════════════════
  • Greek letters: Δ, α, β, γ, ε, θ, λ (use Unicode or spelled out: Delta)
  • Subscripts: H₂O → write "H2O"; CaCl₂ → "CaCl2"
  • Superscripts: x² → "x^2"
  • Arrows: → ⇒ ∝ (use these Unicode chars)
  • Fractions: α/m = aP/(1+bP)
  • Temperatures: Tc, T₁, T₂

═══════════════════════════════════════════════════
RULE 4 — STRUCTURAL TYPES
═══════════════════════════════════════════════════
Assign each paragraph ONE of these types:
  "title"          — main page title (top of page, often underlined/boxed)
  "heading"        — section heading (# prefix, underlined, or bold)
  "subheading"     — sub-section heading
  "body"           — regular paragraph text
  "formula"        — standalone math/chemical equation
  "bullet"         — list item (starts with •, -, *, →, number)
  "boxed"          — text visually enclosed in a drawn rectangle/box
  "diagram_label"  — label on a graph or diagram

═══════════════════════════════════════════════════
OUTPUT FORMAT (RETURN ONLY THIS JSON — NO MARKDOWN)
═══════════════════════════════════════════════════
{
  "document_title": "string or null",
  "has_multiple_columns": true,
  "paragraphs": [
    {
      "text":               "exact extracted text",
      "type":               "heading",
      "column":             "left",
      "alignment":          "left",
      "is_bold":            true,
      "is_italic":          false,
      "is_strikethrough":   false,
      "font_size_relative": "large",
      "list_item":          false,
      "indent_level":       0
    }
  ],
  "overall_structure":   "two_column",
  "has_table":           false,
  "has_diagrams":        true,
  "diagram_descriptions": ["Freundlich isotherm graph: x-axis P, y-axis α/m"],
  "formatting_notes":    "Red and black ink; diagrams in bottom third",
  "confidence_score":    0.88
}
"""


class VisionAgent:
    """
    GPT-4o Vision — primary text extractor and document analyser.

    Parameters
    ----------
    logger  : AgentLogger
    memory  : MemoryAgent (optional — used to store extraction in session)
    """

    def __init__(self, logger, memory=None):
        self.logger = logger
        self.memory = memory
        api_key = config.OPENAI_API_KEY if config else None
        self.client = openai.OpenAI(api_key=api_key)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _encode_image(path: str) -> str:
        with open(path, "rb") as fh:
            return base64.b64encode(fh.read()).decode("utf-8")

    @staticmethod
    def _media_type(path: str) -> str:
        return (
            "image/jpeg"
            if Path(path).suffix.lower() in {".jpg", ".jpeg"}
            else "image/png"
        )

    @staticmethod
    def _clean_json(raw: str) -> str:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        return raw.strip()

    # ── Core extraction ───────────────────────────────────────────────────────

    def extract_and_analyze(self, image_path: str) -> dict:
        """
        Send the image to GPT-4o Vision and return a structured analysis dict
        compatible with FormattingAgent.plan_document().

        Falls back to an empty structure on unrecoverable errors.
        """
        self.logger.log(
            "VISION",
            f"Sending '{Path(image_path).name}' to GPT-4o Vision (high detail) …",
        )

        b64   = self._encode_image(image_path)
        media = self._media_type(image_path)
        model = config.MODEL_NAME  if config else "gpt-4o"
        maxt  = config.MAX_TOKENS  if config else 4096

        raw = ""
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a highly accurate document transcription AI. "
                            "You read handwritten and printed documents and return structured JSON. "
                            "Never skip text. Handle multi-column layouts precisely. "
                            "Return ONLY valid JSON — no markdown, no prose."
                        ),
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url":    f"data:{media};base64,{b64}",
                                    "detail": "high",
                                },
                            },
                            {"type": "text", "text": _EXTRACTION_PROMPT},
                        ],
                    },
                ],
                max_tokens=maxt,
                temperature=0.05,
            )

            raw     = response.choices[0].message.content or ""
            cleaned = self._clean_json(raw)
            result  = json.loads(cleaned)

            count = len(result.get("paragraphs", []))
            score = result.get("confidence_score", 0)
            self.logger.log(
                "VISION",
                f"Extraction complete — {count} paragraph(s), confidence: {score:.2f}",
            )

            if self.memory:
                self.memory.store_session("vision_extraction", result)

            return result

        except json.JSONDecodeError as exc:
            self.logger.log(
                "VISION", f"JSON parse error: {exc}. Attempting partial recovery.", level="WARNING"
            )
            return self._partial_recovery(raw)

        except openai.OpenAIError as exc:
            self.logger.log("VISION", f"OpenAI API error: {exc}", level="ERROR")
            raise

        except Exception as exc:
            self.logger.log("VISION", f"Unexpected error: {exc}", level="ERROR")
            raise

    # ── Partial recovery ──────────────────────────────────────────────────────

    def _partial_recovery(self, raw: str) -> dict:
        """Try to salvage paragraphs array from a malformed JSON response."""
        self.logger.log("VISION", "Attempting partial JSON recovery …")
        try:
            match = re.search(r'"paragraphs"\s*:\s*(\[.*?\])', raw, re.DOTALL)
            if match:
                paragraphs = json.loads(match.group(1))
                self.logger.log(
                    "VISION", f"Recovered {len(paragraphs)} paragraph(s) from partial JSON."
                )
                return {
                    "document_title":       None,
                    "has_multiple_columns": False,
                    "paragraphs":           paragraphs,
                    "overall_structure":    "single_column",
                    "has_table":            False,
                    "has_diagrams":         False,
                    "diagram_descriptions": [],
                    "formatting_notes":     "Partial recovery from malformed API response",
                    "confidence_score":     0.3,
                }
        except Exception:
            pass

        self.logger.log("VISION", "Partial recovery failed — returning empty structure.", level="WARNING")
        return {
            "document_title":       None,
            "has_multiple_columns": False,
            "paragraphs":           [],
            "overall_structure":    "single_column",
            "has_table":            False,
            "has_diagrams":         False,
            "diagram_descriptions": [],
            "formatting_notes":     "Extraction failed",
            "confidence_score":     0.0,
        }
