const api = "/api/conditions";
const $ = id => document.getElementById(id);
let targets = { combats: [], subjects: [] }, definitions = [], view = null;
const params = new URLSearchParams(location.search);
const el = (tag, content = "", cls = "") => { const node = document.createElement(tag); node.textContent = content; if (cls) node.className = cls; return node; };
const btn = (label, action) => { const node = el("button", label); node.type = "button"; node.onclick = action; return node; };
async function call(path, method = "GET", body = null) {
  const response = await fetch(api + path, {method, headers: body === null ? {} : {"Content-Type": "application/json"}, body: body === null ? undefined : JSON.stringify(body)});
  if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${response.status})`); }
  return response.status === 204 ? null : response.json();
}
function status(message, error = false) { $("message").textContent = message; $("message").classList.toggle("error", error); }
function currentCombat() { return targets.combats.find(row => String(row.id) === $("combat").value); }
function target() { const id = Number($("target").value); return id ? (currentCombat() ? {combat_id: Number($("combat").value), combatant_id:id} : {subject_id:id}) : null; }
function query(object) { return new URLSearchParams(object).toString(); }
function label(row) { const name = definitions.find(x => x.slug === row.slug)?.name || row.slug; return name + (row.value ? ` ${row.value}` : ""); }
function selectedDefinition() { return definitions.find(row => row.slug === $("condition").value); }
async function refreshTargets() {
  const oldCombat = $("combat").value, oldTarget = $("target").value;
  targets = await call("/targets");
  $("combat").replaceChildren(new Option("Standalone characters", ""));
  targets.combats.forEach(row => $("combat").append(new Option(row.name, String(row.id))));
  const linked = params.get("combat_id");
  $("combat").value = oldCombat || (linked && targets.combats.some(row => String(row.id) === linked) ? linked : "");
  fillTargets(oldTarget || params.get("combatant_id"));
}
function fillTargets(preferred = "") {
  $("target").replaceChildren(new Option("Choose character or monster", ""));
  const items = currentCombat()?.combatants || targets.subjects;
  items.forEach(row => $("target").append(new Option(row.name, String(row.id))));
  $("target").value = preferred && items.some(row => String(row.id) === String(preferred)) ? String(preferred) : "";
  const controller = $("controller"); controller.replaceChildren(new Option("Choose creature", ""));
  items.forEach(row => controller.append(new Option(row.name, String(row.id))));
  if (target()) controller.value = $("target").value;
  $("subject-name").parentElement.hidden = !!currentCombat();
  $("delete-subject").hidden = !!currentCombat() || !target();
  loadActive();
}
async function loadActive() {
  const chosen = target();
  $("delete-subject").hidden = !!currentCombat() || !chosen;
  view = chosen ? await call(`/active?${query(chosen)}`) : null;
  renderActive();
  const history = $("recovery-history"); history.replaceChildren();
  if (chosen) {
    const entries = await call(`/recovery-history?${query(chosen)}`);
    if (!entries.length) history.append(el("p", "No recovery checks recorded.", "hint"));
    entries.forEach(row => history.append(el("p", `${row.damage_expression} ${row.damage_type} (${row.source || "unspecified source"}): ${row.checks.map(check => check.success ? "success" : "failure").join(", ")}`, "hint")));
  }
  await renderTurn();
}
function renderRule() {
  const row = selectedDefinition(), box = $("rule-detail"); box.replaceChildren();
  if (!row) return;
  const inner = el("div", "", "rule-box");
  inner.append(el("strong", row.name), el("p", row.summary), el("p", row.effects), el("p", `Normally ends: ${row.ending}`));
  const link = el("a", `${row.source_book} p. ${row.source_page} · full rule`); link.href = row.source_url; link.target = "_blank"; link.rel = "noopener noreferrer"; inner.append(link); box.append(inner);
  $("value").parentElement.hidden = !row.valued;
  $("quickened-restriction").parentElement.hidden = row.slug !== "quickened";
  for (const id of ["damage-type", "damage-expression", "recovery-dc"]) $(id).parentElement.hidden = row.slug !== "persistent-damage";
  renderDurationFields();
}
function renderDurationFields() {
  const kind = $("duration").value;
  $("controller").parentElement.hidden = !["start_turn","end_turn","rounds"].includes(kind);
  $("duration-event").parentElement.hidden = kind !== "rounds";
  $("rounds").parentElement.hidden = kind !== "rounds";
  $("custom-duration").parentElement.hidden = kind !== "custom";
}
function renderActive() {
  const box = $("active"), guide = $("guidance"); box.replaceChildren(); guide.replaceChildren();
  if (!view) { box.append(el("p", "Choose a combatant or add a standalone character.", "hint")); return; }
  const visible = view.visible.filter(row => !row.overridden);
  const labels = el("div"); visible.forEach(row => labels.append(el("span", label(row), `condition-pill${row.implied_by.length && !row.source_ids.length ? " implied" : ""}`))); box.append(labels);
  if (!view.instances.length) box.append(el("p", "No conditions recorded.", "hint"));
  for (const row of view.instances) {
    const rule = definitions.find(x => x.slug === row.slug), item = el("div", "", "condition-row");
    item.append(el("strong", `${label(row)}${row.source ? ` · ${row.source}` : ""}`), el("p", rule?.summary || ""), el("p", rule?.effects || "", "hint"));
    if (rule) { const link = el("a", `${rule.source_book} p. ${rule.source_page} · full rule`); link.href = rule.source_url; link.target = "_blank"; link.rel = "noopener noreferrer"; item.append(link); }
    if (["dying","wounded","doomed","unconscious"].includes(row.slug)) { const helper = el("a", " · Open Healing & Death Helper"); helper.href = `/tools/healing-death?${query(target())}`; item.append(helper); }
    const duration = row.duration_kind === "rounds" ? `${row.rounds_remaining} round(s), ${row.duration_event} of creature ${row.controller_id}'s turn` : row.duration_kind === "start_turn" || row.duration_kind === "end_turn" ? `${row.duration_kind.replace("_", " ")} of creature ${row.controller_id}` : row.duration_kind === "custom" ? row.custom_duration : row.duration_kind === "recovery" ? "Until recovery succeeds" : "Until manually removed";
    item.append(el("p", `Duration: ${duration}${row.temporary ? " · temporary" : " · ongoing"}${row.notes ? ` · ${row.notes}` : ""}`, "hint"));
    if (row.slug === "persistent-damage") item.append(el("p", `${row.damage_expression} ${row.damage_type} · recovery DC ${row.recovery_dc} · ${row.recovery_log.length} recorded check(s)`, "warning"));
    const actions = el("div", "", "buttons");
    if (rule?.valued) { actions.append(btn("Increase", () => change(row.id, {value:row.value + 1})), btn("Reduce all sources", () => reduce(row.id))); }
    actions.append(btn("Edit", () => edit(row)), btn("Remove", () => remove(row.id)));
    if (row.slug === "persistent-damage") actions.append(btn("Recovery failed", () => recovery(row.id, false)), btn("Recovery succeeded", () => recovery(row.id, true)));
    item.append(actions); box.append(item);
  }
  const p = view.penalties, a = view.actions;
  guide.append(el("p", `Status: all checks/DCs ${p.all_checks_and_dcs_status}; AC ${p.ac_status}; Dexterity ${p.dexterity_status}; Strength ${p.strength_status}; Constitution ${p.constitution_status}; mental ${p.mental_status}.`));
  guide.append(el("p", `Circumstance: AC ${p.ac_circumstance}; attacks ${p.attack_circumstance}.`, "hint"));
  guide.append(el("p", `Saving throws (status): Fortitude ${p.fortitude_status}, Reflex ${p.reflex_status}, Will ${p.will_status}. Perception ${p.perception_status}.`, "hint"));
  guide.append(el("p", `Turn-start guidance: ${a.total_guidance} action(s) after ${a.actions_lost} lost; Quickened can add at most ${a.quickened_extra} restricted action. ${a.slowed ? `Slowed ${a.slowed}. ` : ""}${a.stunned ? `Stunned ${a.stunned}. ` : ""}${a.quickened_restrictions.join(" or ")}. Choose which action is lost when actions differ.`, "hint"));
  if (view.persistent_groups.some(row => row.gm_choice_needed)) guide.append(el("p", "Overlapping same-type persistent damage has incomparable amounts. GM chooses which source applies; do not add them.", "warning"));
  for (const row of view.upcoming) {
    const controller = (currentCombat()?.combatants || targets.subjects).find(actor => actor.id === row.controller_id)?.name || `creature ${row.controller_id}`;
    guide.append(el("p", `Upcoming: ${row.slug.replaceAll("-", " ")} · ${row.event} of ${controller}'s turn${row.rounds_remaining ? ` · ${row.rounds_remaining} round(s)` : ""}.`, "warning"));
  }
  guide.append(el("p", p.notes, "hint"));
}
async function renderTurn() {
  const chosen = target(), combat = currentCombat(), box = $("turn-reminders"); box.replaceChildren();
  $("turn-context").textContent = combat ? `Round ${combat.round}; active combatant: ${combat.combatants.find(row => row.id === combat.active_id)?.name || "none"}. Reminders are advisory; confirm each change.` : "Standalone tracking: choose a turn event below.";
  if (!chosen) return;
  const controls = el("div", "", "buttons");
  controls.append(btn("Start-turn reminders", () => showReminders("start")), btn("End-turn reminders", () => showReminders("end")));
  box.append(controls);
  if (combat && combat.active_id === chosen.combatant_id) await showReminders("start");
}
async function showReminders(event) {
  const chosen = target(), box = $("turn-reminders");
  if (!chosen) return;
  const actor_id = currentCombat()?.active_id || chosen.subject_id;
  const rows = await call(`/reminders?${query({...chosen, event, actor_id})}`);
  box.querySelectorAll(".reminder").forEach(node => node.remove());
  rows.forEach(row => { const item = el("div", row.text, "warning reminder");
    if (row.kind === "reduce") item.append(btn("Confirm reduction", () => reduce(row.instance_id)));
    if (row.kind === "stunned_reduce") item.append(btn("Confirm Stunned action loss", () => reduce(row.instance_id, row.amount)));
    if (row.kind === "persistent") item.append(btn("Recovery failed", () => recovery(row.instance_id, false)), btn("Recovery succeeded", () => recovery(row.instance_id, true)));
    if (row.kind === "persistent_choice") item.append(el("span", "Choose the stronger source in the active list below.", "hint"));
    if (row.kind === "round") item.append(btn("Confirm round tick", async () => { const entry = view.instances.find(x => x.id === row.instance_id); if (entry.rounds_remaining <= 1) await remove(entry.id); else await change(entry.id, {rounds_remaining:entry.rounds_remaining - 1}); }));
    if (row.kind === "expiration") item.append(btn("Confirm end", () => remove(row.instance_id)));
    box.append(item); });
}
async function change(id, body) { try { await call(`/active/${id}`, "PATCH", body); await loadActive(); status("Condition saved."); } catch (error) { status(error.message, true); } }
async function reduce(id, amount = 1) { try { await call(`/active/${id}/reduce`, "POST", {amount}); await loadActive(); status("All sources of this valued condition reduced."); } catch (error) { status(error.message, true); } }
async function remove(id) { try { await call(`/active/${id}`, "DELETE"); await loadActive(); status("Condition source removed."); } catch (error) { status(error.message, true); } }
async function recovery(id, success) { try { await call(`/active/${id}/recovery`, "POST", {success}); await loadActive(); status(success ? "Recovery confirmed; source removed." : "Failed recovery recorded."); } catch (error) { status(error.message, true); } }
function edit(row) {
  $("search").value = ""; $("search").dispatchEvent(new Event("input"));
  $("condition").value = row.slug; renderRule();
  const map = {value:row.value,source:row.source,notes:row.notes,duration:row.duration_kind,controller:row.controller_id,"duration-event":row.duration_event,rounds:row.rounds_remaining,"custom-duration":row.custom_duration,"quickened-restriction":row.quickened_restriction,"damage-type":row.damage_type,"damage-expression":row.damage_expression,"recovery-dc":row.recovery_dc};
  Object.entries(map).forEach(([id,value]) => { $(id).value = value ?? ""; }); $("temporary").checked = row.temporary;
  renderDurationFields();
  $("apply").textContent = "Save condition"; $("apply").dataset.editId = row.id; $("apply").focus();
}
function input() {
  const chosen = target(); if (!chosen) throw new Error("Choose a combatant or standalone character.");
  const rule = selectedDefinition(); if (!rule) throw new Error("Choose a condition.");
  return {...chosen, slug:rule.slug, value:rule.valued && $("value").value.trim() ? Number($("value").value) : null,
    source:$("source").value,notes:$("notes").value,temporary:$("temporary").checked,
    duration_kind:$("duration").value,controller_id:$("controller").value ? Number($("controller").value) : null,
    duration_event:$("duration-event").value,rounds_remaining:$("duration").value === "rounds" ? Number($("rounds").value) : null,
    custom_duration:$("custom-duration").value,quickened_restriction:$("quickened-restriction").value,
    damage_type:$("damage-type").value,damage_expression:$("damage-expression").value,recovery_dc:Number($("recovery-dc").value)};
}
$("apply").onclick = async () => { try { const values = input(), id = $("apply").dataset.editId;
  if (id) { const {combat_id,combatant_id,subject_id,slug,...edits} = values; await call(`/active/${id}`, "PATCH", edits); delete $("apply").dataset.editId; $("apply").textContent = "Apply condition"; }
  else await call("/active", "POST", values);
  await loadActive(); status("Condition saved.");
} catch(error) { status(error.message,true); } };
$("add-subject").onclick = async () => { try { const row = await call("/subjects","POST",{name:$("subject-name").value}); await refreshTargets(); $("target").value = String(row.id); await loadActive(); status("Standalone character added."); } catch(error) { status(error.message,true); } };
$("delete-subject").onclick = async () => { const chosen = target(); if (!chosen?.subject_id || !confirm("Remove this standalone character and its conditions?")) return;
  try { await call(`/subjects/${chosen.subject_id}`,"DELETE"); await refreshTargets(); status("Standalone character removed."); } catch(error) { status(error.message,true); } };
$("combat").onchange = () => fillTargets(); $("target").onchange = () => { $("controller").value = $("target").value; loadActive(); };
$("condition").onchange = renderRule;
$("duration").onchange = renderDurationFields;
$("search").oninput = () => { const q = $("search").value.toLowerCase(), selected = $("condition").value;
  $("condition").replaceChildren(); definitions.filter(row => `${row.name} ${row.summary} ${row.effects}`.toLowerCase().includes(q)).forEach(row => $("condition").append(new Option(row.name,row.slug)));
  if ([...$("condition").options].some(option => option.value === selected)) $("condition").value = selected;
  renderRule(); };
Promise.all([call("/library"),refreshTargets()]).then(([rows]) => { definitions = rows; definitions.forEach(row => $("condition").append(new Option(row.name,row.slug)));
  if (params.get("condition")) $("condition").value = params.get("condition"); renderRule(); if (target()) loadActive();
}).catch(error => status(error.message,true));
window.addEventListener("focus", () => { refreshTargets().catch(() => {}); });
