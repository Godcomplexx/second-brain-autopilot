// ── Tracker sidebar ───────────────────────────────────────────────────────

"use strict";

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
    setSafeHtml($("ts-habits"), `<div class="ts-empty">Unavailable</div>`);
    setSafeHtml($("ts-tasks"), `<div class="ts-empty">Unavailable</div>`);
  }
}

function renderHabitsSidebar(data) {
  const today = new Date().toISOString().slice(0, 10);
  const days = getLast7Days();
  const byDate = Object.fromEntries(data.map(d => [d.date, d]));

  const d = new Date();
  $("ts-date").textContent = d.toLocaleDateString("en", { weekday: "short", day: "numeric", month: "short" });

  setSafeHtml($("ts-habits"), HABITS.map(h => {
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
  }).join(""));

  $("ts-habits").querySelectorAll(".ts-day-today").forEach(dot => {
    dot.addEventListener("click", async () => {
      try {
        await api("POST", "/api/habits/toggle", { key: dot.dataset.key, value: parseInt(dot.dataset.val) });
        loadTrackerSidebar();
      } catch (err) { showToast(err.message, true); }
    });
  });
}

// Sort order: high → medium → low → no priority, then by due date
const PRIORITY_ORDER = { high: 0, medium: 1, low: 2, "": 3, undefined: 3 };

function sortTasks(tasks) {
  return [...tasks].sort((a, b) => {
    const pa = PRIORITY_ORDER[a.priority] ?? 3;
    const pb = PRIORITY_ORDER[b.priority] ?? 3;
    if (pa !== pb) return pa - pb;
    // tasks with a due date come before those without
    if (a.due && !b.due) return -1;
    if (!a.due && b.due) return 1;
    if (a.due && b.due) return a.due.localeCompare(b.due);
    return 0;
  });
}

function renderTasksSidebar(tasks) {
  const open = sortTasks(tasks.filter(t => !t.done));
  const el = $("ts-tasks");
  const badge = $("ts-task-count");
  badge.textContent = open.length || "";
  badge.hidden = open.length === 0;

  if (open.length === 0) {
    setSafeHtml(el, `<div class="ts-empty">All done</div>`);
    return;
  }

  setSafeHtml(el, open.map(t => {
    const pri = { high: "🔴", medium: "🟡", low: "🟢" }[t.priority] || "";
    const due = t.due ? `<span class="ts-task-due">📅 ${escHtml(t.due)}</span>` : "";
    return `
    <div class="ts-task-row" data-text="${escHtml(t.text)}" data-source="${escHtml(t.source || "")}">
      <button class="ts-task-check" title="Mark done"></button>
      <span class="ts-task-text">${pri ? pri + " " : ""}${escHtml(t.text)}${due ? " " + due : ""}</span>
    </div>`;
  }).join(""));

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

// ── Task tracker (main panel) ─────────────────────────────────────────────

function renderTasks(tasks) {
  const el = $("tracker-tasks");
  if (tasks.length === 0) {
    setSafeHtml(el, `<p class="tracker-empty">No tasks extracted yet — process a daily note first.</p>`);
    return;
  }

  const open = sortTasks(tasks.filter(t => !t.done));
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

  setSafeHtml(el, html);

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
    const indexData = await api("GET", "/api/index");
    renderTasks(indexData.tasks || []);
  } catch (err) {
    showToast(err.message, true);
  }
}

