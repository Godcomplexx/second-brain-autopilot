// ── Wire up events ────────────────────────────────────────────────────────

"use strict";

btnScan.addEventListener("click", doScan);
btnAggregate.addEventListener("click", doAggregate);
$("btn-preview").addEventListener("click", doPreview);
$("btn-write").addEventListener("click", doWrite);
$("btn-index").addEventListener("click", doViewIndex);
noteSearch?.addEventListener("input", renderNoteList);

// ── Boot ──────────────────────────────────────────────────────────────────

checkHealth();
setInterval(checkHealth, 30_000);
setPanel("dashboard");
loadSystems();
loadTrackerSidebar();
setInterval(loadTrackerSidebar, 60_000);
