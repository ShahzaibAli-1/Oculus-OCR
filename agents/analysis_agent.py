"""
Analysis Agent
==============
Responsibilities:
  1. Send the document image + OCR text to GPT-4o Vision and obtain a
     structured JSON description of formatting / document structure.
  2. Make autonomous preprocessing decisions based on OCR confidence.
  3. Provide a rule-based fallback when the API is unavailable.

The agent pulls historical context from MemoryAgent to give the LLM
richer context (goal-based + learning behaviour).
"""

import base64
import json
import re
from pathlib import Path

import openai

try:
    import config
except ImportError:
    config = None  # allow standalone testing


_ANALYSIS_SCHEMA = """\
{
  "document_title": "<string or null>",
  "paragraphs": [
    {
      "text":               "<paragraph text>",
      "type":               "title|heading|subheading|body|bullet|code|quote",
      "alignment":          "left|center|right|justify",
      "is_bold":            true,
      "is_italic":          false,
      "font_size_relative": "large|medium|small",
      "list_item":          false,
      "indent_level":       0
    }
  ],
  "overall_structure": "single_column|two_column|mixed",
  "has_table":         false,
  "formatting_notes":  "<any special observations>",
  "confidence_score":  0.95
}"""


class AnalysisAgent:
    """Uses GPT-4o Vision to analyse document structure and formatting."""

    def __init__(self, logger, memory):
        self.logger = logger
        self.memory = memory
        api_key = config.OPENAI_API_KEY if config else None
        self.client = openai.OpenAI(api_key=api_key)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _encode_image(image_path: str) -> str:
        with open(image_path, "rb") as fh:
            return base64.b64encode(fh.read()).decode("utf-8")

    def _media_type(self, image_path: str) -> str:
        ext = Path(image_path).suffix.lower()
        return "image/jpeg" if ext in {".jpg", ".jpeg"} else "image/png"

    def _context_snippet(self) -> str:
        avg = self.memory.get_avg_confidence()
        hist = self.memory.get_history(5)
        snippet = f"Historical avg OCR confidence: {avg:.1f}%.\n"
        if hist:
            snippet += f"Previously processed {len(hist)} document(s).\n"
        return snippet

    @staticmethod
    def _clean_json(raw: str) -> str:
        """Strip markdown fences if the model wraps its JSON in them."""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        return raw.strip()

    # ── Core analysis ─────────────────────────────────────────────────────────

    def analyze_document(self, image_path: str, ocr_text: str, layout: dict) -> dict:
        """
        Send image + OCR to GPT-4o Vision.
        Falls back to rule-based analysis on any error.
        """
        self.logger.log("ANALYSIS", "Sending image to GPT-4o Vision …")

        image_b64  = self._encode_image(image_path)
        media_type = self._media_type(image_path)
        context    = self._context_snippet()

        prompt = (
            "You are an expert document-structure analyser.\n"
            "Analyse the attached document image together with the OCR text below.\n\n"
            f"OCR Text (first 3 000 chars):\n```\n{ocr_text[:3000]}\n```\n\n"
            f"Context:\n{context}\n"
            "Return a JSON object that exactly matches this schema "
            "(no extra keys, no markdown wrapper):\n\n"
            f"{_ANALYSIS_SCHEMA}\n\n"
            "Be precise about formatting. Return ONLY valid JSON."
        )

        model_name = config.MODEL_NAME if config else "gpt-4o"
        max_tokens = config.MAX_TOKENS if config else 4096

        try:
            response = self.client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a document-analysis AI. "
                            "You analyse document images and return structured JSON "
                            "describing their formatting and content. "
                            "Always return valid JSON only — no markdown, no prose."
                        ),
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url":    f"data:{media_type};base64,{image_b64}",
                                    "detail": "high",
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    },
                ],
                max_tokens=max_tokens,
                temperature=0.1,
            )

            raw     = response.choices[0].message.content or ""
            cleaned = self._clean_json(raw)
            result  = json.loads(cleaned)

            score = result.get("confidence_score", 0)
            self.logger.log("ANALYSIS", f"GPT-4o analysis complete — confidence: {score:.2f}")
            self.memory.store_session("last_analysis", result)
            return result

        except json.JSONDecodeError as exc:
            self.logger.log("ANALYSIS", f"JSON parse error: {exc}. Using fallback.", level="WARNING")
        except openai.OpenAIError as exc:
            self.logger.log("ANALYSIS", f"OpenAI API error: {exc}. Using fallback.", level="WARNING")
        except Exception as exc:
            self.logger.log("ANALYSIS", f"Unexpected error: {exc}. Using fallback.", level="WARNING")

        return self._fallback_analysis(ocr_text)

    # ── Rule-based fallback ───────────────────────────────────────────────────

    def _fallback_analysis(self, ocr_text: str) -> dict:
        """Simple heuristic analysis used when GPT-4o is unavailable."""
        self.logger.log("ANALYSIS", "Running rule-based fallback analysis.")

        paragraphs = []
        for line in ocr_text.splitlines():
            line = line.strip()
            if not line:
                continue

            para_type  = "body"
            is_bold    = False
            alignment  = "left"
            font_size  = "medium"
            list_item  = False

            if line.isupper() and len(line) < 80:
                para_type = "heading"
                is_bold   = True
                alignment = "center"
                font_size = "large"
            elif len(line) < 60 and not line.endswith("."):
                para_type = "subheading"
                is_bold   = True
            elif line[:1] in {"•", "-", "*", "◦"}:
                para_type = "bullet"
                list_item = True

            paragraphs.append({
                "text":               line,
                "type":               para_type,
                "alignment":          alignment,
                "is_bold":            is_bold,
                "is_italic":          False,
                "font_size_relative": font_size,
                "list_item":          list_item,
                "indent_level":       0,
            })

        return {
            "document_title":    None,
            "paragraphs":        paragraphs,
            "overall_structure": "single_column",
            "has_table":         False,
            "formatting_notes":  "Rule-based fallback (GPT-4o unavailable)",
            "confidence_score":  0.4,
        }

    # ── Decision-making ───────────────────────────────────────────────────────

    def decide_preprocessing(self, image_path: str, initial_confidence: float) -> dict:
        """
        Autonomous decision: is the current OCR confidence acceptable,
        or should additional preprocessing be applied?
        """
        self.logger.log(
            "ANALYSIS",
            f"Decision check — OCR confidence: {initial_confidence:.1f}%",
        )

        low    = config.CONFIDENCE_LOW    if config else 60
        medium = config.CONFIDENCE_MEDIUM if config else 75

        if initial_confidence < low:
            reason             = "Very low confidence → aggressive enhancement recommended."
            needs_enhancement  = True
            apply_denoising    = True
            apply_contrast     = True
        elif initial_confidence < medium:
            reason             = "Moderate confidence → light enhancement recommended."
            needs_enhancement  = True
            apply_denoising    = False
            apply_contrast     = True
        else:
            reason             = "High confidence → no extra preprocessing needed."
            needs_enhancement  = False
            apply_denoising    = False
            apply_contrast     = False

        self.logger.log("ANALYSIS", f"Decision: {reason}")
        return {
            "needs_enhancement": needs_enhancement,
            "apply_denoising":   apply_denoising,
            "apply_contrast":    apply_contrast,
            "reason":            reason,
        }
