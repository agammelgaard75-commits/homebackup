const api = "/api/encounter-builder";
const $ = (id) => document.getElementById(id);
let currentId = null;
let templates = [];
let calculationSequence = 0;

function input(label, type, value, options = {}) {
  const wrapper = document.createElement("label");
  wrapper.textContent = label;
  const field = document.createElement("input");
  field.type = type;
  field.value = value;
  for (const [key, item] of Object.entries(options)) field.setAttribute(key, String(item));
  field.addEventListener("input", calculate);
  wrapper.append(field);
  return [wrapper, field];
}

function addCreature(data = {}) {
  const row = document.createElement("div");
  row.className = "creature-row";
  const [nameLabel, name] = input("Creature name", "text", data.name ?? "", { maxlength: 120, placeholder: "Creature name" });
  const [levelLabel, level] = input("Level", "number", data.level ?? Number($("party-level").value), { min: -1, max: 25, step: 1 });
  const [quantityLabel, quantity] = input("Quantity", "number", data.quantity ?? 1, { min: 1, step: 1 });
  const [notesLabel, notes] = input("Notes", "text", data.notes ?? "", { maxlength: 1000, placeholder: "Optional" });
  const [urlLabel, url] = input("Creature URL", "url", data.url ?? "", { maxlength: 500, placeholder: "Optional https://…" });
  const xp = document.createElement("output");
  xp.className = "creature-xp";
  const reference = document.createElement("a");
  reference.textContent = "Open creature reference";
  reference.target = "_blank";
  reference.rel = "noopener noreferrer";
  reference.className = "creature-reference";
  function updateReference() {
    const value = url.value.trim();
    const valid = /^https?:\/\/[^\s/]+/i.test(value);
    reference.hidden = !valid;
    if (valid) reference.href = value;
    else reference.removeAttribute("href");
  }
  url.addEventListener("input", updateReference);
  updateReference();
  const remove = document.createElement("button");
  remove.type = "button";
  remove.textContent = "Remove";
  remove.addEventListener("click", () => { row.remove(); calculate(); });
  row.append(nameLabel, levelLabel, quantityLabel, notesLabel, urlLabel, xp, reference, remove);
  row.fields = { name, level, quantity, notes, url };
  row.xp = xp;
  $("creature-list").append(row);
  calculate();
}

function integer(value) {
  return /^-?\d+$/.test(value.trim()) ? Number(value) : null;
}

function creatureValues() {
  return [...$("creature-list").children].map((row) => ({
    name: row.fields.name.value.trim(),
    level: integer(row.fields.level.value),
    quantity: integer(row.fields.quantity.value),
    notes: row.fields.notes.value,
    url: row.fields.url.value.trim(),
  }));
}

function values() {
  return {
    party_level: Number($("party-level").value),
    party_size: Number($("party-size").value),
    target: $("target").value,
    creatures: creatureValues(),
  };
}

function saveValues() {
  return { ...values(), name: $("encounter-name").value.trim(), notes: $("encounter-notes").value };
}

async function request(path, options = {}) {
  const response = await fetch(api + path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body.detail;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status}). Check the entered values.`);
  }
  return response.status === 204 ? null : response.json();
}

function setText(id, value) { $(id).textContent = String(value); }
function signed(value) { return value > 0 ? `+${value}` : String(value); }

function render(result) {
  const unavailable = result.total_xp === null;
  setText("total-xp", unavailable ? "—" : result.total_xp);
  setText("selected-target", result.target);
  setText("adjusted-target", result.adjusted_target);
  setText("remaining-xp", unavailable ? "—" : result.remaining_xp);
  setText("difference-xp", unavailable ? "—" : signed(result.difference_from_target));
  setText("comparison", result.comparison);
  setText("award-guidance", result.award_guidance);
  $("total-xp").classList.toggle("over-budget", result.difference_from_target > 0);
  $("difference-xp").classList.toggle("over-budget", result.difference_from_target > 0);
  $("budget-list").replaceChildren();
  for (const [name, amount] of Object.entries(result.budgets)) {
    const item = document.createElement("span");
    const difference = result.total_xp === null ? "" : ` · ${result.total_xp === amount ? "matches" : `${Math.abs(result.total_xp - amount)} ${result.total_xp > amount ? "above" : "below"}`}`;
    item.textContent = `${name}: ${amount} XP${difference}`;
    if (name === result.target) item.className = "selected-budget";
    $("budget-list").append(item);
  }
  $("warnings").replaceChildren();
  for (const message of result.warnings) {
    const item = document.createElement("li");
    item.textContent = message;
    $("warnings").append(item);
  }
  [...$("creature-list").children].forEach((row, index) => {
    const group = result.creatures[index];
    row.xp.textContent = group.xp_total === null ? "Unsupported level difference" : `${group.xp_each} XP each · ${group.xp_total} XP total`;
  });
}

async function calculate() {
  const sequence = ++calculationSequence;
  const creatures = creatureValues();
  const bad = creatures.some((item) => !item.name || !Number.isInteger(item.level) || item.level < -1 || item.level > 25 || !Number.isInteger(item.quantity) || item.quantity < 1 || (item.url && !/^https?:\/\/[^\s/]+/i.test(item.url)));
  if (bad) {
    $("calculation-error").hidden = false;
    setText("calculation-error", "Complete creature names, levels (−1 to 25), positive quantities, and valid URLs to calculate XP.");
    setText("total-xp", "—");
    setText("remaining-xp", "—");
    setText("difference-xp", "—");
    return;
  }
  try {
    const result = await request("/calculate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values()) });
    if (sequence !== calculationSequence) return;
    $("calculation-error").hidden = true;
    render(result);
  } catch (error) {
    if (sequence !== calculationSequence) return;
    $("calculation-error").hidden = false;
    setText("calculation-error", error.message);
  }
}

async function updateTemplates() {
  try {
    templates = await request(`/templates?party_level=${$("party-level").value}`);
    $("template").replaceChildren(new Option("Choose a template", ""));
    for (const template of templates) $("template").append(new Option(template.name, template.id));
  } catch (error) { setText("save-status", error.message); }
}

async function refreshSaved(selectedId = currentId) {
  const entries = await request("/encounters");
  $("saved-list").replaceChildren(new Option("Choose saved encounter", ""));
  for (const item of entries) $("saved-list").append(new Option(item.name, String(item.id)));
  $("saved-list").value = selectedId === null ? "" : String(selectedId);
}

function setCurrent(id) {
  currentId = id;
  for (const name of ["resave-encounter", "duplicate-encounter", "delete-encounter"]) $(name).disabled = id === null;
}

function loadData(data) {
  setCurrent(data.id);
  $("encounter-name").value = data.name;
  $("encounter-notes").value = data.notes;
  $("party-level").value = data.party_level;
  $("party-size").value = data.party_size;
  $("target").value = data.target;
  $("creature-list").replaceChildren();
  for (const creature of data.creatures) addCreature(creature);
  updateTemplates();
  calculate();
}

async function save(method, path) {
  try {
    const payload = saveValues();
    if (!payload.name) throw new Error("Enter an encounter name before saving.");
    const data = await request(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    setCurrent(data.id);
    await refreshSaved(data.id);
    setText("save-status", `Saved “${data.name}”.`);
  } catch (error) { setText("save-status", error.message); }
}

for (const id of ["party-level", "party-size", "target"]) $(id).addEventListener("change", calculate);
$("party-level").addEventListener("change", updateTemplates);
$("add-creature").addEventListener("click", () => addCreature());
$("apply-template").addEventListener("click", () => {
  const template = templates.find((item) => item.id === $("template").value);
  if (!template) return;
  $("creature-list").replaceChildren();
  for (const creature of template.creatures) addCreature(creature);
});
$("save-encounter").addEventListener("click", () => save("POST", "/encounters"));
$("resave-encounter").addEventListener("click", () => { if (currentId !== null) save("PUT", `/encounters/${currentId}`); });
$("load-encounter").addEventListener("click", async () => {
  if (!$("saved-list").value) return;
  try { const data = await request(`/encounters/${$("saved-list").value}`); loadData(data); setText("save-status", `Loaded “${data.name}”.`); }
  catch (error) { setText("save-status", error.message); }
});
$("duplicate-encounter").addEventListener("click", async () => {
  if (currentId === null) return;
  try { const data = await request(`/encounters/${currentId}/duplicate`, { method: "POST" }); loadData(data); await refreshSaved(data.id); setText("save-status", `Duplicated as “${data.name}”.`); }
  catch (error) { setText("save-status", error.message); }
});
$("delete-encounter").addEventListener("click", async () => {
  if (currentId === null || !window.confirm("Delete this saved encounter?")) return;
  try { await request(`/encounters/${currentId}`, { method: "DELETE" }); setCurrent(null); await refreshSaved(); setText("save-status", "Saved encounter deleted. The current form remains available."); }
  catch (error) { setText("save-status", error.message); }
});
updateTemplates();
refreshSaved().catch((error) => setText("save-status", error.message));
calculate();
