import os
import shutil
from dotenv import load_dotenv

load_dotenv()

# ── API ─────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAIAPIKEY")

# ── Tesseract path — auto-detect, then fall back to default Windows install ─
def _find_tesseract() -> str:
    """Return the path to the tesseract executable, or the Windows default."""
    on_path = shutil.which("tesseract")
    if on_path:
        return on_path
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"C:\Users\{}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe".format(
            os.environ.get("USERNAME", "")
        ),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return candidates[0]   # default — pytesseract will raise a clear error if missing

TESSERACT_CMD = _find_tesseract()

# ── OpenAI model ─────────────────────────────────────────────────────────────
MODEL_NAME = "gpt-4o"
MAX_TOKENS = 4096

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(__file__)
MEMORY_DB_PATH = os.path.join(BASE_DIR, "data", "memory.db")
LOG_DIR        = os.path.join(BASE_DIR, "logs")

# ── OCR confidence thresholds ────────────────────────────────────────────────
CONFIDENCE_LOW    = 60   # below → aggressive preprocessing
CONFIDENCE_MEDIUM = 75   # below → moderate preprocessing
