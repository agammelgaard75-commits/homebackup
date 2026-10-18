const api = "/api/healing-death";
const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
let targets = {combats:[],subjects:[]}, current = null, pending = null;
const node = (tag,text="",cls="") => { const item=document.createElement(tag);item.textContent=text;if(cls)item.className=cls;return item; };
async function request(path,method="GET",body=null){
  const response=await fetch(api+path,{method,headers:body===null?{}:{"Content-Type":"application/json"},body:body===null?undefined:JSON.stringify(body)});
  if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(typeof data.detail==="string"?data.detail:`Request failed (${response.status})`);}
  return response.status===204?null:response.json();
}
function message(text,error=false){$("healing-message").textContent=text;$("healing-message").classList.toggle("heal-error",error);}
function n(id){const value=$(id).value.trim();return value===""?null:Number(value);}
function combat(){return targets.combats.find(row=>String(row.id)===$("combat").value);}
function target(){const id=Number($("patient").value);return id?(combat()?{combat_id:Number($("combat").value),combatant_id:id}:{subject_id:id}):null;}
function query(object){return new URLSearchParams(object).toString();}
async function refreshTargets(){
  const oldCombat=$("combat").value,oldPatient=$("patient").value;
  targets=await request("/targets");$("combat").replaceChildren(new Option("Standalone characters",""));
  targets.combats.forEach(row=>$("combat").append(new Option(row.name,String(row.id))));
  const linked=params.get("combat_id");$("combat").value=oldCombat||(linked&&targets.combats.some(row=>String(row.id)===linked)?linked:"");
  fillPatients(oldPatient||params.get("combatant_id")||params.get("subject_id"));
}
function fillPatients(preferred=""){
  const list=combat()?.combatants||targets.subjects;
  $("patient").replaceChildren(new Option("Choose character",""));list.forEach(row=>$("patient").append(new Option(row.name,String(row.id))));
  $("patient").value=preferred&&list.some(row=>String(row.id)===String(preferred))?String(preferred):"";
  $("new-subject").hidden=!!combat();refreshStatus();
}
function pill(text,urgent=false,href=null){const item=node("span","",`heal-pill${urgent?" urgent":""}`);if(href){const a=node("a",text);a.href=href;item.append(a);}else item.textContent=text;return item;}
function duration(minutes){return `${Math.floor(minutes/60)}h ${minutes%60}m`;} 
async function refreshStatus(){
  pending=null;$("preview-card").hidden=true;
  const chosen=target();current=chosen?await request(`/status?${query(chosen)}`):null;
  renderStatus();
}
function renderStatus(){
  const box=$("status");box.replaceChildren();$("manual").hidden=!current;
  if(!current){box.append(node("p","Choose a combatant or add a standalone character.","hint"));return;}
  const t=target(),link=`/tools/conditions?${query(t)}`;
  box.append(pill(current.name),pill(`HP ${current.current_hp??"?"}/${current.max_hp??"?"}`,current.current_hp===0),pill(`Temp HP ${current.temp_hp}`));
  for(const slug of ["dying","wounded","doomed"]){box.append(pill(`${slug[0].toUpperCase()+slug.slice(1)} ${current[slug]}`,slug==="dying"&&current.dying>0,link));}
  box.append(pill(current.unconscious?"Unconscious":"Conscious",current.unconscious,link),pill(`Hero Points ${current.hero_points}`));
  if(current.at_death_threshold)box.append(node("p",`Death threshold ${current.death_threshold} has been reached. Review the rule and any exception.`,"heal-warning"));
  if(current.current_hp===0&&!current.dying&&!current.unconscious)box.append(node("p","At 0 HP with no Dying or Unconscious condition recorded. Review Knocked Out.","heal-warning"));
  $("recovery-hint").textContent=current.dying?`Recovery flat check DC ${current.recovery_dc}, normally at the start of this character's turn.`:"Recovery checks become available while Dying.";
  $("stabilize-hint").textContent=current.dying?`Medicine DC ${15+current.dying}; two actions and a healer's toolkit.`:"Stabilize applies at 0 HP while Dying.";
  $("game-time").textContent=`Game time ${duration(current.game_minutes)} (minute ${current.game_minutes})`;
  $("manual-hp").value=current.current_hp??"";$("manual-max").value=current.max_hp??"";$("manual-temp").value=current.temp_hp;
  $("status-value").value=current[$("status-slug").value]??0;
  const immune=current.treat_immune_until>current.game_minutes;
  $("eligibility").textContent=immune?`Treat Wounds immunity ends at game minute ${current.treat_immune_until}.`:`Treat Wounds eligible now. Battle Medicine eligibility depends on the healer.`;
  const records=$("treatment-records");records.replaceChildren();
  if(!current.treatments.length)records.append(node("p","No treatments recorded.","hint"));
  current.treatments.slice(0,8).forEach(row=>records.append(node("div",`${row.kind==="treat"?"Treat Wounds":"Battle Medicine"} · ${row.healer} · minute ${row.started_minute} · DC ${row.dc} ${row.degree.replaceAll("_"," ")} · HP ${row.actual_hp_change>=0?"+":""}${row.actual_hp_change} · immunity through minute ${row.immunity_until_minute}${row.override_note?` · override: ${row.override_note}`:""}`,"heal-record")));
}
function base(){const selected=target();if(!selected)throw new Error("Choose a patient first.");return selected;}
function addLine(box,label,value){const p=node("p",`${label}: ${value}`);box.append(p);}
async function preview(action,options={}){
  try{
    const payload={...base(),action,...options};const plan=await request("/preview","POST",payload);
    pending=payload;const box=$("preview-result");box.replaceChildren();
    addLine(box,"Action",action.replaceAll("_"," "));
    if(plan.dc)addLine(box,"DC",plan.dc);
    if(plan.degree)addLine(box,"Degree",plan.degree.replaceAll("_"," "));
    if(plan.dice)addLine(box,"Dice",`${plan.dice}${plan.bonus?` + ${plan.bonus}`:""}${plan.duration_minutes===60?" · doubled after 1 hour":""}`);
    addLine(box,"Projected HP",`${plan.current_hp??"?"}/${plan.max_hp??current.max_hp}`);
    addLine(box,"Projected conditions",`Dying ${plan.dying}, Wounded ${plan.wounded}, Doomed ${plan.doomed}, ${plan.unconscious?"Unconscious":"Conscious"}`);
    addLine(box,"Hero Points",plan.hero_points);
    if(plan.immunity_until_minute!==undefined)addLine(box,"Immunity through game minute",plan.immunity_until_minute);
    if(plan.game_minutes_after!==undefined)addLine(box,"Game time after treatment",duration(plan.game_minutes_after));
    if(plan.warning)box.append(node("p",plan.warning,"heal-warning"));
    if(plan.note)box.append(node("p",plan.note,"hint"));
    $("preview-card").hidden=false;$("confirm-action").focus();message("Review the projected result, then confirm.");
  }catch(error){message(error.message,true);}
}
async function applyDirect(payload){try{const result=await request("/apply","POST",payload);await refreshStatus();message(result.result.warning||"Saved.",!!result.result.warning);}catch(error){message(error.message,true);}}
$("combat").onchange=()=>fillPatients();$("patient").onchange=refreshStatus;
$("status-slug").onchange=()=>{$("status-value").max=$("status-slug").value==="hero_points"?"3":"99";$("status-value").value=current?.[$("status-slug").value]??0;};
$("create-subject").onclick=async()=>{try{const row=await request("/subjects","POST",{name:$("subject-name").value,max_hp:n("subject-max"),current_hp:n("subject-hp")});await refreshTargets();$("patient").value=String(row.id);await refreshStatus();message("Standalone character added.");}catch(error){message(error.message,true);}};
$("save-hp").onclick=()=>applyDirect({...base(),action:"manual_hp",current_hp:n("manual-hp"),max_hp:n("manual-max"),temp_hp:n("manual-temp")});
$("save-status").onclick=()=>{const slug=$("status-slug").value,value=n("status-value");applyDirect({...base(),action:"manual_status",status_slug:slug,...(slug==="hero_points"?{hero_points:value}:{status_value:value})});};
$("advance-time").onclick=async()=>{try{current=await request("/time","POST",{...base(),minutes:n("advance-minutes")});renderStatus();message("Game time advanced.");}catch(error){message(error.message,true);}};
$("rest-full").onclick=()=>preview("rest_full_hp");
$("preview-knockout").onclick=()=>preview("knockout",{critical:$("ko-critical").checked,own_critical_failure:$("ko-own-critical").checked,nonlethal:$("ko-nonlethal").checked,significant_creature:$("ko-significant").checked,move_initiative:$("ko-move").checked});
$("preview-recovery").onclick=()=>preview("recovery",{roll:n("recovery-roll"),use_hero_points:$("recovery-hero").checked});
$("preview-damage").onclick=()=>preview("dying_damage",{critical:$("dying-critical").checked,own_critical_failure:$("dying-own-critical").checked,use_hero_points:$("dying-hero").checked});
$("preview-aid").onclick=()=>preview("stabilize",{roll:n("aid-roll"),modifier:n("aid-mod"),manual_degree:$("aid-degree").value||null});
$("preview-hero").onclick=()=>preview("hero");
$("treatment-kind").onchange=()=>{const battle=$("treatment-kind").value==="battle";if(battle)$("continue-hour").checked=false;$("battle-feat").parentElement.hidden=!battle;$("continue-hour").parentElement.hidden=battle;};
$("treatment-kind").dispatchEvent(new Event("change"));
$("preview-treatment").onclick=()=>preview("treatment",{status_slug:$("treatment-kind").value,healer:$("healer").value,proficiency:$("rank").value,dc:n("treatment-dc"),roll:n("treatment-roll"),modifier:n("treatment-mod"),manual_degree:$("treatment-degree").value||null,dice_total:n("dice-total"),has_battle_medicine:$("battle-feat").checked,continue_hour:$("continue-hour").checked,override_immunity:$("override-immunity").checked,override_note:$("override-note").value});
$("preview-heal").onclick=()=>preview("manual_heal",{amount:n("heal-amount")});
$("confirm-action").onclick=async()=>{if(!pending)return;try{const result=await request("/apply","POST",pending);pending=null;await refreshStatus();message(result.result.warning||"Change confirmed and saved.",!!result.result.warning);}catch(error){message(error.message,true);}};
$("cancel-preview").onclick=()=>{pending=null;$("preview-card").hidden=true;message("Preview canceled.");};
refreshTargets().catch(error=>message(error.message,true));
window.addEventListener("focus",()=>{if(target())refreshStatus().catch(()=>{});});
