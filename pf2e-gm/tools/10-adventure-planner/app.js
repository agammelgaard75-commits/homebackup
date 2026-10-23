const API = '/api/adventure-planner';
const root = document.getElementById('app');
let adventures = [], options = {campaigns: [], parties: [], encounters: []}, data = null;
let rosterPartyId = null, rosterMembers = [], editingMemberId = null;
let mode = 'prep', editing = null, activeSession = null, message = '';
const noteTimers = new Map();
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const txt = (name, label, value='', rows=0) => `<label>${label}${rows ? `<textarea name="${name}" rows="${rows}">${esc(value)}</textarea>` : `<input name="${name}" value="${esc(value)}">`}</label>`;
const num = (name, label, value='', min=0, max=10000, step=1) => `<label>${label}<input type="number" name="${name}" value="${esc(value)}" min="${min}" max="${max}" step="${step}"></label>`;
const sel = (name, label, choices, value='') => `<label>${label}<select name="${name}">${choices.map(([v,t]) => `<option value="${esc(v)}" ${String(v)===String(value ?? '')?'selected':''}>${esc(t)}</option>`).join('')}</select></label>`;
const check = (name, label, value=false) => `<label class="inline"><input type="checkbox" name="${name}" ${value?'checked':''}>${label}</label>`;
const sceneChoices = () => (data?.scenes || []).map(s => [s.id, s.title]);
const multiScenes = ids => `<fieldset><legend>Relevant scenes (optional)</legend><div class="checkgrid">${sceneChoices().map(([id,title]) => `<label><input type="checkbox" name="scene_ids" value="${id}" ${(ids||[]).includes(id)?'checked':''}>${esc(title)}</label>`).join('')}</div></fieldset>`;
const choice = (items, selected, empty) => [["",empty], ...items.map(v => [v.id,v.name || v.title])];
async function api(path, method='GET', body) {
  const response = await fetch(API + path, {method, headers: body === undefined ? {} : {'Content-Type':'application/json'}, body: body === undefined ? undefined : JSON.stringify(body)});
  if (!response.ok) { let e; try {e=await response.json();} catch {e={detail:response.statusText};} throw Error(typeof e.detail==='string' ? e.detail : JSON.stringify(e.detail)); }
  return response.status===204 ? null : response.json();
}
async function rosterApi(path, method='GET', body) {
  const response = await fetch('/api/party-roster'+path, {method, headers:body===undefined?{}:{'Content-Type':'application/json'}, body:body===undefined?undefined:JSON.stringify(body)});
  if (!response.ok) {const result=await response.json().catch(()=>({})); throw Error(typeof result.detail==='string'?result.detail:JSON.stringify(result.detail));}
  return response.status===204?null:response.json();
}
async function refresh(id=data?.adventure.id) {
  [adventures, options] = await Promise.all([api('/adventures'), api('/options')]);
  data = id ? await api(`/adventures/${id}`) : null;
  if (data?.adventure.party_id) rosterPartyId=data.adventure.party_id;
  else if (!options.parties.some(p=>p.id===rosterPartyId)) rosterPartyId=options.parties[0]?.id||null;
  rosterMembers=rosterPartyId?await rosterApi(`/parties/${rosterPartyId}/members`):[];
  if (data && !data.sessions.some(s=>s.id===activeSession)) activeSession=data.sessions[0]?.id || null;
  render();
}
function fields(kind, value={}) {
  const v=value;
  if (kind==='adventure') return txt('title','Title',v.title)+txt('description','Short description',v.description,2)+txt('starting_situation','Starting situation',v.starting_situation,2)+txt('main_objective','Main objective',v.main_objective,2)+num('suggested_level','Suggested party level',v.suggested_level,1,20)+num('expected_players','Expected players',v.expected_players,1,12)+num('estimated_hours','Estimated playtime (hours)',v.estimated_hours,0,1000,.5)+txt('secrets','Important secrets',v.secrets,2)+txt('outcomes','Possible endings or outcomes',v.outcomes,2)+txt('gm_notes','GM notes',v.gm_notes,3)+sel('campaign_id','Campaign',choice(options.campaigns,v.campaign_id,'None'),v.campaign_id)+sel('party_id','Party',choice(options.parties,v.party_id,'None'),v.party_id);
  if (kind==='scene') return txt('title','Title',v.title)+sel('type','Scene type',['roleplaying','exploration','combat','puzzle','investigation','travel','other'].map(x=>[x,x]),v.type||'other')+sel('status','Status',['not_started','active','completed','skipped'].map(x=>[x,x.replace('_',' ')]),v.status||'not_started')+txt('location','Location',v.location)+txt('purpose','Purpose or objective',v.purpose,2)+txt('description','Short GM description',v.description,2)+txt('complications','Possible complications',v.complications,2)+num('duration_minutes','Estimated minutes',v.duration_minutes||0)+txt('notes','GM notes',v.notes,2);
  if (kind==='npc') return txt('name','Name',v.name)+txt('role','Role',v.role)+txt('personality','Personality',v.personality)+txt('motivation','Motivation',v.motivation)+txt('knows','What they know',v.knows,2)+txt('wants','What they want',v.wants)+txt('secret','Secret',v.secret)+txt('status','Current status',v.status)+txt('external_url','External reference URL',v.external_url)+txt('notes','Notes',v.notes,2)+multiScenes(v.scene_ids);
  if (kind==='clue') return txt('name','Name',v.name)+txt('description','Description',v.description,2)+txt('location','Possible discovery location',v.location)+txt('reveals','What it reveals',v.reveals,2)+txt('alternatives','Alternative discovery locations',v.alternatives)+check('discovered','Discovered',v.discovered)+sel('discovered_scene_id','Discovered in',choice(data.scenes,v.discovered_scene_id,'Not recorded'),v.discovered_scene_id)+txt('notes','GM notes',v.notes,2)+multiScenes(v.scene_ids);
  if (kind==='item') return txt('name','Name',v.name)+sel('kind','Type',[['item','Item'],['objective','Objective']],v.kind||'item')+txt('description','Description',v.description,2)+txt('starting_location','Starting location',v.starting_location)+txt('current_location','Current holder or location',v.current_location)+check('required','Required',v.required)+check('obtained','Obtained or completed',v.obtained)+txt('notes','GM notes',v.notes,2)+multiScenes(v.scene_ids);
  if (kind==='session') return txt('title','Session title',v.title)+num('number','Session number',v.number,1)+num('planned_minutes','Planned minutes',v.planned_minutes||0)+sel('status','Status',['planned','active','completed'].map(x=>[x,x]),v.status||'planned')+txt('objectives','Session objectives',v.objectives,2)+txt('prep_notes','Preparation notes',v.prep_notes,2)+txt('actual_notes','Actual session notes',v.actual_notes,2)+txt('next_session_notes','GM notes for next session',v.next_session_notes,2)+txt('summary_markdown','Saved recap (editable)',v.summary_markdown,5)+multiScenes(v.scene_ids);
  if (kind==='event') return txt('text','Short note',v.text,2)+sel('kind','Kind',[['note','Note'],['decision','Player decision'],['npc','NPC interaction'],['unexpected','Unexpected event'],['objective','Objective'],['encounter','Encounter']],v.kind||'note')+sel('scene_id','Scene',choice(data.scenes,v.scene_id,'None'),v.scene_id)+txt('game_time','In-game time (optional)',v.game_time);
}
function editor() {
  if (!editing) return '';
  const v=editing.value||{};
  return `<section class="card editor"><div class="row"><h2>${editing.id?'Edit':'Add'} ${esc(editing.kind)}</h2><button type="button" data-action="close-editor">Close</button></div><form id="editor-form" data-kind="${editing.kind}">${fields(editing.kind,v)}<div class="actions"><button type="submit">Save ${esc(editing.kind)}</button></div></form></section>`;
}
const link = (href,title) => `<a href="${href}">${title} ↗</a>`;
const tools = () => `<nav class="tool-links" aria-label="Related tools">${[['dc-helper','DC Helper'],['encounter-builder','Encounter Builder'],['combat-tracker','Combat Tracker'],['conditions','Conditions'],['healing-death','Healing'],['exploration','Exploration'],['treasure-xp','Rewards'],['rules-reference','Rules Reference']].map(([s,n])=>link('/tools/'+s,n)).join('')}</nav>`;
function render() {
  let html = `<div class="row toolbar"><a href="/">← Dashboard</a><strong>${esc(message)}</strong></div><div class="row"><label>Adventure<select id="adventure-select"><option value="">Choose adventure</option>${adventures.map(a=>`<option value="${a.id}" ${data?.adventure.id===a.id?'selected':''}>${esc(a.title)}${a.status==='archived'?' (archived)':''}</option>`).join('')}</select></label><button data-action="new" data-kind="adventure">New adventure</button><label>Import JSON backup<input type="file" id="import-file" accept="application/json,.json"></label><label>Mode<select id="mode"><option value="prep" ${mode==='prep'?'selected':''}>Preparation</option><option value="play" ${mode==='play'?'selected':''}>Play</option></select></label></div>`;
  if (!data) { root.innerHTML=html+rosterSection()+editor()+`<p>Choose or create an adventure. Everything is stored locally.</p>`; return; }
  const a=data.adventure;
  html += `<section class="card"><div class="row"><div><h2>${esc(a.title)}</h2><p>${esc(a.description)}</p><p class="muted">${esc(options.campaigns.find(c=>c.id===a.campaign_id)?.name||'No campaign')} · ${esc(options.parties.find(p=>p.id===a.party_id)?.name||'No party')}</p></div><div class="actions"><button data-action="edit-adventure">Edit</button><button data-action="duplicate-adventure">Duplicate</button><button data-action="archive-adventure">${a.status==='archived'?'Unarchive':'Archive'}</button><button class="danger" data-action="delete-adventure">Delete</button></div></div>${mode==='prep'?`<p><b>Starting situation:</b> ${esc(a.starting_situation)}</p><p><b>Main objective:</b> ${esc(a.main_objective)}</p><p><b>Secrets:</b> ${esc(a.secrets)}</p><p><b>Possible outcomes:</b> ${esc(a.outcomes)}</p><p><b>GM notes:</b> ${esc(a.gm_notes)}</p>`:''}</section>`;
  html += editor();
  html += rosterSection();
  html += mode==='prep' ? prep() : play();
  html += `<section class="card"><h2>Guidance and backup</h2><p>Scenes are flexible prompts. Use any scene in any order; links never force progression.</p><p>${link('https://2e.aonprd.com/Rules.aspx?ID=2688','GM Core, Adventure Design (p. 68)')} · ${link('https://2e.aonprd.com/Rules.aspx?ID=2716','GM Core, Encounter Design')}</p><div class="actions"><a href="${API}/adventures/${a.id}/export.json" download="adventure-${a.id}.json">Export JSON</a><a href="${API}/adventures/${a.id}/export.md" download="adventure-${a.id}.md">Export Markdown</a></div></section>`;
  root.innerHTML=html;
}
function rosterSection() {
  const selected=options.parties.find(p=>p.id===rosterPartyId);
  const formMember=rosterMembers.find(m=>m.id===editingMemberId)||{};
  return `<section class="card"><div class="row"><h2>Party PCs</h2>${selected?`<a href="/tools/combat-tracker?party_id=${selected.id}">Open Combat Tracker with this party ↗</a>`:''}</div>
    <p class="muted">A reusable PC template. Running combat HP stays separate until you explicitly copy it back.</p>
    <div class="row"><label>Party<select id="roster-party"><option value="">Choose party</option>${options.parties.map(p=>`<option value="${p.id}" ${p.id===rosterPartyId?'selected':''}>${esc(p.name)}</option>`).join('')}</select></label>
    <form id="new-campaign" class="compact-form">${txt('name','New campaign')}<button>Create campaign</button></form>
    <form id="new-party" class="compact-form">${sel('campaign_id','Campaign',options.campaigns.map(c=>[c.id,c.name]))}${txt('name','New party')}<button>Create party</button></form></div>
    ${selected?`<div class="list">${rosterMembers.map(m=>`<article><div class="row"><div><b>${esc(m.name)}</b> · ${esc(m.class_name||'Class not set')}<small>HP ${m.current_hp??'?'} / ${m.max_hp??'?'} · Speed ${m.speed??'?'} ft</small>${m.notes?`<small>${esc(m.notes)}</small>`:''}</div><div class="actions"><button data-action="edit-member" data-id="${m.id}">Edit</button><button class="danger" data-action="delete-member" data-id="${m.id}">Remove</button></div></div></article>`).join('')||'<p>No PCs in this party yet.</p>'}</div>
    <form id="member-form" class="compact-form">${txt('name','PC name',formMember.name)}${txt('class_name','Class',formMember.class_name)}${num('max_hp','Maximum HP',formMember.max_hp??'',1,99999)}${num('current_hp','Current HP',formMember.current_hp??'',0,99999)}${num('speed','Speed (ft)',formMember.speed??'',1,9999)}${txt('notes','Short note',formMember.notes)}<button>${editingMemberId?'Save PC':'Add PC'}</button>${editingMemberId?'<button type="button" data-action="cancel-member">Cancel</button>':''}</form>`:''}
    ${data&&!data.adventure.party_id?'<p class="muted">To use this party for the adventure, choose it in Edit adventure.</p>':''}</section>`;
}
function controls(kind,row) { return `<span class="actions"><button data-action="edit" data-kind="${kind}" data-id="${row.id}">Edit</button><button class="danger" data-action="delete" data-kind="${kind}" data-id="${row.id}">Delete</button></span>`; }
function prep() {
  let h = `<section class="card"><div class="row"><h2>Scenes</h2><button data-action="new" data-kind="scene">Add scene</button></div><p class="muted">Order is suggested. Start any scene at any time.</p><div class="list">`;
  h += data.scenes.map((s,i)=>`<article class="${s.status==='completed'?'is-done':''}"><div class="row"><div><b>${i+1}. ${esc(s.title)}</b> <span class="pill">${esc(s.type)}</span> <span class="pill ${s.status==='completed'?'is-done':''}">${esc(s.status.replace('_',' '))}</span><small>${s.duration_minutes} min · ${esc(s.location)}</small><p>${esc(s.purpose||s.description)}</p></div><div class="actions"><button data-action="select-scene" data-id="${s.id}">Open</button><button data-action="move" data-id="${s.id}" data-delta="-1" ${i===0?'disabled':''}>↑</button><button data-action="move" data-id="${s.id}" data-delta="1" ${i===data.scenes.length-1?'disabled':''}>↓</button><button data-action="duplicate-scene" data-id="${s.id}">Duplicate</button>${controls('scene',s)}</div></div></article>`).join('');
  h += `</div></section>`;
  h += `<section class="card"><div class="row"><h2>Scene connections</h2></div><form id="connection-form" class="compact-form">${sel('from_scene_id','From',sceneChoices())}${sel('to_scene_id','To',sceneChoices())}${sel('kind','Link type',[['leads_to','Leads to'],['clue_points_to','Clue points to'],['alternative_route','Alternative route'],['optional_scene','Optional scene']])}<button>Add link</button></form><ul>${data.connections.map(c=>`<li>${esc(data.scenes.find(s=>s.id===c.from_scene_id)?.title)} → ${esc(data.scenes.find(s=>s.id===c.to_scene_id)?.title)} (${esc(c.kind.replaceAll('_',' '))}) <button data-action="delete-connection" data-id="${c.id}">Remove</button></li>`).join('')}</ul></section>`;
  for (const [entity,title] of [['npcs','NPCs'],['clues','Clues'],['items','Items and objectives']]) {
    const kind=entity.slice(0,-1);
    h += `<section class="card"><div class="row"><h2>${title}</h2><button data-action="new" data-kind="${kind}">Add ${kind}</button></div><div class="list">${data[entity].map(r=>`<article class="${(entity==='clues'&&r.discovered)||(entity==='items'&&r.obtained)?'is-done':''}"><div class="row"><div><b>${esc(r.name)}</b> ${entity==='clues'?`<span class="pill ${r.discovered?'is-done':''}">${r.discovered?'Discovered':'Undiscovered'}</span>`:''}${entity==='items'?`<span class="pill ${r.obtained?'is-done':''}">${r.obtained?'Obtained':'Open'}</span>`:''}<p>${esc(r.role||r.reveals||r.description)}</p><small>${r.scene_ids.map(id=>data.scenes.find(s=>s.id===id)?.title).filter(Boolean).map(esc).join(', ')}</small>${entity==='items'?`<p>${link('/tools/treasure-xp','Treasure & XP')}</p>`:''}</div>${controls(kind,r)}</div></article>`).join('')}</div></section>`;
  }
  h += `<section class="card"><div class="row"><h2>Linked encounters</h2></div><form id="encounter-form" class="compact-form">${sel('scene_id','Scene',sceneChoices())}${sel('encounter_id','Saved encounter',options.encounters.map(e=>[e.id,e.name]))}<button>Link encounter</button></form>${data.encounters.map(e=>encounterView(e,true)).join('')}</section>`;
  h += sessions();
  return h;
}
function encounterView(e, editable) {
  const scene=data.scenes.find(s=>s.id===e.scene_id);
  return `<article class="${e.completed?'is-done':''}"><div class="row"><div><b>${esc(scene?.title)}:</b> ${e.missing?`<strong class="warning">Encounter #${e.encounter_id} unavailable</strong>`:`${link('/tools/encounter-builder',esc(e.name))} · ${e.xp??'Unsupported'} XP · ${esc(e.difficulty)} · ${esc(e.creatures.map(c=>`${c.quantity} ${c.name}`).join(', '))}`} ${e.completed?'<span class="pill is-done">Completed</span>':''}</div><div class="actions">${!e.missing?`<a href="/tools/combat-tracker?encounter_id=${e.encounter_id}${data.adventure.party_id?`&party_id=${data.adventure.party_id}`:''}">Open combat</a>`:''}${editable?`${e.missing?'':`<button data-action="toggle-encounter" data-id="${e.id}">${e.completed?'Mark open':'Mark complete'}</button>`}<button data-action="unlink-encounter" data-id="${e.id}">Unlink</button>`:''}</div></div></article>`;
}
function sessions() {
  return `<section class="card"><div class="row"><h2>Sessions</h2><button data-action="new" data-kind="session">Add session</button></div>${data.sessions.map(s=>`<article class="${s.status==='completed'?'is-done':''}"><div class="row"><div><b>${esc(s.title)}</b> <span class="pill ${s.status==='completed'?'is-done':''}">${esc(s.status)}</span><p>${s.budget.scene_minutes} / ${s.planned_minutes} planned minutes · ${s.budget.over_budget?'<strong class="warning">Over session time</strong>':`${s.budget.buffer_minutes} min buffer`}</p><p>${esc(s.objectives)}</p></div>${controls('session',s)}</div><div class="actions"><button data-action="choose-session" data-id="${s.id}">Use for notes</button><button data-action="recap" data-id="${s.id}">Generate recap</button><a href="${API}/adventures/${data.adventure.id}/sessions/${s.id}/recap.md" download="session-${s.id}-recap.md">Export recap</a></div><div class="event-list">${s.events.map(e=>`<div><small>${esc(e.game_time||e.created_at)} · ${esc(e.kind)}</small> ${esc(e.text)} <button data-action="edit" data-kind="event" data-id="${e.id}" data-session="${s.id}">Edit</button><button data-action="delete" data-kind="event" data-id="${e.id}" data-session="${s.id}">×</button></div>`).join('')}</div></article>`).join('')}${noteForm()}</section>`;
}
function noteForm() {
  if (!data.sessions.length) return '<p>Create a session to record during-session notes.</p>';
  return `<form id="note-form" class="compact-form">${sel('session_id','Session',data.sessions.map(s=>[s.id,s.title]),activeSession)}${txt('text','Add note')}${sel('kind','Kind',[['note','Note'],['decision','Player decision'],['npc','NPC interaction'],['unexpected','Unexpected event'],['objective','Objective'],['encounter','Encounter']])}${sel('scene_id','Scene',choice(data.scenes,null,'None'),data.adventure.current_scene_id)}${txt('game_time','In-game time')}<button>Add Note</button></form>`;
}
function play() {
  const current=data.scenes.find(s=>s.id===data.adventure.current_scene_id)||data.scenes[0];
  let h=`<section class="card ${current?.status==='completed'?'is-done':''}"><div class="row"><h2>Current scene</h2><button data-action="new" data-kind="scene">Add scene</button></div><label>Switch scene<select id="play-scene">${sceneChoices().map(([id,title])=>`<option value="${id}" ${id===current?.id?'selected':''}>${esc(title)}</option>`).join('')}</select></label>${current?`<h3>${esc(current.title)}</h3><p><b>Objective:</b> ${esc(current.purpose)}</p><p>${esc(current.description)}</p><p><b>Location:</b> ${esc(current.location)} · <b>Status:</b> ${esc(current.status.replace('_',' '))}</p><p><b>Complications:</b> ${esc(current.complications)}</p><label class="quick-notes">Quick scene notes (save automatically)<textarea id="scene-quick-notes" data-id="${current.id}" rows="3">${esc(current.notes)}</textarea></label><div class="actions"><button data-action="edit" data-kind="scene" data-id="${current.id}">Edit scene</button><button data-action="complete-scene" data-id="${current.id}">Mark completed</button><button data-action="skip-scene" data-id="${current.id}">Skip</button></div>`:'<p>Add a scene to begin.</p>'}</section>`;
  if (current) {
    for (const [entity,title] of [['npcs','Important NPCs'],['clues','Clues available'],['items','Relevant items']]) {
      const rows=data[entity].filter(r=>r.scene_ids.includes(current.id));
      h+=`<section class="card"><div class="row"><h2>${title}</h2><button data-action="new" data-kind="${entity.slice(0,-1)}">Add</button></div>${rows.map(r=>`<article class="${(entity==='clues'&&r.discovered)||(entity==='items'&&r.obtained)?'is-done':''}"><div class="row"><div><b>${esc(r.name)}</b><p>${esc(r.role||r.reveals||r.description)}</p>${entity==='clues'?`<small>${r.discovered?'Discovered':'Undiscovered'} · ${esc(r.alternatives)}</small>`:''}${entity==='items'?`<small>${r.obtained?'Obtained':'Not obtained'} · ${esc(r.current_location)}</small>`:''}</div><div class="actions"><button data-action="edit" data-kind="${entity.slice(0,-1)}" data-id="${r.id}">Edit</button>${entity==='clues'&&!r.discovered?`<button data-action="discover" data-id="${r.id}" data-scene="${current.id}">Discovered</button>`:''}${entity==='items'&&!r.obtained?`<button data-action="obtain" data-id="${r.id}">Obtained</button>`:''}</div></div></article>`).join('')||'<p class="muted">None linked. Add or move one at any time.</p>'}</section>`;
    }
    h+=`<section class="card"><h2>Linked encounters</h2>${data.encounters.filter(e=>e.scene_id===current.id).map(e=>encounterView(e,true)).join('')||'<p>No encounter linked.</p>'}<p>Opening combat does not start it automatically.</p></section>`;
  }
  h+=`<section class="card"><h2>Quick actions</h2>${tools()}</section><section class="card"><h2>Session log</h2>${noteForm()}</section><section class="card"><h2>Other available scenes</h2><div class="actions">${data.scenes.map(s=>`<button data-action="select-scene" data-id="${s.id}">${esc(s.title)} (${esc(s.status.replace('_',' '))})</button>`).join('')}</div></section>`;
  return h;
}
function payload(form, kind) {
  const fd=new FormData(form), out={};
  for (const [key,val] of fd) if (key!=='scene_ids') out[key]=val;
  if (['npc','clue','item','session'].includes(kind)) out.scene_ids=fd.getAll('scene_ids').map(Number);
  const numbers={adventure:['suggested_level','expected_players','estimated_hours','campaign_id','party_id'],scene:['duration_minutes'],clue:['discovered_scene_id'],session:['number','planned_minutes'],event:['scene_id']};
  for (const key of numbers[kind]||[]) out[key]=out[key]===''||out[key]===undefined?null:Number(out[key]);
  if (kind==='scene' && out.duration_minutes===null) out.duration_minutes=0;
  if (kind==='session' && out.planned_minutes===null) out.planned_minutes=0;
  for (const key of ['completed_session_id','discovered_session_id','obtained_session_id']) if (editing?.value && key in editing.value) out[key]=editing.value[key];
  for (const key of ['required','obtained','discovered']) if (kind==='item'||kind==='clue') if (key in out || form.elements.namedItem(key)) out[key]=fd.has(key);
  return out;
}
function record(kind,id,sessionId) {
  const names={scene:'scenes',npc:'npcs',clue:'clues',item:'items',session:'sessions'};
  if (kind==='event') return data.sessions.find(s=>s.id===sessionId)?.events.find(r=>r.id===id);
  return data[names[kind]]?.find(r=>r.id===id);
}
function path(kind,id,sessionId) {
  const a=`/adventures/${data.adventure.id}`;
  if (kind==='adventure') return a;
  if (kind==='event') return `${a}/sessions/${sessionId}/events${id?'/'+id:''}`;
  const resource={scene:'scenes',npc:'npcs',clue:'clues',item:'items',session:'sessions'}[kind];
  return `${a}/${resource}${id?'/'+id:''}`;
}
async function run(fn) { try {await fn(); message='Saved locally';} catch(e) {message=e.message; alert(e.message);} render(); }
root.addEventListener('change', e => {
  if (e.target.id==='roster-party') run(async()=>{rosterPartyId=Number(e.target.value)||null;editingMemberId=null;rosterMembers=rosterPartyId?await rosterApi(`/parties/${rosterPartyId}/members`):[];});
  if (e.target.id==='adventure-select') run(async()=>{editing=null;await refresh(Number(e.target.value)||null);});
  if (e.target.id==='mode') {mode=e.target.value;editing=null;render();}
  if (e.target.id==='play-scene') run(async()=>{await api(`/adventures/${data.adventure.id}/scenes/${e.target.value}/select`,'POST');await refresh();});
  if (e.target.id==='import-file') run(async()=>{const file=e.target.files[0];if(!file)return;const value=JSON.parse(await file.text());const created=await api('/import','POST',value);editing=null;await refresh(created.adventure.id);});
});
root.addEventListener('input', e => {
  if (e.target.id !== 'scene-quick-notes') return;
  const id=Number(e.target.dataset.id), notes=e.target.value, adventureId=data.adventure.id, original=data.scenes.find(s=>s.id===id);
  clearTimeout(noteTimers.get(id));
  noteTimers.set(id,setTimeout(async()=>{
    try {
      const scene=(data?.adventure.id===adventureId?data.scenes.find(s=>s.id===id):null)||original;
      if (!scene) return;
      await api(`/adventures/${adventureId}/scenes/${id}`,'PATCH',{...pickScene(scene),notes});
      scene.notes=notes;
      message='Scene notes saved';
    } catch(error) { message=error.message; alert(error.message); }
    noteTimers.delete(id);
  },600));
});
root.addEventListener('submit', e => {e.preventDefault();run(async()=>{
  const form=e.target, a=data?.adventure.id;
  if (form.id==='new-campaign') {await rosterApi('/campaigns','POST',{name:new FormData(form).get('name')});await refresh();}
  else if (form.id==='new-party') {const fd=new FormData(form);const created=await rosterApi('/parties','POST',{campaign_id:Number(fd.get('campaign_id')),name:fd.get('name')});rosterPartyId=created.id;await refresh();}
  else if (form.id==='member-form') {const fd=new FormData(form);const value=Object.fromEntries(fd);for(const key of ['max_hp','current_hp','speed']) value[key]=value[key]===''?null:Number(value[key]);await rosterApi(editingMemberId?`/members/${editingMemberId}`:`/parties/${rosterPartyId}/members`,editingMemberId?'PUT':'POST',value);editingMemberId=null;rosterMembers=await rosterApi(`/parties/${rosterPartyId}/members`);}
  else if (form.id==='editor-form') {
    const kind=editing.kind, body=payload(form,kind), url=kind==='adventure'&&!editing.id?'/adventures':path(kind,editing.id,editing.sessionId);
    const result=await api(url,editing.id?'PATCH':'POST',body);
    editing=null;await refresh(kind==='adventure'&&!a?result.adventure.id:a);
  } else if (form.id==='connection-form') {
    const fd=new FormData(form);await api(`/adventures/${a}/connections`,'POST',{from_scene_id:Number(fd.get('from_scene_id')),to_scene_id:Number(fd.get('to_scene_id')),kind:fd.get('kind')});await refresh();
  } else if (form.id==='encounter-form') {
    const fd=new FormData(form);await api(`/adventures/${a}/scenes/${fd.get('scene_id')}/encounters`,'POST',{encounter_id:Number(fd.get('encounter_id'))});await refresh();
  } else if (form.id==='note-form') {
    const fd=new FormData(form), sid=Number(fd.get('session_id'));activeSession=sid;
    await api(`/adventures/${a}/sessions/${sid}/events`,'POST',{text:fd.get('text'),kind:fd.get('kind'),scene_id:fd.get('scene_id')?Number(fd.get('scene_id')):null,game_time:fd.get('game_time')});await refresh();
  }
});});
root.addEventListener('click', e => {const b=e.target.closest('button[data-action]');if(!b)return;const act=b.dataset.action,id=Number(b.dataset.id),kind=b.dataset.kind,a=data?.adventure.id;
  run(async()=>{
    if (act==='edit-member') editingMemberId=id;
    else if (act==='cancel-member') editingMemberId=null;
    else if (act==='delete-member') {if(!confirm('Remove this PC from the roster? Existing combats keep their snapshots.'))return;await rosterApi(`/members/${id}`,'DELETE');editingMemberId=null;rosterMembers=await rosterApi(`/parties/${rosterPartyId}/members`);}
    else if (act==='close-editor') editing=null;
    else if (act==='new') editing={kind};
    else if (act==='edit-adventure') editing={kind:'adventure',id:a,value:data.adventure};
    else if (act==='edit') editing={kind,id,sessionId:Number(b.dataset.session)||null,value:record(kind,id,Number(b.dataset.session))};
    else if (act==='delete-adventure') {if(!confirm('Delete this adventure and its planner notes?'))return;await api(`/adventures/${a}`,'DELETE');editing=null;await refresh(null);}
    else if (act==='duplicate-adventure') {const copy=await api(`/adventures/${a}/duplicate`,'POST');await refresh(copy.adventure.id);}
    else if (act==='archive-adventure') {if(!confirm(data.adventure.status==='archived'?'Restore this adventure?':'Archive this adventure?'))return;await api(`/adventures/${a}/archive`,'POST');await refresh();}
    else if (act==='delete') {if(!confirm(`Delete this ${kind}?`))return;await api(path(kind,id,Number(b.dataset.session)),'DELETE');editing=null;await refresh();}
    else if (act==='duplicate-scene') {await api(`/adventures/${a}/scenes/${id}/duplicate`,'POST');await refresh();}
    else if (act==='select-scene') {await api(`/adventures/${a}/scenes/${id}/select`,'POST');await refresh();}
    else if (act==='complete-scene'||act==='skip-scene') {const s=record('scene',id);await api(path('scene',id),'PATCH',{...pickScene(s),status:act==='complete-scene'?'completed':'skipped',completed_session_id:act==='complete-scene'?activeSession:null});await refresh();}
    else if (act==='move') {const ids=data.scenes.map(s=>s.id),i=ids.indexOf(id),j=i+Number(b.dataset.delta);[ids[i],ids[j]]=[ids[j],ids[i]];await api(`/adventures/${a}/scenes/reorder`,'POST',{scene_ids:ids});await refresh();}
    else if (act==='delete-connection') {await api(`/adventures/${a}/connections/${id}`,'DELETE');await refresh();}
    else if (act==='unlink-encounter'||act==='toggle-encounter') {const l=data.encounters.find(e=>e.id===id),url=`/adventures/${a}/scenes/${l.scene_id}/encounters/${id}`;if(act==='unlink-encounter')await api(url,'DELETE');else await api(url,'PATCH',{encounter_id:l.encounter_id,completed:!l.completed,completed_session_id:!l.completed?activeSession:null});await refresh();}
    else if (act==='discover') {const c=record('clue',id);await api(path('clue',id),'PATCH',{...pickEntity('clue',c),discovered:true,discovered_scene_id:Number(b.dataset.scene),discovered_session_id:activeSession});await refresh();}
    else if (act==='obtain') {const item=record('item',id);await api(path('item',id),'PATCH',{...pickEntity('item',item),obtained:true,obtained_session_id:activeSession});await refresh();}
    else if (act==='choose-session') {activeSession=id;render();}
    else if (act==='recap') {const r=await api(`/adventures/${a}/sessions/${id}/recap`);const s=record('session',id);editing={kind:'session',id,value:{...s,summary_markdown:r.generated}};}
  });
});
function pickScene(s) {const keys=['title','type','status','location','purpose','description','complications','duration_minutes','notes','completed_session_id'];return Object.fromEntries(keys.map(k=>[k,s[k]]));}
function pickEntity(kind,v) {const keys={clue:['name','description','location','reveals','alternatives','discovered','discovered_scene_id','discovered_session_id','notes','scene_ids'],item:['name','kind','description','starting_location','current_location','required','obtained','obtained_session_id','notes','scene_ids']}[kind];return Object.fromEntries(keys.map(k=>[k,v[k]]));}
refresh(null).catch(e=>{root.textContent=e.message;});
