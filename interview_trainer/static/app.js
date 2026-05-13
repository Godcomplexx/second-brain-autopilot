"use strict";

// ── State ─────────────────────────────────────────────────────────────────

let _notes = [];           // [{rel_path, name, size, hash, status, targets}]
let _selected = null;      // rel_path string of the selected note, or null
let _lastResult = null;    // last aggregation result
let _segments = [];        // editable segments [{topic, folder_key, filename, content}]
let _previewDone = false;
let _lastHealthKey = null; // last serialized health state for change detection

// ── DOM refs ──────────────────────────────────────────────────────────────

const $ = id => document.getElementById(id);

const dotOllama    = $("dot-ollama");
const dotVault     = $("dot-vault");
const statusText   = $("status-text");
const btnScan      = $("btn-scan");
const noteListSec  = $("note-list-section");
const noteList     = $("note-list");
const noteCount    = $("note-count");
const btnAggregate = $("btn-aggregate");
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
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
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
    if (h.ollama) parts.push(`Ollama (${h.ollama_models.length} models)`);
    else parts.push("Ollama offline");
    if (h.vault_exists && h.daily_exists) parts.push("Vault OK");
    else if (h.vault_exists) parts.push("Daily folder missing");
    else parts.push("Vault missing");
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
    _selected = null;
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

function renderNoteList() {
  noteList.innerHTML = "";
  _notes.forEach(note => {
    const item = document.createElement("div");
    item.className = "note-item" + (_selected === note.rel_path ? " selected" : "");
    item.dataset.rel = note.rel_path;
    const statusClass = { new: "s-new", changed: "s-changed", processed: "s-done" }[note.status] || "";
    item.innerHTML = `
      <span class="note-status ${statusClass}" title="${note.status}"></span>
      <span class="note-name" title="${note.rel_path}">${note.name}</span>
      <span class="note-size">${(note.size / 1024).toFixed(1)}k</span>
    `;
    item.addEventListener("click", () => toggleSelect(note.rel_path));
    noteList.appendChild(item);
  });
  updateAggregateBtn();
}

function toggleSelect(relPath) {
  const prev = _selected;
  _selected = _selected === relPath ? null : relPath;
  if (prev) noteList.querySelector(`[data-rel="${CSS.escape(prev)}"]`)?.classList.remove("selected");
  if (_selected) noteList.querySelector(`[data-rel="${CSS.escape(_selected)}"]`)?.classList.add("selected");
  updateAggregateBtn();
}

function updateAggregateBtn() {
  btnAggregate.disabled = _selected === null;

  const note = _notes.find(n => n.rel_path === _selected);
  const infoEl = $("note-processed-info");

  if (note && note.status === "processed") {
    const date = note.processed_at ? note.processed_at.slice(0, 10) : "earlier";
    const targets = (note.targets || []).map(t => t.split("/").pop()).join(", ");
    infoEl.innerHTML = `✓ Already processed on ${date}${targets ? `<br><span class="note-info-targets">${targets}</span>` : ""}`;
    infoEl.hidden = false;
    btnAggregate.textContent = "Re-process Note";
  } else {
    infoEl.hidden = true;
    btnAggregate.textContent = "Restructure Note";
  }
}

// ── Aggregate ─────────────────────────────────────────────────────────────

async function doAggregate() {
  if (_selected === null) return;
  showLoading("Restructuring with LLM…");
  _previewDone = false;
  _segments = [];
  try {
    const data = await api("POST", "/api/aggregate", { rel_paths: [_selected] });
    _lastResult = data;
    renderResult(data);
    setPanel("result");
  } catch (err) {
    showToast(err.message, true);
  } finally {
    hideLoading();
  }
}

// ── Render result ─────────────────────────────────────────────────────────

function renderResult(data) {
  const r = data.result || {};
  $("result-meta").textContent = `Source: ${data.sources.join(", ")}`;

  if (r.parse_error) {
    $("segments-area").innerHTML = `
      <div class="card error-card">
        <h3>⚠ Could not parse LLM response</h3>
        <pre>${escHtml(r.raw_response || data.raw_llm || "")}</pre>
      </div>`;
    $("btn-preview").disabled = true;
    $("btn-write").disabled = true;
    return;
  }

  const segments = r.segments || [];
  _segments = segments.map(s => ({ ...s })); // editable copy

  // Tasks summary
  const tasks = r.tasks || [];
  const tasksSummary = tasks.length
    ? `<div class="tasks-summary"><strong>✅ ${tasks.length} task${tasks.length > 1 ? "s" : ""} found</strong> — will go to 06 Tracking/Task Inbox.md<ul>${
        tasks.map(t => `<li>- [ ] ${escHtml(t.text)}${t.due ? ` 📅 ${t.due}` : ""}</li>`).join("")
      }</ul></div>`
    : "";

  // Habit detection summary
  const habits = r.habits || {};
  const habitKeys = Object.keys(habits).filter(k => habits[k] > 0);
  const habitsSummary = habitKeys.length
    ? `<div class="tasks-summary"><strong>📊 Habits detected</strong><ul>${
        habitKeys.map(k => {
          const h = HABITS.find(h => h.key === k);
          return `<li style="color:${h?.color || "inherit"}">${h?.label || k}: ${habits[k]}</li>`;
        }).join("")
      }</ul></div>`
    : "";

  // Segment cards
  const segCards = segments.map((seg, i) => {
    const conns = (seg.connections || []);
    const connHtml = conns.length
      ? `<div class="seg-connections">${conns.map(c => `<span class="conn-pill">${escHtml(c)}</span>`).join("")}</div>`
      : "";
    return `
    <div class="seg-card card" data-idx="${i}">
      <div class="seg-header">
        <span class="seg-topic">${escHtml(seg.topic)}</span>
        <span class="seg-reason">${escHtml(seg.reason || "")}</span>
      </div>
      <div class="seg-fields">
        <label>Folder
          <select class="seg-folder" data-idx="${i}">${folderSelectHtml(seg.folder_key)}</select>
        </label>
        <label>Filename
          <input class="seg-filename" data-idx="${i}" type="text" value="${escHtml(seg.filename)}" />
        </label>
      </div>
      ${connHtml}
      <details class="seg-preview">
        <summary>Preview content</summary>
        <pre>${escHtml(seg.content)}</pre>
      </details>
    </div>`;
  }).join("");

  $("segments-area").innerHTML = segCards + tasksSummary + habitsSummary;

  // Wire up live edits
  document.querySelectorAll(".seg-folder").forEach(el => {
    el.addEventListener("change", () => {
      _segments[+el.dataset.idx].folder_key = el.value;
      resetPreview();
    });
  });
  document.querySelectorAll(".seg-filename").forEach(el => {
    el.addEventListener("input", () => {
      _segments[+el.dataset.idx].filename = el.value.trim();
      resetPreview();
    });
  });

  $("btn-preview").disabled = segments.length === 0;
  $("btn-write").disabled = true;
  $("write-preview").hidden = true;
  $("write-done").hidden = true;
  $("write-actions").hidden = false;
}

function resetPreview() {
  _previewDone = false;
  $("btn-write").disabled = true;
  $("write-preview").hidden = true;
  $("write-done").hidden = true;
  $("write-actions").hidden = false;
}

// ── Preview ───────────────────────────────────────────────────────────────

async function doPreview() {
  if (!_lastResult || _segments.length === 0) return;
  const source = _lastResult.sources[0];
  const r = _lastResult.result;
  const tasks = (r.tasks || []).filter(t => t.text);

  showLoading("Building preview…");
  try {
    const prev = await api("POST", "/api/preview", {
      source_rel: source,
      segments: serializeSegments(),
    });

    const previews = prev.previews || [];
    let html = "";

    previews.forEach((p, i) => {
      const seg = _segments[i];
      const action = p.target_exists ? "update existing file" : "create new file";
      html += `
        <div class="plan-item">
          <div class="plan-icon">📝</div>
          <div class="plan-body">
            <div class="plan-dest">${escHtml(p.target_path)}</div>
            <div class="plan-action">${action} · topic: ${escHtml(seg.topic)}</div>
            <pre class="preview-block">${escHtml(p.block_preview)}</pre>
          </div>
        </div>`;
    });

    if (tasks.length) {
      const taskLines = tasks.map(t => {
        const due = t.due ? ` 📅 ${t.due}` : "";
        const pri = {high:"🔴",medium:"🟡",low:"🟢"}[t.priority] || "";
        return `<li>- [ ] ${escHtml(t.text)}${escHtml(due)} ${pri}</li>`;
      }).join("");
      html += `
        <div class="plan-item">
          <div class="plan-icon">✅</div>
          <div class="plan-body">
            <div class="plan-dest">06 Tracking/Task Inbox.md</div>
            <div class="plan-action">${tasks.length} task${tasks.length > 1 ? "s" : ""} appended</div>
            <ul class="plan-tasks">${taskLines}</ul>
          </div>
        </div>`;
    }

    // Habits write preview
    const habits = r.habits || {};
    const habitKeys = Object.keys(habits).filter(k => habits[k] > 0);
    if (habitKeys.length) {
      const lines = habitKeys.map(k => `<li>${k}:: ${habits[k]}</li>`).join("");
      html += `
        <div class="plan-item">
          <div class="plan-icon">📊</div>
          <div class="plan-body">
            <div class="plan-dest">${escHtml(source)}</div>
            <div class="plan-action">habit fields updated by AI</div>
            <ul class="plan-tasks">${lines}</ul>
          </div>
        </div>`;
    }

    const box = $("write-preview");
    box.innerHTML = html;
    box.hidden = false;
    _previewDone = true;
    $("btn-write").disabled = false;
  } catch (err) {
    showToast(err.message, true);
  } finally {
    hideLoading();
  }
}

// ── Write ─────────────────────────────────────────────────────────────────

async function doWrite() {
  if (!_lastResult || !_previewDone) return;
  const source = _lastResult.sources[0];
  const tasks = (_lastResult.result.tasks || []).filter(t => t.text);
  const habits = _lastResult.result.habits || {};
  const btnWrite = $("btn-write");

  btnWrite.classList.add("btn-loading");
  btnWrite.innerHTML = `Writing… <span class="btn-spinner"></span>`;
  showLoading("Writing to vault…");

  try {
    const res = await api("POST", "/api/write", {
      source_rel: source,
      segments: serializeSegments(),
      tasks,
      habits,
    });

    const written = res.written || [];
    const paths = written.map(w => w.target_path);
    const taskCount = res.tasks_written?.written || 0;
    const habitsUpdated = res.habits_written ? " · habits updated" : "";

    // show persistent done banner
    $("write-preview").hidden = true;
    $("write-actions").hidden = true;
    const donePaths = $("write-done-paths");
    donePaths.textContent = paths.join(" · ") + (taskCount ? ` · ${taskCount} tasks` : "") + habitsUpdated;
    $("write-done").hidden = false;

    _previewDone = false;
    await doScan();
    loadTrackerSidebar();
  } catch (err) {
    showToast(err.message, true);
  } finally {
    hideLoading();
    btnWrite.classList.remove("btn-loading");
    btnWrite.innerHTML = "Approve &amp; Write All";
  }
}

// ── Index view ────────────────────────────────────────────────────────────

async function doViewIndex() {
  showLoading("Loading index…");
  try {
    const idx = await api("GET", "/api/index");
    const processed = idx.processed || {};
    const tasks = idx.tasks || [];
    const keys = Object.keys(processed);
    let html = `<h3>Processed (${keys.length})</h3>`;
    if (keys.length === 0) {
      html += "<p>No notes processed yet.</p>";
    } else {
      html += "<ul class='index-list'>";
      keys.forEach(k => {
        const rec = processed[k];
        html += `<li><strong>${escHtml(k)}</strong> → ${(rec.targets || []).map(escHtml).join(", ")} <em>(${rec.processed_at || ""})</em></li>`;
      });
      html += "</ul>";
    }
    html += `<h3>Tasks (${tasks.length})</h3>`;
    if (tasks.length === 0) {
      html += "<p>No tasks indexed.</p>";
    } else {
      html += "<ul class='index-list'>";
      tasks.forEach(t => {
        html += `<li>[${t.done ? "x" : " "}] ${escHtml(t.text)} <em>← ${escHtml(t.source || "")}</em></li>`;
      });
      html += "</ul>";
    }
    $("index-content").innerHTML = html;
    setPanel("index");
  } catch (err) {
    showToast(err.message, true);
  } finally {
    hideLoading();
  }
}

// ── Tracker sidebar ───────────────────────────────────────────────────────

function getLast7Days() {
  const days = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    days.push(d.toISOString().slice(0, 10));
  }
  return days;
}

async function loadTrackerSidebar() {
  try {
    const [habitsResp, indexResp] = await Promise.all([
      api("GET", "/api/habits"),
      api("GET", "/api/index"),
    ]);
    renderHabitsSidebar(habitsResp.habits || []);
    renderTasksSidebar(indexResp.tasks || []);
  } catch {
    $("ts-habits").innerHTML = `<div class="ts-empty">Unavailable</div>`;
    $("ts-tasks").innerHTML  = `<div class="ts-empty">Unavailable</div>`;
  }
}

function renderHabitsSidebar(data) {
  const today = new Date().toISOString().slice(0, 10);
  const days = getLast7Days();
  const byDate = Object.fromEntries(data.map(d => [d.date, d]));

  const d = new Date();
  $("ts-date").textContent = d.toLocaleDateString("en", { weekday: "short", day: "numeric", month: "short" });

  $("ts-habits").innerHTML = HABITS.map(h => {
    const dots = days.map(day => {
      const rec = byDate[day] || {};
      const done = (rec[h.key] ?? 0) >= 1;
      const isToday = day === today;
      const newVal = done ? 0 : 1;
      return `<span class="ts-day${isToday ? " ts-day-today" : ""}${done ? " ts-day-done" : ""}"
        style="${done ? `background:${h.color}` : ""}"
        data-key="${h.key}" data-val="${newVal}" title="${day}"></span>`;
    }).join("");
    const weekDone = days.filter(day => ((byDate[day] || {})[h.key] ?? 0) >= 1).length;
    return `
      <div class="ts-habit-row">
        <span class="ts-habit-name">${h.label}</span>
        <span class="ts-habit-days">${dots}</span>
        <span class="ts-habit-week">${weekDone}/7</span>
      </div>`;
  }).join("");

  $("ts-habits").querySelectorAll(".ts-day-today").forEach(dot => {
    dot.addEventListener("click", async () => {
      try {
        await api("POST", "/api/habits/toggle", { key: dot.dataset.key, value: parseInt(dot.dataset.val) });
        loadTrackerSidebar();
      } catch (err) { showToast(err.message, true); }
    });
  });
}

function renderTasksSidebar(tasks) {
  const open = tasks.filter(t => !t.done);
  const el = $("ts-tasks");
  const badge = $("ts-task-count");
  badge.textContent = open.length || "";
  badge.hidden = open.length === 0;

  if (open.length === 0) {
    el.innerHTML = `<div class="ts-empty">All done</div>`;
    return;
  }

  el.innerHTML = open.map(t => `
    <div class="ts-task-row" data-text="${escHtml(t.text)}" data-source="${escHtml(t.source || "")}">
      <button class="ts-task-check" title="Mark done"></button>
      <span class="ts-task-text">${escHtml(t.text)}</span>
    </div>`).join("");

  el.querySelectorAll(".ts-task-check").forEach(btn => {
    btn.addEventListener("click", async () => {
      const row = btn.closest(".ts-task-row");
      try {
        await api("POST", "/api/tasks/toggle", { text: row.dataset.text, source: row.dataset.source });
        loadTrackerSidebar();
      } catch (err) { showToast(err.message, true); }
    });
  });
}

// ── Task tracker ─────────────────────────────────────────────────────────

function renderTasks(tasks) {
  const el = $("tracker-tasks");
  if (tasks.length === 0) {
    el.innerHTML = `<p class="tracker-empty">No tasks extracted yet — process a daily note first.</p>`;
    return;
  }

  const open = tasks.filter(t => !t.done);
  const done = tasks.filter(t => t.done);

  const taskHtml = (t, isDone) => {
    const due = t.due ? `<span class="task-due">📅 ${escHtml(t.due)}</span>` : "";
    const pri = { high: "🔴", medium: "🟡", low: "🟢" }[t.priority] || "";
    const src = t.source ? `<span class="task-src">${escHtml(t.source.replace(/^.*[/\\]/, "").replace(/\.md$/, ""))}</span>` : "";
    return `
      <div class="task-item${isDone ? " task-done" : ""}" data-text="${escHtml(t.text)}" data-source="${escHtml(t.source || "")}">
        <button class="task-check${isDone ? " task-check-done" : ""}" title="${isDone ? "Mark undone" : "Mark done"}">
          ${isDone ? "✓" : ""}
        </button>
        <span class="task-text">${escHtml(t.text)}</span>
        <span class="task-meta">${due}${pri ? ` ${pri}` : ""}${src}</span>
      </div>`;
  };

  let html = "";
  if (open.length) {
    html += `<div class="task-group-label">Open (${open.length})</div>`;
    html += open.map(t => taskHtml(t, false)).join("");
  }
  if (done.length) {
    html += `<div class="task-group-label task-group-done">Done (${done.length})</div>`;
    html += done.map(t => taskHtml(t, true)).join("");
  }

  el.innerHTML = html;

  el.querySelectorAll(".task-check").forEach(btn => {
    btn.addEventListener("click", () => toggleTask(btn.closest(".task-item")));
  });
}

async function toggleTask(itemEl) {
  const text = itemEl.dataset.text;
  const source = itemEl.dataset.source;
  try {
    const res = await api("POST", "/api/tasks/toggle", { text, source });
    const isDone = res.done;
    itemEl.classList.toggle("task-done", isDone);
    const btn = itemEl.querySelector(".task-check");
    btn.classList.toggle("task-check-done", isDone);
    btn.textContent = isDone ? "✓" : "";
    // Move item to correct group by re-fetching
    const indexData = await api("GET", "/api/index");
    renderTasks(indexData.tasks || []);
  } catch (err) {
    showToast(err.message, true);
  }
}

// ── Wire up events ────────────────────────────────────────────────────────

btnScan.addEventListener("click", doScan);
btnAggregate.addEventListener("click", doAggregate);
$("btn-preview").addEventListener("click", doPreview);
$("btn-write").addEventListener("click", doWrite);
$("btn-index").addEventListener("click", doViewIndex);

// ── Boot ──────────────────────────────────────────────────────────────────

checkHealth();
setInterval(checkHealth, 30_000);
setPanel("empty");
loadTrackerSidebar();
setInterval(loadTrackerSidebar, 60_000);
