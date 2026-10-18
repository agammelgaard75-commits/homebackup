const api = "/api/combat-tracker";
const $ = (id) => document.getElementById(id);
let combat = null;
let selectedId = null;
let queue = Promise.resolve();
let conditionSummary = {};
let conditionLibrary = [];
let conditionReminders = [];
async function conditionRequest(path, method = "GET", data = null) {
  const response = await fetch(`/api/conditions${path}`, {method, headers: data === null ? {} : {"Content-Type":"application/json"}, body: data === null ? undefined : JSON.stringify(data)});
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(typeof body.detail === "string" ? body.detail : `Condition request failed (${response.status})`); }
  return response.status === 204 ? null : response.json();
}
async function refreshConditions() {
  if (!combat) { conditionSummary = {}; return; }
  conditionSummary = await conditionRequest(`/combat/${combat.id}/summary`);
  render();
}
function conditionLabel(row) { return (conditionLibrary.find(def => def.slug === row.slug)?.name || row.slug) + (row.value ? ` ${row.value}` : ""); }
function renderConditionReminders() {
  const box = $("condition-reminders"); if (!box) return;
  box.replaceChildren();
  if (!conditionReminders.length) { box.append(element("p", "No turn reminders.", "hint")); return; }
  for (const row of conditionReminders) {
    const line = element("div", row.text, "condition-reminder");
    if (row.kind === "reduce") line.append(button("Confirm reduction", async () => { try { await conditionRequest(`/active/${row.instance_id}/reduce`, "POST", {amount:1}); conditionReminders = conditionReminders.filter(item => item !== row); await refreshConditions(); renderConditionReminders(); } catch(error) { message(error.message,true); } }));
    if (row.kind === "stunned_reduce") line.append(button("Confirm Stunned action loss", async () => { try { await conditionRequest(`/active/${row.instance_id}/reduce`, "POST", {amount:row.amount}); conditionReminders = conditionReminders.filter(item => item !== row); await refreshConditions(); renderConditionReminders(); } catch(error) { message(error.message,true); } }));
    if (row.kind === "persistent") for (const [label, success] of [["Recovery failed",false],["Recovery succeeded",true]]) line.append(button(label, async () => { try { await conditionRequest(`/active/${row.instance_id}/recovery`, "POST", {success}); conditionReminders = conditionReminders.filter(item => item !== row); await refreshConditions(); renderConditionReminders(); } catch(error) { message(error.message,true); } }));
    if (row.kind === "persistent_choice") line.append(button("Choose source", () => { location.href = `/tools/conditions?combat_id=${combat.id}&combatant_id=${row.combatant_id}&condition=persistent-damage`; }));
    if (row.kind === "expiration") line.append(button("Confirm end", async () => { try { await conditionRequest(`/active/${row.instance_id}`, "DELETE"); conditionReminders = conditionReminders.filter(item => item !== row); await refreshConditions(); renderConditionReminders(); } catch(error) { message(error.message,true); } }));
    if (row.kind === "round") line.append(button("Review in Conditions Tracker", () => { location.href = `/tools/conditions?combat_id=${combat.id}&combatant_id=${row.combatant_id}`; }));
    if (row.kind === "healing_recovery") line.append(button("Open recovery check", () => { location.href = `/tools/healing-death?combat_id=${combat.id}&combatant_id=${row.combatant_id}`; }));
    box.append(line);
  }
}
async function collectTurnReminders(event, actorId) {
  if (!combat || actorId === null) return [];
  const result = [];
  for (const actor of combat.combatants) {
    const rows = await conditionRequest(`/reminders?${new URLSearchParams({combat_id:combat.id,combatant_id:actor.id,event,actor_id:actorId})}`);
    result.push(...rows.map(row => ({...row,combatant_id:actor.id})));
  }
  if (event === "start") {
    try {
      const response = await fetch(`/api/healing-death/combat/${combat.id}/reminders?actor_id=${actorId}`);
      if (response.ok) result.push(...(await response.json()));
    } catch (_) { /* The combat tracker remains usable independently. */ }
  }
  return result;
}

async function request(path, method = "GET", data = null) {
  const response = await fetch(api + path, {
    method,
    headers: data === null ? {} : { "Content-Type": "application/json" },
    body: data === null ? undefined : JSON.stringify(data),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${response.status}). Check the entered values.`);
  }
  return response.status === 204 ? null : response.json();
}

function message(text, error = false) {
  $("combat-message").textContent = text;
  $("combat-message").classList.toggle("error", error);
}

function numberOrNull(value) {
  return value.trim() === "" ? null : /^-?\d+$/.test(value.trim()) ? Number(value) : value.trim();
}

function actor(id) { return combat?.combatants.find((item) => item.id === id); }
function element(tag, text = "", className = "") {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}
function button(text, click, className = "") {
  const node = element("button", text, className);
  node.type = "button";
  node.addEventListener("click", click);
  return node;
}
function labelInput(label, type, value, onChange, options = {}) {
  const wrapper = element("label", label);
  const field = document.createElement("input");
  field.type = type;
  field.value = value ?? "";
  for (const [key, val] of Object.entries(options)) if (val !== false && val !== null && val !== undefined) field.setAttribute(key, val === true ? "" : String(val));
  field.addEventListener("change", () => onChange(field.value));
  wrapper.append(field);
  return wrapper;
}

function send(command) {
  if (!combat) return;
  const id = combat.id;
  queue = queue.catch(() => {}).then(async () => {
    try {
      const transition = ["next_turn", "ready", "delay"].includes(command.op);
      const outgoing = ["next_turn", "ready"].includes(command.op) ? combat.active_id : null;
      const endPrompts = outgoing === null ? [] : await collectTurnReminders("end", outgoing).catch(() => []);
      const updated = await request(`/combats/${id}/command`, "POST", command);
      if (combat?.id === id) {
        combat = updated;
        if (transition) conditionReminders = endPrompts;
        const incoming = updated.active_id;
        if (transition && incoming !== null) conditionReminders.push(...await collectTurnReminders("start", incoming).catch(() => []));
        render();
        renderConditionReminders();
        await refreshConditions();
        message("Saved automatically.");
        if (["rename_combat", "end", "resume"].includes(command.op)) refreshCombats(id);
      }
    } catch (error) { message(error.message, true); }
  });
}

async function refreshCombats(selectId = combat?.id) {
  const rows = await request("/combats");
  $("combat-list").replaceChildren(new Option("Choose saved combat", ""));
  for (const row of rows) $("combat-list").append(new Option(`${row.name} (${row.status})`, String(row.id)));
  $("combat-list").value = selectId === null || selectId === undefined ? "" : String(selectId);
}

async function refreshSources() {
  const rows = await request("/encounter-definitions");
  $("source-list").replaceChildren(new Option("Choose saved encounter", ""));
  for (const row of rows) $("source-list").append(new Option(row.name, String(row.id)));
}

function loadState(data) {
  combat = data;
  conditionSummary = {};
  selectedId = data.active_id ?? data.combatants[0]?.id ?? null;
  localStorage.setItem("pf2e-current-combat", String(data.id));
  render();
  conditionReminders = [];
  refreshConditions().catch((error) => message(error.message, true));
  if (data.active_id !== null) {
    fetch(`/api/healing-death/combat/${data.id}/reminders?actor_id=${data.active_id}`).then(response => response.ok ? response.json() : []).then(rows => { if (combat?.id === data.id) { conditionReminders.push(...rows); renderConditionReminders(); } }).catch(() => {});
  }
}

function render() {
  $("workspace").hidden = !combat;
  if (!combat) return;
  if (!actor(selectedId)) selectedId = combat.active_id ?? combat.combatants[0]?.id ?? null;
  const ended = combat.status === "ended";
  $("combat-name").value = combat.name;
  $("combat-status").textContent = ended ? "Ended · saved history" : "Active · autosaved";
  $("round-number").textContent = String(combat.round);
  $("active-name").textContent = actor(combat.active_id)?.name ?? "No combatants";
  $("end-combat").hidden = ended;
  $("resume-combat").hidden = !ended;
  $("combat-rewards").hidden = !ended;
  $("combat-rewards").href = `/tools/treasure-xp?combat_id=${combat.id}`;
  for (const id of ["next-turn", "add-combatant", "save-combat", "rename-combat"]) $(id).disabled = ended;
  $("next-turn").disabled = ended || combat.active_id === null;
  renderOrder(ended);
  renderActive(ended);
  renderSelected(ended);
  renderConditionReminders();
}

function renderOrder(ended) {
  const list = $("initiative-list");
  list.replaceChildren();
  if (!combat.order.length) list.append(element("p", "Add a combatant to start the turn order.", "hint"));
  for (const id of combat.order) {
    if (combat.delayed.includes(id)) continue;
    const item = actor(id);
    const row = element("div", "", `initiative-row ${item.type.toLowerCase()}${id === combat.active_id ? " active" : ""}${item.current_hp === 0 ? " zero-hp" : ""}${combat.delayed.includes(id) ? " delayed" : ""}`);
    const head = element("div", "", "row-head");
    const select = button(item.name, () => { selectedId = id; render(); }, "actor-name");
    select.setAttribute("aria-label", `Select ${item.name}`);
    head.append(select, element("span", item.type, "kind"));
    if (id === combat.active_id) head.append(element("strong", "Active", "active-tag"));
    if (item.current_hp === 0) head.append(element("strong", "0 HP — review knockout/dying", "zero-tag"));
    const fields = element("div", "", "row-fields");
    fields.append(
      labelInput("Initiative", "number", item.initiative, (value) => send({ op: "set_initiative", combatant_id: id, initiative: numberOrNull(value) }), { disabled: ended }),
      labelInput("Current HP", "number", item.current_hp, (value) => send({ op: "set_hp", combatant_id: id, current_hp: numberOrNull(value) }), { min: 0, disabled: ended }),
      labelInput("Max HP", "number", item.max_hp, (value) => send({ op: "set_hp", combatant_id: id, max_hp: numberOrNull(value) }), { min: 1, disabled: ended }),
      labelInput("Temp HP", "number", item.temp_hp, (value) => send({ op: "set_hp", combatant_id: id, temp_hp: numberOrNull(value) }), { min: 0, disabled: ended }),
    );
    const detail = element("div", "", "row-detail");
    detail.textContent = [item.effects.map((effect) => effect.duration ? `${effect.label} (${effect.duration})` : effect.label).join(" · "), item.notes].filter(Boolean).join(" · ");
    for (const condition of (conditionSummary[String(id)]?.visible || []).filter(row => !row.overridden)) {
      const link = element("a", conditionLabel(condition), "combat-condition");
      link.href = `/tools/conditions?combat_id=${combat.id}&combatant_id=${id}&condition=${condition.slug}`;
      link.title = "Open condition details";
      detail.append(link);
    }
    const actions = element("div", "", "row-buttons");
    actions.append(button("↑", () => send({ op: "move", combatant_id: id, direction: "up" })), button("↓", () => send({ op: "move", combatant_id: id, direction: "down" })), button("Remove", () => send({ op: "remove", combatant_id: id })));
    for (const child of actions.children) child.disabled = ended;
    row.append(head, fields, detail, actions);
    list.append(row);
  }
  const delayed = $("delayed-list");
  delayed.replaceChildren();
  if (!combat.delayed.length) delayed.append(element("p", "No delayed combatants.", "hint"));
  for (const id of combat.delayed) {
    const row = element("div", "", "delay-row");
    row.append(element("strong", actor(id).name));
    const select = document.createElement("select");
    const originalIndex = combat.pending.indexOf(id);
    const choices = originalIndex < 0 ? combat.pending : combat.pending.slice(0, originalIndex);
    for (const after of choices) select.append(new Option(`After ${actor(after).name}`, String(after)));
    const reenter = button("Reenter at chosen point", () => send({ op: "reenter", combatant_id: id, after_id: Number(select.value) }));
    reenter.disabled = ended || !choices.length;
    row.append(select, reenter);
    delayed.append(row);
  }
}

function renderActive(ended) {
  const container = $("active-controls");
  container.replaceChildren();
  const current = actor(combat.active_id);
  if (!current) { container.append(element("p", "Add combatants to begin.")); return; }
  const actions = element("p", `Actions: ${"●".repeat(Math.min(current.actions_remaining, 3))}${"○".repeat(Math.max(0, 3 - current.actions_remaining))}${current.actions_remaining > 3 ? ` +${current.actions_remaining - 3}` : ""} (${current.actions_remaining} available)`, "action-indicators");
  const reaction = element("p", `Reaction: ${current.reaction_remaining > 0 ? "●" : "○"} (${current.reaction_remaining} available)`, "reaction-indicator");
  const conditionActions = conditionSummary[String(current.id)]?.actions;
  if (conditionActions && (conditionActions.slowed || conditionActions.stunned || conditionActions.quickened_extra)) {
    container.append(element("p", `Condition guidance at turn start: ${conditionActions.total_guidance} action(s) after ${conditionActions.actions_lost} lost; Quickened can add at most ${conditionActions.quickened_extra} restricted action. Choose which action is lost and adjust counters manually.`, "condition-reminder"));
  }
  const controls = element("div", "", "control-buttons");
  controls.append(
    button("Spend action", () => send({ op: "actions", combatant_id: current.id, amount: -1 })),
    button("Restore action", () => send({ op: "actions", combatant_id: current.id, amount: 1 })),
    button("Spend reaction", () => send({ op: "reaction", combatant_id: current.id, amount: -1 })),
    button("Restore reaction", () => send({ op: "reaction", combatant_id: current.id, amount: 1 })),
  );
  const map = element("div", "", "map-box");
  map.append(element("strong", `Attack actions used this turn: ${current.attack_count}`));
  map.append(element("p", `Next attack MAP: standard ${current.map_standard}, agile ${current.map_agile}. Use the value for the attack used now.`));
  const attackControls = element("div", "", "control-buttons");
  attackControls.append(button("Attack +", () => send({ op: "attack", combatant_id: current.id, amount: 1 })), button("Attack −", () => send({ op: "attack", combatant_id: current.id, amount: -1 })));
  map.append(attackControls);
  const turnControls = element("div", "", "control-buttons turn-controls");
  turnControls.append(button("End Turn / Next Turn", () => send({ op: "next_turn" }), "next-turn"), button("Delay", () => send({ op: "delay" })), button("Ready (2 actions, end turn)", () => send({ op: "ready", combatant_id: current.id })));
  for (const group of [controls, attackControls, turnControls]) for (const child of group.children) child.disabled = ended;
  container.append(actions, reaction, controls, map, turnControls);
  container.append(element("p", "Ready does not change initiative. Record the readied trigger in a note; a readied attack can use the MAP present when Ready was used. Delay is triggered at the start of a turn, before taking actions.", "hint"));
}

function renderSelected(ended) {
  const box = $("selected-detail");
  box.replaceChildren();
  const item = actor(selectedId);
  if (!item) { box.append(element("p", "Select a combatant.")); return; }
  const name = labelInput("Name", "text", item.name, (value) => send({ op: "set_name", combatant_id: item.id, name: value }), { maxlength: 120, disabled: ended });
  const typeLabel = element("label", "Type");
  const type = document.createElement("select");
  for (const kind of ["PC", "NPC", "monster"]) type.append(new Option(kind, kind));
  type.value = item.type;
  type.disabled = ended;
  type.addEventListener("change", () => send({ op: "set_type", combatant_id: item.id, type: type.value }));
  typeLabel.append(type);
  const hp = element("p", `HP ${item.current_hp ?? "?"} / ${item.max_hp ?? "?"} · Temporary ${item.temp_hp}`);
  if (item.current_hp === 0) hp.append(element("strong", " · 0 HP: check knockout/dying rules", "zero-tag"));
  const healingLink = element("a", "Open Healing & Death Helper"); healingLink.href = `/tools/healing-death?combat_id=${combat.id}&combatant_id=${item.id}`;
  const amountLabel = element("label", "Damage or healing amount");
  const amount = document.createElement("input");
  amount.type = "number"; amount.min = "0"; amount.value = "1";
  amountLabel.append(amount);
  const hpButtons = element("div", "", "control-buttons");
  hpButtons.append(button("Apply damage", () => send({ op: "damage", combatant_id: item.id, amount: numberOrNull(amount.value) })), button("Apply healing", () => send({ op: "heal", combatant_id: item.id, amount: numberOrNull(amount.value) })));
  const reactions = element("div", "", "control-buttons");
  reactions.append(element("span", `Reaction available: ${item.reaction_remaining}`), button("Spend", () => send({ op: "reaction", combatant_id: item.id, amount: -1 })), button("Restore", () => send({ op: "reaction", combatant_id: item.id, amount: 1 })));
  const notesLabel = element("label", "Notes");
  const notes = document.createElement("textarea");
  notes.rows = 2; notes.maxLength = 1000; notes.value = item.notes;
  notes.addEventListener("change", () => send({ op: "notes", combatant_id: item.id, notes: notes.value }));
  notesLabel.append(notes);
  const effects = element("div", "", "effect-list");
  const conditions = element("div", "", "effect-list");
  conditions.append(element("h3", "Rules conditions"));
  const conditionLink = element("a", "Open Conditions Tracker for full details");
  conditionLink.href = `/tools/conditions?combat_id=${combat.id}&combatant_id=${item.id}`;
  conditions.append(conditionLink);
  const conditionControls = element("div", "", "effect-fields");
  const picker = document.createElement("select"); picker.append(new Option("Choose condition", ""));
  conditionLibrary.forEach(row => picker.append(new Option(row.name, row.slug)));
  const addCondition = button("Add condition", async () => {
    const rule = conditionLibrary.find(row => row.slug === picker.value); if (!rule) return;
    if (rule.slug === "persistent-damage") { location.href = `/tools/conditions?combat_id=${combat.id}&combatant_id=${item.id}&condition=persistent-damage`; return; }
    try { await conditionRequest("/active", "POST", {combat_id:combat.id,combatant_id:item.id,slug:rule.slug,value:rule.valued ? 1 : null}); await refreshConditions(); message("Condition saved."); }
    catch(error) { message(error.message,true); }
  });
  conditionControls.append(picker,addCondition); conditions.append(conditionControls);
  for (const row of (conditionSummary[String(item.id)]?.visible || []).filter(row => !row.overridden)) {
    const line = element("div", "", "effect-row");
    const link = element("a", conditionLabel(row)); link.href = `/tools/conditions?combat_id=${combat.id}&combatant_id=${item.id}&condition=${row.slug}`;
    line.append(link);
    if (row.source_ids.length) line.append(button("Remove", async () => { try { await conditionRequest(`/active/${row.source_ids[0]}`, "DELETE"); await refreshConditions(); message("Condition source removed."); } catch(error) { message(error.message,true); } }));
    conditions.append(line);
  }
  picker.disabled = ended; addCondition.disabled = ended;
  effects.append(element("h3", "Other manual effect notes and durations"));
  for (const [index, effect] of item.effects.entries()) {
    const row = element("div", "", "effect-row");
    row.append(element("span", effect.duration ? `${effect.label} — ${effect.duration}` : effect.label), button("Remove", () => send({ op: "remove_effect", combatant_id: item.id, effect_index: index })));
    effects.append(row);
  }
  const effectFields = element("div", "", "effect-fields");
  const label = document.createElement("input"); label.placeholder = "Frightened 1"; label.maxLength = 80;
  const duration = document.createElement("input"); duration.placeholder = "Until next turn"; duration.maxLength = 100;
  effectFields.append(label, duration, button("Add effect", () => send({ op: "add_effect", combatant_id: item.id, label: label.value, duration: duration.value })));
  for (const group of [hpButtons, reactions, effects, effectFields]) for (const child of group.querySelectorAll("button")) child.disabled = ended;
  for (const field of [amount, notes, label, duration]) field.disabled = ended;
  box.append(name, typeLabel, hp, healingLink, amountLabel, hpButtons, reactions, notesLabel, conditions, effects, effectFields);
  box.append(element("p", "Effects are labels only. Check each duration and apply its rules manually.", "hint"));
}

$("new-combat").addEventListener("click", async () => {
  try { const data = await request("/combats", "POST", { name: $("new-name").value }); loadState(data); await refreshCombats(data.id); message("Created and saved new combat."); }
  catch (error) { message(error.message, true); }
});
$("import-combat").addEventListener("click", async () => {
  if (!$("source-list").value) { message("Choose a saved Phase 4 encounter.", true); return; }
  try { const data = await request("/combats", "POST", { source_encounter_id: Number($("source-list").value) }); loadState(data); await refreshCombats(data.id); message("Copied creature groups into a new combat. Enter HP and initiative."); }
  catch (error) { message(error.message, true); }
});
$("load-combat").addEventListener("click", async () => {
  if (!$("combat-list").value) return;
  try { loadState(await request(`/combats/${$("combat-list").value}`)); message("Loaded saved combat."); }
  catch (error) { message(error.message, true); }
});
$("rename-combat").addEventListener("click", () => send({ op: "rename_combat", name: $("combat-name").value }));
$("save-combat").addEventListener("click", () => send({ op: "save" }));
$("end-combat").addEventListener("click", () => send({ op: "end" }));
$("resume-combat").addEventListener("click", () => send({ op: "resume" }));
$("delete-combat").addEventListener("click", async () => {
  if (!combat || !window.confirm("Delete this saved combat and its history?")) return;
  try { await request(`/combats/${combat.id}`, "DELETE"); combat = null; localStorage.removeItem("pf2e-current-combat"); render(); await refreshCombats(null); message("Saved combat deleted."); }
  catch (error) { message(error.message, true); }
});
$("next-turn").addEventListener("click", () => send({ op: "next_turn" }));
$("add-combatant").addEventListener("click", () => {
  const maximum = numberOrNull($("add-max-hp").value);
  const current = numberOrNull($("add-current-hp").value);
  send({ op: "add", name: $("add-name").value, type: $("add-type").value, quantity: numberOrNull($("add-quantity").value), initiative: numberOrNull($("add-initiative").value), max_hp: maximum, current_hp: current });
});
conditionRequest("/library").then((rules) => {
  conditionLibrary = rules;
  if (combat) render();
}).catch(() => {});
Promise.all([refreshCombats(), refreshSources()]).then(async () => {
  const link = new URLSearchParams(location.search);
  const explorationId = Number(link.get("exploration_id"));
  if (explorationId > 0) {
    try {
      const response = await fetch(`/api/exploration/sessions/${explorationId}/encounter`);
      if (response.ok) {
        const data = await response.json(), box = $("exploration-handoff-list");
        box.replaceChildren(...data.reminders.map(text => element("p", text, "condition-reminder")));
        $("exploration-handoff").hidden = false;
      }
    } catch (_) { /* Combat remains usable without an exploration session. */ }
  }
  const linked = Number(link.get("combat_id"));
  const last = linked > 0 ? linked : Number(localStorage.getItem("pf2e-current-combat"));
  if (last > 0) { try { loadState(await request(`/combats/${last}`)); await refreshCombats(last); } catch (_) { if (!linked) localStorage.removeItem("pf2e-current-combat"); } }
}).catch((error) => message(error.message, true));
window.addEventListener("focus", () => { if (combat) refreshConditions().catch(() => {}); });
