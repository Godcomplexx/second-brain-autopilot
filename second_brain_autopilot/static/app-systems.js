"use strict";

let _systems = [];
let _draftConfig = null;
let _lastSystemRequest = null;

async function loadSystems() {
  const target = $("system-list");
  try {
    const data = await api("GET", "/api/systems");
    _systems = data.systems || [];
    target.replaceChildren();
    if (!_systems.length) {
      const empty = document.createElement("div");
      empty.className = "empty-card card";
      empty.textContent = "No systems yet. Create one from a goal prompt.";
      target.append(empty);
      return;
    }
    _systems.forEach(system => {
      const card = document.createElement("article");
      card.className = "system-card card";
      card.tabIndex = 0;
      const title = document.createElement("h3");
      title.textContent = system.name;
      const description = document.createElement("p");
      description.textContent = system.description || "No description";
      const meta = document.createElement("div");
      meta.className = "system-meta";
      meta.textContent = `${system.entity_count} tables · ${system.record_count} records`;
      card.append(title, description, meta);
      const open = () => openSystem(Number(system.id));
      card.addEventListener("click", open);
      card.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") open();
      });
      target.append(card);
    });
  } catch (error) {
    showToast(error.message, true);
  }
}

function systemFormRequest() {
  const form = $("system-form");
  const data = new FormData(form);
  return Object.fromEntries([...data.entries()].map(([key, value]) => [key, String(value)]));
}

async function generateSystem() {
  _lastSystemRequest = systemFormRequest();
  showLoading("Designing tracking system…");
  try {
    const data = await api("POST", "/api/systems/generate", _lastSystemRequest);
    _draftConfig = data.config;
    $("system-config-json").value = JSON.stringify(_draftConfig, null, 2);
    $("config-preview").hidden = false;
    $("config-preview").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showToast(error.message, true);
  } finally {
    hideLoading();
  }
}

$("system-form").addEventListener("submit", async event => {
  event.preventDefault();
  await generateSystem();
});

$("btn-regenerate").addEventListener("click", generateSystem);

$("btn-approve-system").addEventListener("click", async () => {
  let config;
  try {
    config = JSON.parse($("system-config-json").value);
  } catch (error) {
    showToast(`Invalid JSON: ${error.message}`, true);
    return;
  }
  showLoading("Saving system…");
  try {
    const data = await api("POST", "/api/systems", {
      config,
      source_prompt: _lastSystemRequest?.main_goal || "",
    });
    showToast("System created");
    $("config-preview").hidden = true;
    $("system-form").reset();
    await openSystem(Number(data.system.id));
  } catch (error) {
    showToast(error.message, true);
  } finally {
    hideLoading();
  }
});
