const api = '/api/monster-reference';
const $ = id => document.getElementById(id);
let monsters = [], collections = [], selected = null, editorMode = null;
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const shown = value => value === null || value === undefined || value === '' ? '—' : esc(value);
const badge = value => `<span class="monster-badge">${esc(value)}</span>`;
async function request(path, method='GET', body) {
  const response = await fetch(api+path, {method, headers:body===undefined?{}:{'Content-Type':'application/json'}, body:body===undefined?undefined:JSON.stringify(body)});
  if (!response.ok) {const value=await response.json().catch(()=>({}));throw Error(typeof value.detail==='string'?value.detail:JSON.stringify(value.detail));}
  return response.status===204?null:response.json();
}
function notice(text, id='quick-message') {$(id).textContent=text;}
async function refresh() {
  const params = new URLSearchParams();
  if ($('monster-search').value) params.set('q',$('monster-search').value);
  if ($('completeness-filter').value) params.set('completeness',$('completeness-filter').value);
  [monsters,collections] = await Promise.all([request('/monsters?'+params),request('/collections')]);
  if (selected) selected=await request(`/monsters/${selected.id}`).catch(()=>null);
  renderList();renderDetails();renderCollections();
}
function renderList() {
  $('monster-list').innerHTML = monsters.map(m=>`<article class="monster-row"><div><button type="button" data-action="open" data-id="${m.id}"><b>${esc(m.name)}</b></button> ${badge(m.completeness.level)}<small>Level ${m.level} · HP ${m.max_hp}</small></div></article>`).join('') || '<p>No matching monsters.</p>';
}
const field = (name,label,value,type='text',extra='') => `<label>${label}<input name="${name}" type="${type}" value="${esc(value ?? '')}" ${extra}></label>`;
const textArea = (name,label,value) => `<label>${label}<textarea name="${name}" rows="2">${esc(value)}</textarea></label>`;
function entryRow(kind,row={}) {
  const fields = kind==='speeds' ? field('type','Movement type',row.type||'land')+field('feet','Feet',row.feet,'number','min="1"') :
    kind==='skills' ? field('name','Skill',row.name)+field('modifier','Modifier',row.modifier,'number') :
    kind==='attacks' ? field('name','Name',row.name)+field('type','Type',row.type)+field('actions','Actions',row.actions)+field('bonus','Attack bonus',row.bonus,'number')+field('traits','Traits (comma separated)',(row.traits||[]).join(', '))+field('damage','Damage',row.damage)+textArea('effect','Effect',row.effect) :
    kind==='abilities' ? field('name','Name',row.name)+field('actions','Actions or passive',row.actions)+field('traits','Traits (comma separated)',(row.traits||[]).join(', '))+field('trigger','Trigger',row.trigger)+field('requirements','Requirements',row.requirements)+field('dc','DC',row.dc,'number')+textArea('description','Description',row.description) :
    field('name','Name',row.name)+textArea('description','Description',row.description)+`<label class="inline"><input name="offensive" type="checkbox" ${row.offensive?'checked':''}>Offensive spell</label>`;
  return `<div class="repeat-row" data-kind="${kind}">${fields}<button type="button" data-action="remove-row">Remove</button></div>`;
}
const repeat = (kind,title,rows=[]) => `<div class="repeat-list" data-kind="${kind}"><h3>${title}</h3><div class="repeat-rows">${rows.map(row=>entryRow(kind,row)).join('')}</div><button type="button" data-action="add-row" data-kind="${kind}">Add ${title.toLowerCase().replace(/s$/,'')}</button></div>`;
function renderEditor() {
  if (!selected||!editorMode) { $('monster-editor').innerHTML='';return; }
  const m=selected, quick=editorMode==='quick';
  let html=`<form id="monster-form"><div class="monster-grid">${field('name','Name',m.name,'text','required maxlength="120"')}${field('level','Level',m.level,'number','required min="-1" max="25"')}${field('max_hp','Maximum HP',m.max_hp,'number','required min="1"')}</div>`;
  if (!quick) html+=`<details open><summary>General information and traits</summary>${field('traits','Traits (comma separated)',m.traits.join(', '))}</details>
    <details><summary>Defenses and saving throws</summary><div class="monster-grid">${field('ac','AC',m.ac,'number')}${field('fortitude','Fortitude',m.fortitude,'number')}${field('reflex','Reflex',m.reflex,'number')}${field('will','Will',m.will,'number')}</div></details>
    <details><summary>Perception, senses, and skills</summary><div class="monster-grid">${field('perception','Perception',m.perception,'number')}${field('senses','Senses (comma separated)',m.senses.join(', '))}</div>${repeat('skills','Skills',Object.entries(m.skills).map(([name,modifier])=>({name,modifier})))}</details>
    <details><summary>Movement</summary>${repeat('speeds','Speeds',m.speeds)}</details>
    <details><summary>Attacks</summary>${repeat('attacks','Attacks',m.attacks)}</details>
    <details><summary>Special abilities</summary>${repeat('abilities','Abilities',m.abilities)}</details>
    <details><summary>Spellcasting</summary>${repeat('spellcasting','Spellcasting entries',m.spellcasting)}</details>
    <details><summary>Source references and GM notes</summary><div class="monster-grid">${field('source_book','Source book',m.source_book)}${field('source_page','Page',m.source_page,'number','min="1"')}${field('source_url','Source URL',m.source_url,'url')}</div>${textArea('notes','GM notes',m.notes)}</details>`;
  html+=`<div class="monster-actions"><button>Save and continue editing</button><button type="button" data-action="close-editor">Close editor</button></div></form>`;
  $('monster-editor').innerHTML=html;
}
function readRows(kind) {
  return [...document.querySelectorAll(`.repeat-list[data-kind="${kind}"] .repeat-row`)].map(row=>{
    const get=name=>row.querySelector(`[name="${name}"]`);
    if(kind==='speeds') return {type:get('type').value.trim(),feet:Number(get('feet').value)};
    if(kind==='skills') return {name:get('name').value.trim(),modifier:get('modifier').value===''?null:Number(get('modifier').value)};
    const action = value => value.trim()==='' ? null : /^\d+$/.test(value.trim()) ? Number(value.trim()) : value.trim();
    const terms = value => value.split(',').map(term=>term.trim()).filter(Boolean);
    if(kind==='attacks') return {name:get('name').value.trim(),type:get('type').value.trim()||null,actions:action(get('actions').value),bonus:get('bonus').value===''?null:Number(get('bonus').value),traits:terms(get('traits').value),damage:get('damage').value,effect:get('effect').value};
    if(kind==='abilities') return {name:get('name').value.trim(),actions:action(get('actions').value),traits:terms(get('traits').value),trigger:get('trigger').value.trim()||null,requirements:get('requirements').value.trim()||null,description:get('description').value,dc:get('dc').value===''?null:Number(get('dc').value)};
    return {name:get('name').value.trim(),description:get('description').value,offensive:get('offensive').checked};
  }).filter(row=>row.name || (kind==='speeds'&&row.feet>0));
}
function formValue(form) {
  const fd=new FormData(form), m={...selected};
  for(const key of ['name','level','max_hp']) m[key]=key==='name'?String(fd.get(key)).trim():Number(fd.get(key));
  if(editorMode==='detailed') {
    for(const key of ['ac','fortitude','reflex','will','perception','source_page']) m[key]=fd.get(key)===''?null:Number(fd.get(key));
    for(const key of ['source_book','source_url','notes']) m[key]=String(fd.get(key)||'');
    for(const key of ['traits','senses']) m[key]=String(fd.get(key)||'').split(',').map(x=>x.trim()).filter(Boolean);
    m.speeds=readRows('speeds');m.attacks=readRows('attacks');m.abilities=readRows('abilities');m.spellcasting=readRows('spellcasting');
    m.skills=Object.fromEntries(readRows('skills').filter(row=>row.name&&row.modifier!==null).map(row=>[row.name,row.modifier]));
  }
  delete m.id;delete m.completeness;return m;
}
function renderDetails() {
  $('monster-details').hidden=!selected;if(!selected)return;
  const m=selected,c=m.completeness;
  $('detail-header').innerHTML=`<h3>${esc(m.name)} ${badge(c.level)}</h3><p>Level ${m.level} · HP ${m.max_hp}</p>`;
  $('missing-fields').textContent=c.next_level?`${c.next_level} requires: ${c.missing_for_next.join(', ')}.`:'Detailed: no further fields required.';
  $('monster-summary').innerHTML=`<div class="monster-grid"><p>AC: ${shown(m.ac)}</p><p>Fortitude: ${shown(m.fortitude)}</p><p>Reflex: ${shown(m.reflex)}</p><p>Will: ${shown(m.will)}</p><p>Perception: ${shown(m.perception)}</p><p>Speed: ${m.speeds.length?m.speeds.map(s=>`${esc(s.type)} ${s.feet} ft`).join(', '):'—'}</p></div><p>Attacks: ${m.attacks.length?m.attacks.map(x=>esc(x.name)).join(', '):'—'} · Abilities: ${m.abilities.length?m.abilities.map(x=>esc(x.name)).join(', '):'—'} · Spells: ${m.spellcasting.length?m.spellcasting.map(x=>esc(x.name)).join(', '):'—'}</p>`;
  renderEditor();
}
function renderCollections() {
  $('collection-list').innerHTML=collections.map(c=>`<article class="collection-row"><div class="monster-actions"><h3>${esc(c.name)}</h3><button data-action="delete-collection" data-id="${c.id}" class="danger">Delete collection</button></div><div>${c.monsters.map(m=>`<div>${esc(m.name)} ${badge(m.completeness.level)} <button data-action="open" data-id="${m.id}">Open</button><button data-action="remove-collection-monster" data-id="${c.id}" data-monster="${m.id}">Remove</button></div>`).join('')||'<p>No monsters yet.</p>'}</div><div class="monster-actions"><select class="collection-monster"><option value="">Choose monster</option>${monsters.map(m=>`<option value="${m.id}">${esc(m.name)} — ${esc(m.completeness.level)}</option>`).join('')}</select><button data-action="add-collection-monster" data-id="${c.id}">Add monster</button></div></article>`).join('')||'<p>No session collections yet.</p>';
}
async function openMonster(id) {selected=await request(`/monsters/${id}`);editorMode=null;renderDetails();$('monster-details').scrollIntoView({block:'start'});}
$('quick-add').addEventListener('submit',async event=>{event.preventDefault();try{const fd=new FormData(event.target);const m=await request('/monsters','POST',{name:String(fd.get('name')).trim(),level:Number(fd.get('level')),max_hp:Number(fd.get('max_hp'))});event.target.reset();selected=m;editorMode=null;await refresh();notice(`Created ${m.name}. Open Detailed Editor to add more information.`);$('monster-details').scrollIntoView({block:'start'});}catch(error){notice(error.message);}});
$('monster-search').addEventListener('input',()=>refresh().catch(error=>notice(error.message)));
$('completeness-filter').addEventListener('change',()=>refresh().catch(error=>notice(error.message)));
$('monster-list').addEventListener('click',event=>{const b=event.target.closest('[data-action="open"]');if(b)openMonster(Number(b.dataset.id)).catch(error=>notice(error.message));});
$('monster-details').addEventListener('click',async event=>{const b=event.target.closest('button');if(!b||!selected)return;try{
  if(b.id==='quick-edit'){editorMode='quick';renderEditor();}
  else if(b.id==='detailed-edit'){editorMode='detailed';renderEditor();}
  else if(b.id==='duplicate-monster'){selected=await request(`/monsters/${selected.id}/duplicate`,'POST');editorMode=null;await refresh();}
  else if(b.id==='delete-monster'){if(!confirm(`Delete ${selected.name}?`))return;await request(`/monsters/${selected.id}`,'DELETE');selected=null;editorMode=null;await refresh();}
  else if(b.id==='export-monster'){const value=await request(`/monsters/${selected.id}/export`);const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`monster-${selected.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  else if(b.dataset.action==='close-editor'){editorMode=null;renderEditor();}
  else if(b.dataset.action==='add-row'){b.closest('.repeat-list').querySelector('.repeat-rows').insertAdjacentHTML('beforeend',entryRow(b.dataset.kind));}
  else if(b.dataset.action==='remove-row'){b.closest('.repeat-row').remove();}
}catch(error){notice(error.message);}});
$('monster-details').addEventListener('submit',async event=>{if(event.target.id!=='monster-form')return;event.preventDefault();try{if(!event.target.reportValidity())return;selected=await request(`/monsters/${selected.id}`,'PUT',formValue(event.target));await refresh();notice('Monster saved. Continue editing or close the editor.');}catch(error){notice(error.message);}});
$('monster-import').addEventListener('change',async event=>{const file=event.target.files[0];if(!file)return;try{const imported=await request('/import','POST',JSON.parse(await file.text()));selected=imported[0]||null;editorMode=null;await refresh();notice(`Imported ${imported.length} monster(s).`,'import-message');}catch(error){notice(error.message,'import-message');}event.target.value='';});
$('collection-add').addEventListener('submit',async event=>{event.preventDefault();try{await request('/collections','POST',{name:new FormData(event.target).get('name')});event.target.reset();await refresh();}catch(error){notice(error.message);}});
$('collection-list').addEventListener('click',async event=>{const b=event.target.closest('button[data-action]');if(!b)return;try{
  if(b.dataset.action==='open')return openMonster(Number(b.dataset.id));
  if(b.dataset.action==='add-collection-monster'){const id=Number(b.closest('.collection-row').querySelector('.collection-monster').value);if(id)await request(`/collections/${b.dataset.id}/monsters`,'POST',{monster_id:id});}
  if(b.dataset.action==='remove-collection-monster')await request(`/collections/${b.dataset.id}/monsters/${b.dataset.monster}`,'DELETE');
  if(b.dataset.action==='delete-collection'){if(!confirm('Delete this collection? Monsters remain in the library.'))return;await request(`/collections/${b.dataset.id}`,'DELETE');}
  await refresh();
}catch(error){notice(error.message);}});
refresh().catch(error=>notice(error.message));
