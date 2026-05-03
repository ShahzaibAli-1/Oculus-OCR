/* ══════════════════════════════════════════════════════
   AGENTIC OCR — CLIENT SCRIPT
   Handles: upload, SSE stream, pipeline animation, log,
            results, history, explainability, feedback
══════════════════════════════════════════════════════ */

'use strict';

// ── State ──────────────────────────────────────────────────────────────────
let currentJobId = null;
let selectedFile  = null;
let eventSource   = null;

// Pipeline steps and their keyword triggers
const STEP_TRIGGERS = {
  observe:   ['perceiv', 'ocr', 'preprocessing', 'baseline', 'tesseract'],
  interpret: ['gpt', 'vision', 'interpret', 'analys', 'extract', 'sending'],
  decide:    ['format', 'decid', 'planning', 'making', 'structure', 'style'],
  act:       ['generat', 'writing', 'document', 'word', 'docx'],
  learn:     ['learn', 'stor', 'memory', 'complete', 'done'],
};

// Agent name → badge CSS class
const BADGE_MAP = {
  SYSTEM:       'badge-system',
  ORCHESTRATOR: 'badge-orchestrator',
  PERCEPTION:   'badge-perception',
  VISION:       'badge-vision',
  ANALYSIS:     'badge-analysis',
  FORMATTING:   'badge-formatting',
  DOCUMENT:     'badge-document',
  MEMORY:       'badge-memory',
  ERROR:        'badge-error',
  WARNING:      'badge-warning',
};

// Cycle-bar step ids
const CYCLE_IDS = {
  observe:   'cs-observe',
  interpret: 'cs-interpret',
  decide:    'cs-decide',
  act:       'cs-act',
  learn:     'cs-learn',
};

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initDragDrop();
  initFileInput();
});

// ── Drag-and-drop ──────────────────────────────────────────────────────────
function initDragDrop() {
  const zone = document.getElementById('drop-zone');

  zone.addEventListener('dragover', e => {
    e.preventDefault();
    zone.classList.add('drag-over');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const file = e.dataTransfer?.files?.[0];
    if (file) handleFile(file);
  });
}

function initFileInput() {
  document.getElementById('file-input').addEventListener('change', e => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  });
}

// ── File selection ─────────────────────────────────────────────────────────
function handleFile(file) {
  const allowed = ['image/jpeg', 'image/png', 'image/bmp', 'image/tiff'];
  const isAllowed = allowed.includes(file.type) ||
    /\.(jpg|jpeg|png|bmp|tiff|tif)$/i.test(file.name);

  if (!isAllowed) {
    showToast('Unsupported file type. Please use JPG, PNG, BMP, or TIFF.', 'error');
    return;
  }

  selectedFile = file;

  // Update drop zone label
  document.getElementById('drop-emoji').textContent = '✅';
  document.getElementById('drop-title').textContent  = file.name;

  // Show preview
  const reader = new FileReader();
  reader.onload = e => {
    const img = document.getElementById('preview-img');
    img.src = e.target.result;
    img.onload = () => {
      document.getElementById('preview-meta').textContent =
        `${img.naturalWidth} × ${img.naturalHeight}px  ·  ${(file.size / 1024).toFixed(0)} KB`;
    };
    document.getElementById('preview-box').classList.remove('hidden');
  };
  reader.readAsDataURL(file);

  // Enable convert button
  const btn = document.getElementById('convert-btn');
  btn.disabled = false;

  logEntry('SYSTEM', `File selected: ${file.name}`);
}

// ── Conversion ─────────────────────────────────────────────────────────────
async function startConversion() {
  if (!selectedFile) return;

  // UI: disable button, reset pipeline
  const btn = document.getElementById('convert-btn');
  btn.disabled = true;
  btn.classList.add('processing');
  document.getElementById('btn-label')?.classList; // keep label
  btn.querySelector('.btn-label').textContent = 'Processing…';

  resetPipeline();
  clearLog();
  logEntry('SYSTEM', 'Initiating agentic pipeline…');

  setProgress(0, 'Uploading image…');

  try {
    const formData = new FormData();
    formData.append('file', selectedFile);

    const res  = await fetch('/upload', { method: 'POST', body: formData });
    const data = await res.json();

    if (!res.ok || data.error) {
      handleError(data.error || 'Upload failed');
      return;
    }

    currentJobId = data.job_id;
    logEntry('SYSTEM', `Job started: ${currentJobId.slice(0, 8)}…`);
    connectSSE(currentJobId);

  } catch (err) {
    handleError('Network error: ' + err.message);
  }
}

// ── SSE stream ─────────────────────────────────────────────────────────────
function connectSSE(jobId) {
  if (eventSource) eventSource.close();

  eventSource = new EventSource(`/stream/${jobId}`);

  eventSource.onmessage = e => {
    let data;
    try { data = JSON.parse(e.data); } catch { return; }
    routeSSE(data);
  };

  eventSource.onerror = () => {
    eventSource.close();
    logEntry('ERROR', 'Stream connection lost.');
  };
}

function routeSSE(data) {
  if (data.type === 'ping') return;

  if (data.type === 'progress') {
    const msg = data.message || '';
    setProgress(data.percent || 0, msg);
    detectStep(msg);
    logEntry(detectAgent(msg), msg);
    return;
  }

  if (data.type === 'complete') {
    eventSource?.close();
    onComplete(data);
    return;
  }

  if (data.type === 'error') {
    eventSource?.close();
    handleError(data.message || 'Processing failed');
  }
}

// ── Progress ───────────────────────────────────────────────────────────────
function setProgress(pct, msg) {
  const fill = document.getElementById('progress-fill');
  const glow = document.getElementById('progress-glow');
  const pctEl = document.getElementById('progress-pct');
  const msgEl = document.getElementById('progress-msg');

  fill.style.width = `${pct}%`;
  glow.style.left  = `${pct}%`;
  pctEl.textContent = `${pct}%`;
  msgEl.textContent = msg || '';
}

// ── Pipeline step detection ────────────────────────────────────────────────
let activeStep = null;

function detectStep(msg) {
  const lower = msg.toLowerCase();
  for (const [step, keywords] of Object.entries(STEP_TRIGGERS)) {
    if (keywords.some(k => lower.includes(k))) {
      if (activeStep && activeStep !== step) {
        markStepDone(activeStep);
      }
      markStepActive(step);
      activeStep = step;
      activateCycle(step);
      return;
    }
  }
}

function markStepActive(step) {
  const el = document.getElementById(`ps-${step}`);
  const badge = document.getElementById(`pb-${step}`);
  if (!el) return;
  el.classList.remove('done', 'error');
  el.classList.add('active');
  if (badge) badge.textContent = '⚡';
}

function markStepDone(step) {
  const el = document.getElementById(`ps-${step}`);
  const badge = document.getElementById(`pb-${step}`);
  if (!el) return;
  el.classList.remove('active', 'error');
  el.classList.add('done');
  if (badge) badge.textContent = '✅';
}

function markStepError(step) {
  const el = document.getElementById(`ps-${step}`);
  const badge = document.getElementById(`pb-${step}`);
  if (el) { el.classList.remove('active', 'done'); el.classList.add('error'); }
  if (badge) badge.textContent = '❌';
}

function activateCycle(step) {
  Object.values(CYCLE_IDS).forEach(id =>
    document.getElementById(id)?.classList.remove('active')
  );
  const id = CYCLE_IDS[step];
  if (id) document.getElementById(id)?.classList.add('active');
}

function resetPipeline() {
  activeStep = null;
  ['observe','interpret','decide','act','learn'].forEach(s => {
    const el    = document.getElementById(`ps-${s}`);
    const badge = document.getElementById(`pb-${s}`);
    if (el) el.classList.remove('active','done','error');
    if (badge) badge.textContent = '⏳';
  });
  Object.values(CYCLE_IDS).forEach(id =>
    document.getElementById(id)?.classList.remove('active')
  );
  document.getElementById('metrics')?.classList.add('hidden');
  document.getElementById('result-bar')?.classList.add('hidden');
  document.getElementById('reset-btn')?.classList.add('hidden');
  setProgress(0, 'Starting…');
}

// ── Log ────────────────────────────────────────────────────────────────────
function logEntry(agent, msg) {
  const out   = document.getElementById('log-output');
  const row   = document.createElement('div');
  row.className = 'log-row';

  const badge     = document.createElement('span');
  badge.className = `log-badge ${BADGE_MAP[agent.toUpperCase()] || 'badge-orchestrator'}`;
  badge.textContent = agent.toUpperCase();

  const text = document.createElement('span');
  text.className   = 'log-msg';
  text.textContent = msg;

  row.appendChild(badge);
  row.appendChild(text);
  out.appendChild(row);
  out.scrollTop = out.scrollHeight;
}

function clearLog() {
  const out = document.getElementById('log-output');
  out.innerHTML = '';
  logEntry('SYSTEM', 'Log cleared.');
}

function detectAgent(msg) {
  const m = msg.toLowerCase();
  if (m.includes('perceiv') || m.includes('preprocess') || m.includes('tesseract')) return 'PERCEPTION';
  if (m.includes('vision')  || m.includes('gpt') || m.includes('extract'))          return 'VISION';
  if (m.includes('analys'))                                                           return 'ANALYSIS';
  if (m.includes('format') || m.includes('style') || m.includes('plan'))             return 'FORMATTING';
  if (m.includes('generat') || m.includes('docx') || m.includes('document'))         return 'DOCUMENT';
  if (m.includes('memory') || m.includes('storing') || m.includes('feedback'))       return 'MEMORY';
  return 'ORCHESTRATOR';
}

// ── Completion ─────────────────────────────────────────────────────────────
function onComplete(data) {
  // Finish pipeline
  if (activeStep) markStepDone(activeStep);
  ['observe','interpret','decide','act','learn'].forEach(markStepDone);

  // Activate "Learn" cycle step
  activateCycle('learn');

  setProgress(100, 'Complete!');

  // Show metrics
  const metrics = document.getElementById('metrics');
  document.getElementById('m-paragraphs').textContent = data.paragraphs || '—';
  document.getElementById('m-ocr').textContent        = `${data.ocr_confidence ?? '—'}%`;
  document.getElementById('m-ai').textContent         = `${data.ai_confidence  ?? '—'}%`;
  document.getElementById('m-time').textContent       = data.processing_time ?? '—';
  document.getElementById('m-cols').textContent       = data.multi_column ? '2-col' : '1-col';
  metrics.classList.remove('hidden');

  // Build result bar tags
  const tags = [];
  if (data.multi_column) tags.push('Multi-column');
  if (data.has_diagrams) tags.push('Diagrams detected');
  if (data.structure)    tags.push(data.structure.replace('_', ' '));
  const tagsEl = document.getElementById('result-tags');
  tagsEl.innerHTML = tags.map(t =>
    `<span class="result-tag">${t}</span>`
  ).join('');

  // Show result bar
  document.getElementById('result-bar').classList.remove('hidden');

  // Reset convert button
  const btn = document.getElementById('convert-btn');
  btn.disabled = false;
  btn.classList.remove('processing');
  btn.querySelector('.btn-label').textContent = '▶  Convert Another';

  // Show reset button
  document.getElementById('reset-btn').classList.remove('hidden');

  logEntry('ORCHESTRATOR', `✓ Done — ${data.paragraphs} paragraphs, ${data.processing_time}s`);
}

// ── Error handling ─────────────────────────────────────────────────────────
function handleError(msg) {
  if (activeStep) markStepError(activeStep);

  logEntry('ERROR', msg);
  setProgress(0, 'Processing failed');

  const btn = document.getElementById('convert-btn');
  btn.disabled = false;
  btn.classList.remove('processing');
  btn.querySelector('.btn-label').textContent = '▶  Retry';

  showToast(msg, 'error');
}

// ── Download ───────────────────────────────────────────────────────────────
function downloadDoc() {
  if (!currentJobId) return;
  window.location.href = `/download/${currentJobId}`;
}

// ── Feedback ───────────────────────────────────────────────────────────────
async function sendFeedback(type) {
  if (!currentJobId) return;
  try {
    const res = await fetch(`/feedback/${currentJobId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ feedback: type }),
    });
    if (res.ok) {
      logEntry('MEMORY', `Feedback '${type}' recorded. Agent will learn from this.`);
      showToast(type === 'positive' ? '👍 Thanks! Feedback recorded.' : '👎 Noted. The agent will improve.', 'info');
    }
  } catch {
    showToast('Could not send feedback.', 'error');
  }
}

// ── Explainability ─────────────────────────────────────────────────────────
async function showExplain() {
  const modal = document.getElementById('explain-modal');
  const pre   = document.getElementById('explain-pre');
  modal.classList.remove('hidden');

  if (!currentJobId) {
    pre.textContent = 'No processing run yet.';
    return;
  }
  pre.textContent = 'Loading…';
  try {
    const res  = await fetch(`/log/${currentJobId}`);
    const data = await res.json();
    pre.textContent = data.report || 'No report available.';
  } catch {
    pre.textContent = 'Failed to load report.';
  }
}
function closeExplain() {
  document.getElementById('explain-modal').classList.add('hidden');
}

// ── History ────────────────────────────────────────────────────────────────
async function openHistory() {
  const modal = document.getElementById('history-modal');
  modal.classList.remove('hidden');
  await loadHistory();
}
function closeHistory() {
  document.getElementById('history-modal').classList.add('hidden');
}

async function loadHistory() {
  const body = document.getElementById('history-body');
  body.innerHTML = '<div class="spinner">Loading…</div>';
  try {
    const res  = await fetch('/history');
    const data = await res.json();
    renderHistory(data, body);
  } catch {
    body.innerHTML = '<div class="empty-state"><span class="emoji">⚠️</span>Failed to load history.</div>';
  }
}

function renderHistory(data, container) {
  if (!data.history?.length) {
    container.innerHTML = '<div class="empty-state"><span class="emoji">📭</span>No documents processed yet.</div>';
    return;
  }

  const statHtml = `
    <div class="history-stat">
      <div class="metric">
        <div class="metric-val">${data.total}</div>
        <div class="metric-lbl">Total Processed</div>
      </div>
      <div class="metric">
        <div class="metric-val">${data.avg_confidence}%</div>
        <div class="metric-lbl">Avg OCR Confidence</div>
      </div>
    </div>`;

  const rows = data.history.map(h => `
    <tr>
      <td>${h.timestamp?.slice(0,16) ?? '—'}</td>
      <td title="${h.image_name}">${truncate(h.image_name, 20)}</td>
      <td>${h.confidence}%</td>
      <td>${h.ai_confidence}%</td>
      <td>${h.multi_column ? '2-col' : '1-col'}</td>
      <td>${h.feedback === 'positive' ? '👍' : h.feedback === 'negative' ? '👎' : '—'}</td>
    </tr>`).join('');

  container.innerHTML = statHtml + `
    <table class="history-table">
      <thead>
        <tr>
          <th>Date</th>
          <th>File</th>
          <th>OCR%</th>
          <th>AI%</th>
          <th>Layout</th>
          <th>FB</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// ── Reset ──────────────────────────────────────────────────────────────────
function resetApp() {
  selectedFile  = null;
  currentJobId  = null;
  if (eventSource) { eventSource.close(); eventSource = null; }

  // Reset drop zone
  document.getElementById('drop-emoji').textContent = '🖼️';
  document.getElementById('drop-title').textContent  = 'Drop image here or click to browse';
  document.getElementById('preview-box').classList.add('hidden');
  document.getElementById('file-input').value = '';

  // Reset buttons
  const btn = document.getElementById('convert-btn');
  btn.disabled = true;
  btn.classList.remove('processing');
  btn.querySelector('.btn-label').textContent = 'Convert with AI Agent';
  document.getElementById('reset-btn').classList.add('hidden');

  // Reset pipeline & bars
  resetPipeline();
  clearLog();
  logEntry('SYSTEM', 'Ready for a new image.');
}

// ── Toast ──────────────────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  // Remove existing toasts
  document.querySelectorAll('.toast').forEach(t => t.remove());

  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  Object.assign(el.style, {
    position:     'fixed',
    bottom:       '88px',
    right:        '24px',
    zIndex:       '999',
    padding:      '12px 20px',
    borderRadius: '10px',
    fontSize:     '0.85rem',
    fontWeight:   '500',
    background:   type === 'error' ? 'rgba(248,113,113,0.15)' : 'rgba(124,106,247,0.15)',
    border:       `1px solid ${type === 'error' ? '#f87171' : '#7c6af7'}`,
    color:        type === 'error' ? '#f87171' : '#e8e8ff',
    animation:    'fadeIn 0.2s ease',
    maxWidth:     '360px',
  });
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

// ── Utils ──────────────────────────────────────────────────────────────────
function truncate(str, max) {
  return str.length > max ? str.slice(0, max - 1) + '…' : str;
}
