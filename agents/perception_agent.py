"""
Perception Agent
================
Responsibilities:
  1. Preprocess the input image (grayscale, denoise, threshold, deskew, upscale).
  2. Run Tesseract OCR to extract text + per-word bounding-box data.
  3. Detect coarse layout features (line separators, image dimensions).

Returns a unified perception dictionary consumed by the Orchestrator.
"""

import os
import sys

import cv2
import numpy as np
import pytesseract
from PIL import Image

# ── Tesseract path (set before any pytesseract call) ─────────────────────────
# Import config with a fallback so this module can be tested standalone.
try:
    import config
    pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
except ImportError:
    pass  # will use whatever is on PATH


class PerceptionAgent:
    """Handles image preprocessing and OCR text extraction."""

    def __init__(self, logger):
        self.logger = logger

    # ── Preprocessing ─────────────────────────────────────────────────────────

    def preprocess(self, image_path: str):
        """
        Preprocess image for optimal OCR accuracy.

        Returns
        -------
        (processed_gray, original_bgr) : tuple[np.ndarray, np.ndarray]
        """
        self.logger.log("PERCEPTION", f"Preprocessing: {os.path.basename(image_path)}")

        original = cv2.imread(image_path)
        if original is None:
            raise ValueError(f"Cannot read image at path: {image_path}")

        gray     = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
        denoised = cv2.fastNlMeansDenoising(gray, h=10)

        # Adaptive threshold → clean binary image
        binary = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2,
        )

        # Deskew
        binary = self._deskew(binary)

        # Upscale for better OCR on small text
        scale  = 2.0
        binary = cv2.resize(
            binary, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
        )

        self.logger.log("PERCEPTION", "Preprocessing complete.")
        return binary, original

    def _deskew(self, binary: np.ndarray) -> np.ndarray:
        """Rotate a binary image to correct small tilts."""
        coords = np.column_stack(np.where(binary < 128))
        if len(coords) < 5:
            return binary
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) < 0.5:
            return binary
        h, w   = binary.shape
        center = (w // 2, h // 2)
        M      = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(
            binary, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

    # ── OCR ───────────────────────────────────────────────────────────────────

    def extract_text_data(self, processed: np.ndarray) -> dict:
        """Run Tesseract and return raw text + confidence."""
        self.logger.log("PERCEPTION", "Running Tesseract OCR …")

        pil_img = Image.fromarray(processed)

        ocr_data = pytesseract.image_to_data(
            pil_img,
            output_type=pytesseract.Output.DICT,
            config="--psm 6",
        )
        raw_text = pytesseract.image_to_string(pil_img, config="--psm 6")

        confidences = [int(c) for c in ocr_data["conf"] if str(c).lstrip("-").isdigit() and int(c) > 0]
        avg_conf    = sum(confidences) / len(confidences) if confidences else 0.0

        self.logger.log("PERCEPTION", f"OCR done — avg confidence: {avg_conf:.1f}%")
        return {"text": raw_text, "ocr_data": ocr_data, "confidence": avg_conf}

    # ── Layout features ───────────────────────────────────────────────────────

    def detect_layout_features(self, original: np.ndarray) -> dict:
        """Detect coarse layout features (separators, dimensions)."""
        self.logger.log("PERCEPTION", "Detecting layout features …")

        gray     = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
        h, w     = gray.shape
        edges    = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines    = cv2.HoughLinesP(
            edges, 1, np.pi / 180, threshold=100,
            minLineLength=w // 3, maxLineGap=10,
        )

        return {
            "image_width":          w,
            "image_height":         h,
            "has_horizontal_lines": lines is not None,
        }

    # ── Public pipeline ───────────────────────────────────────────────────────

    def perceive(self, image_path: str) -> dict:
        """
        Full perception pipeline.

        Returns
        -------
        dict with keys: raw_text, ocr_data, confidence, layout, image_path
        """
        processed, original = self.preprocess(image_path)
        ocr_result          = self.extract_text_data(processed)
        layout              = self.detect_layout_features(original)

        return {
            "raw_text":   ocr_result["text"],
            "ocr_data":   ocr_result["ocr_data"],
            "confidence": ocr_result["confidence"],
            "layout":     layout,
            "image_path": image_path,
        }
