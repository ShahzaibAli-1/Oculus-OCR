"""
Ocular — Agentic OCR System
Streamlit Web Interface
"""

import io
import os
import sys
import shutil
import tempfile
from pathlib import Path

import streamlit as st

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="Ocular — Agentic OCR",
    page_icon="👁️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Inject custom dark CSS ────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Global dark override */
  html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background-color: #000 !important;
    color: #ccc !important;
  }
  [data-testid="stSidebar"] {
    background-color: #080808 !important;
    border-right: 1px solid #1a1a1a !important;
  }
  [data-testid="stHeader"] { background: transparent !important; }

  /* Headings */
  h1,h2,h3,h4 { color: #ffffff !important; font-weight: 300 !important; }

  /* File uploader */
  [data-testid="stFileUploader"] {
    background: #0d0d0d !important;
    border: 1px dashed #2a2a2a !important;
    border-radius: 8px !important;
  }

  /* Primary button */
  .stButton > button[kind="primary"] {
    background: #00e5cc !important;
    color: #000 !important;
    border: none !important;
    border-radius: 4px !important;
    font-weight: 600 !important;
    letter-spacing: .06em !important;
    padding: 10px 28px !important;
  }
  .stButton > button[kind="primary"]:hover {
    background: #00c4ae !important;
  }
  .stButton > button {
    background: #111 !important;
    color: #aaa !important;
    border: 1px solid #222 !important;
    border-radius: 4px !important;
  }

  /* Download button */
  .stDownloadButton > button {
    background: #0d2020 !important;
    color: #00e5cc !important;
    border: 1px solid #00e5cc44 !important;
    border-radius: 4px !important;
    font-weight: 600 !important;
  }
  .stDownloadButton > button:hover {
    background: #00e5cc22 !important;
  }

  /* Metric cards */
  [data-testid="stMetric"] {
    background: #0d0d0d !important;
    border: 1px solid #1e1e1e !important;
    border-radius: 8px !important;
    padding: 16px !important;
  }
  [data-testid="stMetricLabel"] { color: #555 !important; font-size: .75rem !important; letter-spacing: .1em !important; text-transform: uppercase !important; }
  [data-testid="stMetricValue"] { color: #fff !important; }

  /* Progress bar */
  .stProgress > div > div { background: #00e5cc !important; }

  /* Status / expander */
  .stExpander { background: #0d0d0d !important; border: 1px solid #1e1e1e !important; border-radius: 8px !important; }
  .stExpander summary { color: #aaa !important; }

  /* Info / success / warning boxes */
  .stAlert { background: #0d0d0d !important; border-left: 3px solid !important; border-radius: 4px !important; }

  /* Sidebar label */
  .sidebar-brand {
    font-size: 1.4rem; font-weight: 300; color: #fff;
    letter-spacing: .04em; margin-bottom: 4px;
  }
  .sidebar-sub { font-size: .75rem; color: #555; letter-spacing: .14em; text-transform: uppercase; }

  /* Log box */
  .log-box {
    background: #070707; border: 1px solid #1a1a1a; border-radius: 6px;
    padding: 14px 16px; font-family: 'Cascadia Code', 'Consolas', monospace;
    font-size: .75rem; color: #555; max-height: 240px; overflow-y: auto;
    line-height: 1.7;
  }
  .log-box .lg-info  { color: #555; }
  .log-box .lg-warn  { color: #fbbf24; }
  .log-box .lg-error { color: #f87171; }
  .log-box .lg-ok    { color: #4ade80; }

  /* Result section */
  .result-header {
    font-size: .72rem; letter-spacing: .2em; text-transform: uppercase;
    color: #444; margin: 24px 0 12px;
  }
  .badge {
    display: inline-block; background: #111; border: 1px solid #222;
    border-radius: 4px; padding: 4px 10px; font-size: .72rem; color: #888;
    letter-spacing: .06em; margin: 3px;
  }
  .divider { border: none; border-top: 1px solid #111; margin: 20px 0; }
</style>
""", unsafe_allow_html=True)

# ── Environment setup ─────────────────────────────────────────────────────────
# 1. API key — Streamlit Cloud secrets take priority, then .env / system env
def _get_api_key() -> str:
    try:
        return st.secrets["OPENAIAPIKEY"]
    except Exception:
        pass
    try:
        return st.secrets.get("OPENAIAPIKEY", "")
    except Exception:
        pass
    return os.getenv("OPENAIAPIKEY", "")

api_key = _get_api_key()
if api_key:
    os.environ["OPENAIAPIKEY"] = api_key

# 2. Tesseract — cloud Linux path
if shutil.which("tesseract"):
    pass  # already on PATH
elif os.path.isfile("/usr/bin/tesseract"):
    os.environ["TESSERACT_PATH"] = "/usr/bin/tesseract"

# 3. Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# ── Lazy import agents (after env is ready) ───────────────────────────────────
@st.cache_resource(show_spinner=False)
def load_orchestrator():
    """Load orchestrator once per app session (cached)."""
    import config as cfg
    import pytesseract
    # Ensure Tesseract path is set in pytesseract
    tess = shutil.which("tesseract") or "/usr/bin/tesseract"
    pytesseract.pytesseract.tesseract_cmd = tess

    from utils.logger import AgentLogger
    from agents.orchestrator import AgentOrchestrator
    os.makedirs("logs", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    logger = AgentLogger("logs")
    orch   = AgentOrchestrator(logger)
    return orch, logger


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="sidebar-brand">👁️ Ocular</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-sub">Agentic OCR System</div>', unsafe_allow_html=True)
    st.markdown("---")

    st.markdown("**How it works**")
    st.markdown("""
<div style='font-size:.82rem;color:#666;line-height:1.7'>
  <span style='color:#00e5cc'>① Perceive</span> — OpenCV preprocessing<br>
  <span style='color:#60a5fa'>② Interpret</span> — GPT-4o Vision analysis<br>
  <span style='color:#4ade80'>③ Decide</span> — Formatting plan<br>
  <span style='color:#fbbf24'>④ Act</span> — Word document generation<br>
  <span style='color:#c084fc'>⑤ Learn</span> — SQLite memory update
</div>
""", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("**Supported formats**")
    st.markdown('<span class="badge">JPG</span><span class="badge">JPEG</span><span class="badge">PNG</span><span class="badge">BMP</span><span class="badge">TIFF</span>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("**Team**")
    st.markdown("""
<div style='font-size:.8rem;color:#555;line-height:1.9'>
  Shahzaib Ali Khan<br>Abdullah Naeem<br>Muhammad Umar
</div>
<div style='font-size:.7rem;color:#333;margin-top:6px;letter-spacing:.1em;text-transform:uppercase'>
  PPIT · Dept of AI · 2026
</div>
""", unsafe_allow_html=True)

    # API key status
    st.markdown("---")
    if api_key:
        st.markdown("🟢 **API key loaded**", unsafe_allow_html=False)
    else:
        st.markdown("🔴 **API key missing**")
        st.caption("Add OPENAIAPIKEY to Streamlit secrets or .env")


# ── Main area ─────────────────────────────────────────────────────────────────
col_title, _ = st.columns([3, 1])
with col_title:
    st.markdown("## Ocular — Agentic OCR")
    st.markdown('<p style="color:#555;font-size:.9rem;margin-top:-10px">Upload a document image → receive a formatted Word file</p>', unsafe_allow_html=True)

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# ── Upload ────────────────────────────────────────────────────────────────────
col_up, col_prev = st.columns([1, 1], gap="large")

with col_up:
    st.markdown('<p class="result-header">① Upload Image</p>', unsafe_allow_html=True)
    uploaded = st.file_uploader(
        "Drop your document image here",
        type=["jpg", "jpeg", "png", "bmp", "tiff", "tif"],
        label_visibility="collapsed",
    )

with col_prev:
    if uploaded:
        st.markdown('<p class="result-header">Preview</p>', unsafe_allow_html=True)
        st.image(uploaded, use_column_width=True)


# ── Process ───────────────────────────────────────────────────────────────────
if uploaded:
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown('<p class="result-header">② Process</p>', unsafe_allow_html=True)

    run_btn = st.button("▶  Run Ocular Pipeline", type="primary", use_container_width=False)

    if run_btn:
        if not api_key:
            st.error("⚠️  OpenAI API key not found. Add OPENAIAPIKEY to your Streamlit secrets or .env file.")
            st.stop()

        # Load orchestrator
        with st.spinner("Initialising agents…"):
            try:
                orchestrator, logger = load_orchestrator()
            except Exception as e:
                st.error(f"Failed to initialise agents: {e}")
                st.stop()

        # Save upload to temp file
        suffix = Path(uploaded.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_in:
            tmp_in.write(uploaded.read())
            input_path = tmp_in.name

        output_path = input_path.replace(suffix, "_output.docx")

        # ── Live progress ─────────────────────────────────────────────────
        log_lines   = []
        progress_bar = st.progress(0, text="Starting pipeline…")
        log_holder  = st.empty()

        def render_log(lines):
            html = "<div class='log-box'>"
            for ln in lines[-20:]:
                cls = "lg-ok" if "Complete" in ln or "done" in ln.lower() else \
                      "lg-warn" if "WARNING" in ln or "fallback" in ln.lower() else \
                      "lg-error" if "ERROR" in ln else "lg-info"
                html += f'<div class="{cls}">{ln}</div>'
            html += "</div>"
            log_holder.markdown(html, unsafe_allow_html=True)

        def on_progress(msg: str, pct: float):
            progress_bar.progress(int(pct), text=msg)
            log_lines.append(f"{'█' * int(pct/10):10s} {msg}")
            render_log(log_lines)

        # ── Run pipeline ──────────────────────────────────────────────────
        result = orchestrator.process(input_path, output_path, on_progress)

        progress_bar.progress(100, text="✅ Pipeline complete")

        if result["success"]:
            # ── Metrics ───────────────────────────────────────────────────
            st.markdown('<hr class="divider">', unsafe_allow_html=True)
            st.markdown('<p class="result-header">③ Results</p>', unsafe_allow_html=True)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("OCR Confidence",    f"{result['ocr_confidence']:.0f}%")
            m2.metric("AI Confidence",     f"{result['ai_confidence']*100:.0f}%")
            m3.metric("Paragraphs",        result["paragraphs"])
            m4.metric("Processing Time",   f"{result['processing_time']:.1f}s")

            # ── Decision log ──────────────────────────────────────────────
            with st.expander("📋 Agent Decision Log", expanded=False):
                dl = result.get("decision_log", {})
                st.markdown(f"""
<div style='font-size:.82rem;color:#888;line-height:2'>
  <b style='color:#555'>Source:</b> <span style='color:#00e5cc'>{dl.get('source','—').upper()}</span>&nbsp;&nbsp;
  <b style='color:#555'>Types detected:</b> {', '.join(dl.get('types', []))}<br>
  <b style='color:#555'>Multi-column:</b> {'Yes' if dl.get('multi_column') else 'No'}&nbsp;&nbsp;
  <b style='color:#555'>Paragraphs planned:</b> {dl.get('paragraph_count','—')}
</div>
""", unsafe_allow_html=True)

            # ── Download ──────────────────────────────────────────────────
            st.markdown('<p class="result-header">④ Download</p>', unsafe_allow_html=True)
            with open(output_path, "rb") as f:
                docx_bytes = f.read()

            st.download_button(
                label="⬇  Download Word Document (.docx)",
                data=docx_bytes,
                file_name=f"ocular_{Path(uploaded.name).stem}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=False,
            )

            st.success(f"✅  Successfully extracted **{result['paragraphs']} paragraphs** in {result['processing_time']:.1f}s")

        else:
            st.error(f"Pipeline error: {result.get('error', 'Unknown error')}")

        # Cleanup temp files
        try:
            os.unlink(input_path)
        except Exception:
            pass

# ── Empty state ───────────────────────────────────────────────────────────────
if not uploaded:
    st.markdown("""
<div style='text-align:center;padding:60px 0;color:#2a2a2a'>
  <div style='font-size:4rem;margin-bottom:16px'>👁️</div>
  <div style='font-size:1.1rem;color:#333;font-weight:300'>Upload a document image to begin</div>
  <div style='font-size:.8rem;color:#222;margin-top:8px'>Supports JPG · PNG · BMP · TIFF</div>
</div>
""", unsafe_allow_html=True)
