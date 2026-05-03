"""
Formatting Agent
================
Translates the structured JSON analysis produced by the AnalysisAgent into
a concrete "document plan" — a list of dicts that the DocumentAgent can
consume directly to build the .docx file.

Responsibilities:
  - Map paragraph types (title / heading / body / …) to font sizes, weights.
  - Resolve AI-detected overrides (bold, italic, alignment, indent).
  - Produce a deterministic, ordered list of paragraph-level formatting specs.
"""

from docx.enum.text import WD_ALIGN_PARAGRAPH


class FormattingAgent:
    """Converts an analysis dict into an ordered document plan."""

    # Default styles per paragraph type
    _TYPE_DEFAULTS = {
        "title":      {"font_size": 24, "bold": True,  "alignment": WD_ALIGN_PARAGRAPH.CENTER},
        "heading":    {"font_size": 18, "bold": True,  "alignment": WD_ALIGN_PARAGRAPH.LEFT},
        "subheading": {"font_size": 14, "bold": True,  "alignment": WD_ALIGN_PARAGRAPH.LEFT},
        "body":       {"font_size": 11, "bold": False, "alignment": WD_ALIGN_PARAGRAPH.LEFT},
        "bullet":     {"font_size": 11, "bold": False, "alignment": WD_ALIGN_PARAGRAPH.LEFT},
        "code":       {"font_size": 10, "bold": False, "alignment": WD_ALIGN_PARAGRAPH.LEFT},
        "quote":      {"font_size": 11, "bold": False, "alignment": WD_ALIGN_PARAGRAPH.LEFT},
    }

    _ALIGN_MAP = {
        "left":    WD_ALIGN_PARAGRAPH.LEFT,
        "center":  WD_ALIGN_PARAGRAPH.CENTER,
        "right":   WD_ALIGN_PARAGRAPH.RIGHT,
        "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
    }

    def __init__(self, logger):
        self.logger = logger

    # ── Public API ────────────────────────────────────────────────────────────

    def plan_document(self, analysis: dict) -> list:
        """
        Build and return an ordered list of paragraph specs.

        Each spec is a dict:
        {
            "text":       str,
            "formatting": {
                "type":         str,
                "font_size":    int,
                "bold":         bool,
                "italic":       bool,
                "alignment":    WD_ALIGN_PARAGRAPH,
                "indent_level": int,
                "is_list":      bool,
            }
        }
        """
        self.logger.log("FORMATTING", "Planning document structure …")
        paragraphs = analysis.get("paragraphs", [])
        plan       = []

        for para in paragraphs:
            text = para.get("text", "").strip()
            if not text:
                continue
            spec = {
                "text":       text,
                "formatting": self._resolve(para),
            }
            plan.append(spec)

        self.logger.log("FORMATTING", f"Plan ready — {len(plan)} paragraph(s).")
        return plan

    # ── Private helpers ───────────────────────────────────────────────────────

    def _resolve(self, para: dict) -> dict:
        """Merge type defaults with AI-detected overrides."""
        para_type = para.get("type", "body")
        defaults  = self._TYPE_DEFAULTS.get(para_type, self._TYPE_DEFAULTS["body"])

        # Font size — AI relative hint overrides type default
        size_relative = para.get("font_size_relative", "medium")
        if size_relative == "large":
            font_size = max(defaults["font_size"], 16)
        elif size_relative == "small":
            font_size = min(defaults["font_size"], 10)
        else:
            font_size = defaults["font_size"]

        # Alignment — AI string → WD_ALIGN constant
        align_str = para.get("alignment", "left")
        alignment = self._ALIGN_MAP.get(align_str, defaults["alignment"])

        return {
            "type":         para_type,
            "font_size":    font_size,
            "bold":         para.get("is_bold",      defaults["bold"]),
            "italic":       para.get("is_italic",    False),
            "alignment":    alignment,
            "indent_level": para.get("indent_level", 0),
            "is_list":      para.get("list_item",    False),
        }
