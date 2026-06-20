"use strict";

// ── State ─────────────────────────────────────────────────────────────────

let _notes = [];           // [{rel_path, name, size, hash, status, targets}]
let _selected = new Set(); // Set of rel_path strings (multi-select; stage 9)
let _lastResult = null;    // last aggregation result (single) or null in batch mode
let _batchResults = [];    // [{sources, result}] — populated in batch mode
let _segments = [];        // editable segments for single-note mode
let _previewDone = false;
let _lastHealthKey = null;
let _aggregateTimer = null;

// ── DOM refs ──────────────────────────────────────────────────────────────

const $ = id => document.getElementById(id);

const dotOllama     = $("dot-ollama");
const dotVault      = $("dot-vault");
const statusText    = $("status-text");
const btnScan       = $("btn-scan");
const noteListSec   = $("note-list-section");
const noteList      = $("note-list");
const noteCount     = $("note-count");
const noteSearch    = $("note-search");
const selectedCount = $("selected-count");
const btnAggregate  = $("btn-aggregate");
const emptyState   = $("empty-state");
const resultPanel  = $("result-panel");
const indexPanel   = $("index-panel");
const loading      = $("loading");
const loadingText  = $("loading-text");
const toast        = $("toast");

const FOLDER_OPTIONS = [
  { value: "knowledge_folder", label: "05 Knowledge" },
  { value: "areas_folder",     label: "04 Areas" },
  { value: "projects_folder",  label: "03 Projects" },
  { value: "tracking_folder",  label: "06 Tracking" },
  { value: "archive_folder",   label: "07 Archive" },
];

const HABITS = [
  { key: "english",  label: "English",  color: "#15803d" },
  { key: "3d",       label: "3D",       color: "#1d4ed8" },
  { key: "learning", label: "Learning", color: "#b45309" },
  { key: "reading",  label: "Reading",  color: "#7c3aed" },
  { key: "walking",  label: "Walking",  color: "#0891b2" },
  { key: "training", label: "Training", color: "#dc2626" },
];

// ── Utility ───────────────────────────────────────────────────────────────

async function api(method, path, body) {
  const opts = { method };
  if (body) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  const envelope = await res.json();
  if (!res.ok || envelope.ok === false) {
    const msg = envelope.error?.message || envelope.error || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  // Return the inner data payload; fall back to whole envelope for legacy compat
  return envelope.data !== undefined ? envelope.data : envelope;
}

function showLoading(text = "Working…") {
  loadingText.textContent = text;
  loading.hidden = false;
}
function hideLoading() { loading.hidden = true; }

function showToast(msg, isError = false) {
  toast.textContent = msg;
  toast.className = "toast" + (isError ? " toast-error" : " toast-ok");
  toast.hidden = false;
  setTimeout(() => { toast.hidden = true; }, 5000);
}

function setPanel(name) {
  emptyState.hidden  = name !== "empty";
  resultPanel.hidden = name !== "result";
  indexPanel.hidden  = name !== "index";
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const SAFE_HTML_TAGS = new Set([
  "BR", "BUTTON", "DETAILS", "DIV", "EM", "H3", "INPUT", "LABEL",
  "LI", "OPTION", "P", "PRE", "SELECT", "SPAN", "STRONG", "SUMMARY",
  "TEXTAREA", "UL",
]);
const SAFE_HTML_ATTRIBUTES = new Set([
  "class", "disabled", "hidden", "open", "rows", "selected", "title",
  "type", "value",
]);

function setSafeHtml(target, html) {
  const parsed = new DOMParser().parseFromString(String(html), "text/html");
  parsed.body.querySelectorAll("*").forEach(element => {
    if (!SAFE_HTML_TAGS.has(element.tagName)) {
      element.replaceWith(parsed.createTextNode(element.textContent || ""));
      return;
    }
    [...element.attributes].forEach(attribute => {
      const name = attribute.name.toLowerCase();
      const isDataAttribute = name.startsWith("data-");
      const isSafeStyle = name === "style"
        && /^(?:background|color):#[0-9a-f]{6}$/i.test(attribute.value.replace(/\s/g, ""));
      if (!SAFE_HTML_ATTRIBUTES.has(name) && !isDataAttribute && !isSafeStyle) {
        element.removeAttribute(attribute.name);
      }
    });
  });
  target.replaceChildren(...[...parsed.body.childNodes].map(node => document.importNode(node, true)));
}

function folderSelectHtml(selectedKey) {
  return FOLDER_OPTIONS.map(o =>
    `<option value="${o.value}"${o.value === selectedKey ? " selected" : ""}>${o.label}</option>`
  ).join("");
}

function serializeSegments() {
  return _segments.map(s => ({
    folder_key: s.folder_key,
    filename: s.filename,
    content: s.content,
    connections: s.connections || [],
  }));
}

// ── Aggregate timer ───────────────────────────────────────────────────────

function startAggregateTimer() {
  let elapsed = 0;
  _aggregateTimer = setInterval(() => {
    elapsed += 1;
    loadingText.textContent = `Restructuring with LLM… ${elapsed}s`;
  }, 1000);
}

function stopAggregateTimer() {
  if (_aggregateTimer) {
    clearInterval(_aggregateTimer);
    _aggregateTimer = null;
  }
}
// ── Health check ──────────────────────────────────────────────────────────

async function checkHealth() {
  try {
    const h = await api("GET", "/api/health");
    const key = `${h.ollama}:${h.vault_exists}:${h.daily_exists}:${h.ollama_models.length}`;
    if (key === _lastHealthKey) return;
    _lastHealthKey = key;
    dotOllama.className = "dot " + (h.ollama ? "dot-ok" : "dot-err");
    dotVault.className  = "dot " + (h.vault_exists && h.daily_exists ? "dot-ok" : "dot-err");

    const parts = [];
    if (h.ollama) {
      parts.push(`Ollama (${h.ollama_models.length} models)`);
    } else {
      parts.push("Ollama offline — run: ollama serve");
    }
    if (h.vault_exists && h.daily_exists) {
      parts.push("Vault OK");
    } else if (h.vault_exists) {
      parts.push("Daily folder missing — check config");
    } else {
      parts.push("Vault not found — set vault_path in Settings");
    }
    statusText.textContent = parts.join(" · ");
  } catch {
    if (_lastHealthKey === "error") return;
    _lastHealthKey = "error";
    dotOllama.className = "dot dot-err";
    dotVault.className  = "dot dot-err";
    statusText.textContent = "Server unreachable";
  }
}

// ── Scan ──────────────────────────────────────────────────────────────────

async function doScan() {
  showLoading("Scanning daily notes…");
  try {
    const data = await api("POST", "/api/scan");
    _notes = data.notes || [];
    _selected = new Set();
    renderNoteList();
    noteCount.textContent = _notes.length;
    noteListSec.hidden = false;
    if (_notes.length === 0) {
      setPanel("empty");
      showToast("No daily notes found.");
    }
  } catch (err) {
    showToast(err.message, true);
  } finally {
    hideLoading();
  }
}

// ── Note list ─────────────────────────────────────────────────────────────

function getFilteredNotes() {
  const q = (noteSearch?.value || "").trim().toLowerCase();
  if (!q) return _notes;
  return _notes.filter(n => n.name.toLowerCase().includes(q));
}

function renderNoteList() {
  noteList.replaceChildren();
  const visible = getFilteredNotes();
  visible.forEach(note => {
    const item = document.createElement("div");
    item.className = "note-item" + (_selected.has(note.rel_path) ? " selected" : "");
    item.dataset.rel = note.rel_path;
    const statusClass = { new: "s-new", changed: "s-changed", processed: "s-done" }[note.status] || "";
    setSafeHtml(item, `
      <span class="note-status ${statusClass}" title="${escHtml(note.status)}"></span>
      <span class="note-name" title="${escHtml(note.rel_path)}">${escHtml(note.name)}</span>
      <span class="note-size">${(note.size / 1024).toFixed(1)}k</span>
    `);
    item.addEventListener("click", () => toggleSelect(note.rel_path));
    noteList.appendChild(item);
  });
  updateAggregateBtn();
}

function toggleSelect(relPath) {
  if (_selected.has(relPath)) {
    _selected.delete(relPath);
  } else {
    _selected.add(relPath);
  }
  const el = noteList.querySelector(`[data-rel="${CSS.escape(relPath)}"]`);
  if (el) el.classList.toggle("selected", _selected.has(relPath));
  updateAggregateBtn();
}

function updateAggregateBtn() {
  btnAggregate.disabled = _selected.size === 0;

  const infoEl = $("note-processed-info");

  // Multi-select badge
  if (selectedCount) {
    if (_selected.size > 1) {
      selectedCount.textContent = `${_selected.size} notes selected`;
      selectedCount.hidden = false;
    } else {
      selectedCount.hidden = true;
    }
  }

  if (_selected.size === 1) {
    const [rel] = _selected;
    const note = _notes.find(n => n.rel_path === rel);
    if (note && note.status === "processed") {
      const date = note.processed_at ? note.processed_at.slice(0, 10) : "earlier";
      const targets = (note.targets || []).map(t => t.split("/").pop()).join(", ");
      setSafeHtml(infoEl, `✓ Already processed on ${escHtml(date)}${targets ? `<br><span class="note-info-targets">${escHtml(targets)}</span>` : ""}`);
      infoEl.hidden = false;
      btnAggregate.textContent = "Re-process Note";
      return;
    }
  }

  infoEl.hidden = true;
  if (_selected.size > 1) {
    btnAggregate.textContent = `Restructure ${_selected.size} Notes`;
  } else {
    btnAggregate.textContent = "Restructure Note";
  }
}

// ── Aggregate ─────────────────────────────────────────────────────────────

async function doAggregate() {
  if (_selected.size === 0) return;
  const isBatch = _selected.size > 1;
  showLoading(isBatch
    ? `Restructuring ${_selected.size} notes with LLM… 0s`
    : "Restructuring with LLM… 0s");
  startAggregateTimer();
  _previewDone = false;
  _segments = [];
  _batchResults = [];
  try {
    const data = await api("POST", "/api/aggregate", { rel_paths: [..._selected] });
    if (data.batch) {
      // Batch mode — show summary panel
      _batchResults = data.results || [];
      renderBatchResult(_batchResults);
      setPanel("result");
    } else {
      // Single-note mode — existing flow
      _lastResult = data;
      renderResult(data);
      setPanel("result");
    }
  } catch (err) {
    showToast(err.message, true);
  } finally {
    stopAggregateTimer();
    hideLoading();
  }
}
