// ── Batch result ──────────────────────────────────────────────────────────

"use strict";

function renderBatchResult(results) {
  $("result-meta").textContent = `Batch: ${results.length} notes`;

  const cards = results.map(job => {
    const src = (job.sources || [])[0] || "?";
    const name = src.split("/").pop().replace(/\.md$/, "");
    const r = job.result || {};
    const segs = (r.segments || []).length;
    const tasks = (r.tasks || []).length;
    const hasError = r.parse_error || r.error;

    if (hasError) {
      return `<div class="card batch-card batch-card-err">
        <div class="seg-topic">${escHtml(name)}</div>
        <div class="seg-reason">⚠ ${escHtml(r.error || "Parse error")}</div>
      </div>`;
    }
    return `<div class="card batch-card">
      <div class="seg-header">
        <span class="seg-topic">${escHtml(name)}</span>
        <span class="seg-reason">${segs} segment${segs !== 1 ? "s" : ""} · ${tasks} task${tasks !== 1 ? "s" : ""}</span>
      </div>
      <div class="batch-actions">
        <button class="btn btn-secondary btn-sm batch-view-btn" data-src="${escHtml(src)}">View &amp; Write</button>
      </div>
    </div>`;
  }).join("");

  setSafeHtml($("segments-area"), cards);
  $("btn-preview").disabled = true;
  $("btn-write").disabled = true;
  $("write-preview").hidden = true;
  $("write-done").hidden = true;
  $("write-actions").hidden = true;

  document.querySelectorAll(".batch-view-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const src = btn.dataset.src;
      const job = _batchResults.find(j => (j.sources || [])[0] === src);
      if (!job) return;
      _lastResult = job;
      _batchResults = [];
      renderResult(job);
      $("write-actions").hidden = false;
    });
  });
}

// ── Render result ──────────────────────────────────────────────────────────

function renderResult(data) {
  const r = data.result || {};
  $("result-meta").textContent = `Source: ${data.sources.join(", ")}`;

  if (r.parse_error) {
    setSafeHtml($("segments-area"), `
      <div class="card error-card">
        <h3>⚠ Could not parse LLM response</h3>
        <pre>${escHtml(r.raw_response || data.raw_llm || "")}</pre>
      </div>`);
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
        tasks.map(t => `<li>- [ ] ${escHtml(t.text)}${t.due ? ` 📅 ${escHtml(t.due)}` : ""}</li>`).join("")
      }</ul></div>`
    : "";

  // Habit detection summary
  const habits = r.habits || {};
  const habitKeys = Object.keys(habits).filter(k => habits[k] > 0);
  const habitsSummary = habitKeys.length
    ? `<div class="tasks-summary"><strong>📊 Habits detected</strong>
        <span class="habits-source-note">will be written back to source note</span>
        <ul>${
          habitKeys.map(k => {
            const h = HABITS.find(h => h.key === k);
            const color = h?.color || "#000000";
            return `<li style="color:${color}">${escHtml(h?.label || k)}: ${escHtml(habits[k])}</li>`;
          }).join("")
        }</ul></div>`
    : "";

  // Segment cards with editable textarea for content
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
      <details class="seg-preview" open>
        <summary>Edit content</summary>
        <textarea class="seg-content" data-idx="${i}" rows="8">${escHtml(seg.content)}</textarea>
      </details>
    </div>`;
  }).join("");

  setSafeHtml($("segments-area"), segCards + tasksSummary + habitsSummary);

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
  document.querySelectorAll(".seg-content").forEach(el => {
    el.addEventListener("input", () => {
      _segments[+el.dataset.idx].content = el.value;
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
      const lines = habitKeys.map(k => `<li>${escHtml(k)}:: ${escHtml(habits[k])}</li>`).join("");
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
    setSafeHtml(box, html);
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
  setSafeHtml(btnWrite, `Writing… <span class="btn-spinner"></span>`);
  showLoading("Writing to vault…");

  try {
    const scanNote = _notes.find(n => n.rel_path === source);
    const res = await api("POST", "/api/write", {
      source_rel: source,
      scan_hash: scanNote?.hash || "",
      segments: serializeSegments(),
      tasks,
      habits,
    });

    const written = res.written || [];
    const paths = written.map(w => w.target_path);
    const taskCount = res.tasks_written?.written || 0;
    const habitsUpdated = res.habits_written ? " · habits updated" : "";

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
    btnWrite.textContent = "Approve & Write All";
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
        html += `<li><strong>${escHtml(k)}</strong> → ${(rec.targets || []).map(escHtml).join(", ")} <em>(${escHtml(rec.processed_at || "")})</em></li>`;
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
    setSafeHtml($("index-content"), html);
    setPanel("index");
  } catch (err) {
    showToast(err.message, true);
  } finally {
    hideLoading();
  }
}

