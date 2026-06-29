"use strict";

let _activeSystem = null;
let _activeEntity = null;

async function initializeTables() {
  try {
    const data = await api("GET", "/api/systems");
    _systems = data.systems || [];
    const select = $("table-system-select");
    select.replaceChildren();
    if (!_systems.length) {
      const option = document.createElement("option");
      option.textContent = "No systems";
      option.value = "";
      select.append(option);
      $("entity-tabs").replaceChildren();
      $("record-form").replaceChildren();
      $("dynamic-table").replaceChildren();
      return;
    }
    _systems.forEach(system => {
      const option = document.createElement("option");
      option.value = system.id;
      option.textContent = system.name;
      select.append(option);
    });
    await openSystem(Number(select.value));
  } catch (error) {
    showToast(error.message, true);
  }
}

async function openSystem(systemId) {
  setPanel("tables");
  showLoading("Loading system…");
  try {
    const data = await api("GET", `/api/systems/${systemId}`);
    _activeSystem = data.system;
    await syncSystemSelect(systemId);
    renderEntityTabs();
    if (_activeSystem.entities.length) {
      await selectEntity(_activeSystem.entities[0]);
    }
  } catch (error) {
    showToast(error.message, true);
  } finally {
    hideLoading();
  }
}

async function syncSystemSelect(systemId) {
  const select = $("table-system-select");
  if (![...select.options].some(option => Number(option.value) === systemId)) {
    const data = await api("GET", "/api/systems");
    _systems = data.systems || [];
    select.replaceChildren();
    _systems.forEach(system => {
      const option = document.createElement("option");
      option.value = system.id;
      option.textContent = system.name;
      select.append(option);
    });
  }
  select.value = String(systemId);
}

function renderEntityTabs() {
  const tabs = $("entity-tabs");
  tabs.replaceChildren();
  _activeSystem.entities.forEach(entity => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-secondary";
    button.textContent = entity.name;
    if (_activeEntity?.id === entity.id) button.classList.add("entity-tab-active");
    button.addEventListener("click", () => selectEntity(entity));
    tabs.append(button);
  });
}

async function selectEntity(entity) {
  _activeEntity = entity;
  renderEntityTabs();
  renderRecordForm();
  await loadRecords();
}

function renderRecordForm() {
  const form = $("record-form");
  form.replaceChildren();
  _activeEntity.fields.forEach(field => {
    const label = document.createElement("label");
    label.className = "field";
    const caption = document.createElement("span");
    caption.textContent = field.name + (field.required ? " *" : "");
    let input;
    if (field.type === "select") {
      input = document.createElement("select");
      if (!field.required) {
        const blank = document.createElement("option");
        blank.value = "";
        blank.textContent = "—";
        input.append(blank);
      }
      field.options.forEach(value => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        input.append(option);
      });
    } else if (field.type === "long_text") {
      input = document.createElement("textarea");
      input.rows = 2;
    } else {
      input = document.createElement("input");
      input.type = {
        number: "number", date: "date", boolean: "checkbox", text: "text",
      }[field.type] || "text";
      if (field.type === "number") input.step = "any";
    }
    input.name = field.key;
    input.required = field.required;
    input.dataset.fieldType = field.type;
    label.append(caption, input);
    form.append(label);
  });
  const actions = document.createElement("div");
  actions.className = "form-actions";
  const submit = document.createElement("button");
  submit.type = "submit";
  submit.className = "btn btn-primary";
  submit.textContent = "Add Record";
  actions.append(submit);
  form.append(actions);
}

function recordValues() {
  const values = {};
  _activeEntity.fields.forEach(field => {
    const input = $("record-form").elements.namedItem(field.key);
    if (field.type === "boolean") {
      values[field.key] = input.checked;
    } else if (input.value !== "") {
      values[field.key] = field.type === "number" ? Number(input.value) : input.value;
    }
  });
  return values;
}

$("record-form").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    await api("POST", `/api/entities/${_activeEntity.id}/records`, { values: recordValues() });
    event.currentTarget.reset();
    showToast("Record added");
    await loadRecords();
  } catch (error) {
    showToast(error.message, true);
  }
});

async function loadRecords() {
  const data = await api("GET", `/api/entities/${_activeEntity.id}/records`);
  renderRecords(data.records || []);
}

function renderRecords(records) {
  const table = $("dynamic-table");
  table.replaceChildren();
  const head = document.createElement("thead");
  const headerRow = document.createElement("tr");
  _activeEntity.fields.forEach(field => {
    const th = document.createElement("th");
    th.textContent = field.name;
    headerRow.append(th);
  });
  const actionHeader = document.createElement("th");
  actionHeader.textContent = "Actions";
  headerRow.append(actionHeader);
  head.append(headerRow);
  table.append(head);

  const body = document.createElement("tbody");
  if (!records.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = _activeEntity.fields.length + 1;
    cell.textContent = "No records yet.";
    row.append(cell);
    body.append(row);
  }
  records.forEach(record => {
    const row = document.createElement("tr");
    _activeEntity.fields.forEach(field => {
      const cell = document.createElement("td");
      const value = record.values[field.key];
      cell.textContent = value === null || value === undefined ? "" : (
        typeof value === "boolean" ? (value ? "✓" : "—") : String(value)
      );
      row.append(cell);
    });
    const actions = document.createElement("td");
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "btn btn-ghost";
    remove.textContent = "Delete";
    remove.addEventListener("click", async () => {
      try {
        await api("DELETE", `/api/records/${record.id}`);
        await loadRecords();
      } catch (error) {
        showToast(error.message, true);
      }
    });
    actions.append(remove);
    row.append(actions);
    body.append(row);
  });
  table.append(body);
}

$("table-system-select").addEventListener("change", event => {
  if (event.target.value) openSystem(Number(event.target.value));
});

$("btn-export-system").addEventListener("click", async () => {
  if (!_activeSystem) return;
  try {
    const data = await api("POST", `/api/systems/${_activeSystem.id}/export`, { preview: true });
    $("export-preview-content").textContent = data.preview.system_markdown;
    $("export-preview").hidden = false;
    $("export-preview").scrollIntoView({ behavior: "smooth" });
  } catch (error) {
    showToast(error.message, true);
  }
});

$("btn-confirm-export").addEventListener("click", async () => {
  try {
    const data = await api("POST", `/api/systems/${_activeSystem.id}/export`, {});
    $("export-preview").hidden = true;
    showToast(`Written to ${data.export.path}`);
  } catch (error) {
    showToast(error.message, true);
  }
});
