"use strict";

document.querySelectorAll(".nav-button").forEach(button => {
  button.addEventListener("click", async () => {
    const panel = button.dataset.panel;
    setPanel(panel);
    if (panel === "dashboard") await loadSystems();
    if (panel === "tables") await initializeTables();
  });
});

$("btn-new-system").addEventListener("click", () => setPanel("create-system"));
