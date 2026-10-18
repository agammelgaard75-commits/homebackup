"""Healing & Death Helper API. Writes Combat HP and Phase 6 conditions atomically."""

from contextlib import closing
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from master.pages import layout
from shared.database.storage import connect

FOLDER = Path(__file__).resolve().parent


def _load(name):
    spec = spec_from_file_location(f"pf2e_healing_{name}", FOLDER / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load healing {name}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rules = _load("rules")
storage = _load("storage")


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid")
    combat_id: int | None = Field(default=None, strict=True, gt=0)
    combatant_id: int | None = Field(default=None, strict=True, gt=0)
    subject_id: int | None = Field(default=None, strict=True, gt=0)


class Action(Target):
    action: str
    critical: bool = False
    own_critical_failure: bool = False
    nonlethal: bool = False
    significant_creature: bool = False
    move_initiative: bool = False
    roll: int | None = Field(default=None, strict=True, ge=1, le=20)
    modifier: int = Field(default=0, strict=True)
    manual_degree: str | None = None
    use_hero_points: bool = False
    amount: int | None = Field(default=None, strict=True, ge=0)
    status_slug: str | None = None
    status_value: int | None = Field(default=None, strict=True, ge=0, le=99)
    hero_points: int | None = Field(default=None, strict=True, ge=0, le=3)
    current_hp: int | None = Field(default=None, strict=True, ge=0)
    max_hp: int | None = Field(default=None, strict=True, gt=0)
    temp_hp: int | None = Field(default=None, strict=True, ge=0)
    healer: str = Field(default="", max_length=120)
    proficiency: str | None = None
    dc: int | None = Field(default=None, strict=True)
    dice_total: int | None = Field(default=None, strict=True)
    has_battle_medicine: bool = False
    continue_hour: bool = False
    override_immunity: bool = False
    override_note: str = Field(default="", max_length=300)


class TimeAdvance(Target):
    minutes: int = Field(strict=True, ge=1, le=10080)


class NewSubject(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    max_hp: int = Field(strict=True, gt=0)
    current_hp: int = Field(strict=True, ge=0)
    hero_points: int = Field(default=0, strict=True, ge=0, le=3)


def initialize(database_path: Path) -> None:
    with closing(connect(database_path)) as db, db:
        storage.initialize(db)


def _target(values) -> dict:
    return {key: value for key in ("combat_id", "combatant_id", "subject_id") if (value := getattr(values, key)) is not None}


def _status(db, current) -> dict:
    records = storage.treatments(db, current)
    now = current["game_minutes"]
    public = {key: value for key, value in current.items() if key not in {"state", "actor", "profile_id"}}
    public["recovery_dc"] = 10 + current["dying"] if current["dying"] else None
    public["death_threshold"] = rules.death_threshold(current["doomed"])
    public["at_death_threshold"] = current["dying"] >= public["death_threshold"]
    public["treat_immune_until"] = storage.immunity_until(records, "treat")
    public["treat_eligible"] = now >= public["treat_immune_until"]
    public["treatments"] = records
    public["active_turn"] = current["state"] is not None and current["state"]["active_id"] == current["target"]["combatant_id"]
    return public


def _degree(values: Action, dc: int) -> str:
    if values.manual_degree is not None:
        if values.manual_degree not in rules.DEGREES:
            raise ValueError("Choose a valid degree of success")
        return values.manual_degree
    if values.roll is None:
        raise ValueError("Enter a d20 roll or choose a degree of success")
    return rules.check_degree(values.roll, values.modifier, dc)


def _plan(db, current: dict, values: Action) -> dict:
    action = values.action
    hp, maximum, dying, wounded, doomed = (current[key] for key in ("current_hp", "max_hp", "dying", "wounded", "doomed"))
    result = {"action": action, "current_hp": hp, "dying": dying, "wounded": wounded,
              "doomed": doomed, "hero_points": current["hero_points"],
              "unconscious": bool(current["unconscious"]), "death_threshold": rules.death_threshold(doomed),
              "fatal": dying >= rules.death_threshold(doomed), "note": ""}
    if action == "knockout":
        if current["type"] not in {"PC", "standalone"} and not values.significant_creature:
            raise ValueError("Ordinary monsters do not automatically use PC dying rules; confirm this is a significant creature")
        if dying:
            raise ValueError("Already Dying; use Damage While Dying")
        result.update(rules.knockout(wounded, doomed, values.critical, values.own_critical_failure, values.nonlethal))
        result.update(current_hp=0, note="At 0 HP. Move initiative directly before the turn that caused knockout if appropriate.")
    elif action == "recovery":
        if values.roll is None:
            raise ValueError("Enter a natural d20 recovery roll")
        result.update(rules.recovery(dying, doomed, values.roll))
        if result["loses_dying"]:
            result["wounded"] = wounded + 1
            result["unconscious"] = hp == 0
        if values.use_hero_points:
            if result["change"] <= 0 or current["hero_points"] < 1:
                raise ValueError("Heroic recovery needs a Dying increase and at least 1 Hero Point")
            result.update(dying=0, current_hp=0, wounded=wounded, hero_points=0,
                          unconscious=True, fatal=False, heroic=True, note="Spent all Hero Points; Wounded is unchanged.")
    elif action == "dying_damage":
        result.update(rules.damage_while_dying(dying, doomed, values.critical, values.own_critical_failure))
        if values.use_hero_points:
            if current["hero_points"] < 1:
                raise ValueError("At least 1 Hero Point is required")
            result.update(dying=0, current_hp=0, wounded=wounded, hero_points=0,
                          unconscious=True, fatal=False, heroic=True, note="Spent all Hero Points; Wounded is unchanged.")
    elif action == "hero":
        if dying < 1 or current["hero_points"] < 1:
            raise ValueError("Heroic recovery requires Dying and at least 1 Hero Point")
        if current["state"] is not None and current["state"]["active_id"] != current["target"]["combatant_id"]:
            raise ValueError("Use this at the dying character's turn start; for an imminent increase use the Hero Point option on that action")
        result.update(dying=0, current_hp=0, wounded=wounded, hero_points=0,
                      unconscious=True, fatal=False, heroic=True, note="Spent all Hero Points; Wounded is unchanged.")
    elif action == "stabilize":
        if hp != 0 or dying < 1:
            raise ValueError("Stabilize requires a dying patient at 0 HP")
        dc = 15 + dying
        degree = _degree(values, dc)
        result.update(rules.first_aid(dying, doomed, degree))
        if result["loses_dying"]:
            result.update(wounded=wounded + 1, unconscious=True)
        result["note"] = "Administer First Aid takes 2 actions and normally requires a healer's toolkit."
    elif action == "manual_heal":
        if hp is None or maximum is None or values.amount is None or values.amount < 1:
            raise ValueError("Set HP and enter a positive healing amount")
        new_hp = min(maximum, hp + values.amount)
        result["current_hp"] = new_hp
        if dying and new_hp > 0:
            result.update(dying=0, wounded=wounded + 1, unconscious=False)
        elif hp == 0 and new_hp > 0 and current["unconscious"]:
            result["unconscious"] = False
        result["note"] = "Other healing does not remove Wounded; full HP plus 10 minutes' rest can end it."
    elif action == "treatment":
        if hp is None or maximum is None:
            raise ValueError("Set patient HP before treatment")
        kind = values.status_slug  # 'treat' or 'battle', avoiding another model field
        if kind not in {"treat", "battle"}:
            raise ValueError("Choose Treat Wounds or Battle Medicine")
        if not values.healer.strip() or values.proficiency is None or values.dc is None:
            raise ValueError("Enter healer, Medicine rank, and DC")
        if kind == "battle" and not values.has_battle_medicine:
            raise ValueError("Healer must have Battle Medicine")
        rules.treatment_option(values.proficiency, values.dc)
        degree = _degree(values, values.dc)
        calculation = rules.treatment(values.proficiency, values.dc, degree, values.dice_total, kind, values.continue_hour)
        healer = values.healer.strip()
        records = storage.treatments(db, current)
        immune_until = storage.immunity_until(records, kind, healer)
        if current["game_minutes"] < immune_until and not values.override_immunity:
            raise ValueError(f"Patient is immune to this treatment until game minute {immune_until}")
        if values.override_immunity and not values.override_note.strip():
            raise ValueError("Describe the feat or GM reason for overriding immunity")
        change = calculation["hp_change"]
        if change < 0:
            absorbed = min(current["temp_hp"], -change)
            new_hp = max(0, hp + change + absorbed)
            result["temp_hp"] = current["temp_hp"] - absorbed
            if dying == 0 and new_hp == 0:
                if current["type"] in {"PC", "standalone"} or values.significant_creature:
                    knockout = rules.knockout(wounded, doomed)
                    result.update(dying=knockout["dying"], unconscious=True, fatal=knockout["fatal"])
                else:
                    result["warning"] = "Ordinary creature at 0 HP: review the knockout rule; PC Dying was not applied."
            elif dying:
                damage = rules.damage_while_dying(dying, doomed)
                result.update(dying=damage["dying"], fatal=damage["fatal"])
        else:
            new_hp = min(maximum, hp + change)
            if dying and new_hp > 0:
                result.update(dying=0, wounded=wounded + 1, unconscious=False)
            elif hp == 0 and new_hp > 0 and current["unconscious"]:
                result["unconscious"] = False
            if calculation["removes_wounded_if_hp_restored"] and new_hp > hp:
                result["wounded"] = 0
        result.update(calculation, current_hp=new_hp, healer=healer, proficiency=values.proficiency,
                      immunity_until_minute=current["game_minutes"] + calculation["immunity_minutes"],
                      game_minutes_after=current["game_minutes"] + calculation["duration_minutes"],
                      actual_hp_change=new_hp - hp,
                      note="Treat Wounds advances game time by its 10-minute or 1-hour duration. Battle Medicine takes 1 action. Immunity is measured from the start of treatment.")
    elif action == "rest_full_hp":
        if hp is None or maximum is None or hp != maximum or current["full_hp_since_minute"] is None or current["game_minutes"] - current["full_hp_since_minute"] < 10:
            raise ValueError("Reach full HP, advance at least 10 game minutes, and confirm the character rested")
        result.update(wounded=0, note="Confirmed full HP and 10 minutes' rest; Wounded ends.")
    elif action == "manual_status":
        if values.status_slug in {"dying", "wounded", "doomed"} and values.status_value is not None:
            result[values.status_slug] = values.status_value
        elif values.status_slug == "unconscious" and values.status_value in {0, 1}:
            result["unconscious"] = bool(values.status_value)
        elif values.status_slug == "hero_points" and values.hero_points is not None:
            result["hero_points"] = values.hero_points
        else:
            raise ValueError("Choose a status and valid value")
        result["death_threshold"] = rules.death_threshold(result["doomed"])
        result["fatal"] = result["dying"] >= result["death_threshold"]
        result["note"] = "Manual override; check special abilities and the full rule."
    elif action == "manual_hp":
        if values.max_hp is None or values.current_hp is None:
            raise ValueError("Enter current and maximum HP")
        if values.current_hp > values.max_hp:
            raise ValueError("Current HP cannot exceed maximum HP")
        result.update(current_hp=values.current_hp, max_hp=values.max_hp,
                      temp_hp=current["temp_hp"] if values.temp_hp is None else values.temp_hp,
                      note="Manual HP edit; use Knocked Out or Manual Status to record Dying when needed.")
    else:
        raise ValueError("Unknown healing action")
    if result["dying"] >= result["death_threshold"]:
        result["fatal"] = True
        result["warning"] = f"Dying {result['dying']} reaches death threshold {result['death_threshold']}; review before confirming."
    return result


def _move_initiative(state, victim_id):
    active_id = state["active_id"]
    if active_id is None or active_id == victim_id or victim_id not in state["order"]:
        return False
    state["order"].remove(victim_id)
    state["order"].insert(state["order"].index(active_id), victim_id)
    if victim_id in state["pending"] and victim_id != active_id:
        state["pending"].remove(victim_id)
    return True


def _apply(db, current, values: Action, plan):
    old_dying, old_unconscious = current["dying"], current["unconscious"]
    if plan["current_hp"] != current["current_hp"] or "max_hp" in plan or "temp_hp" in plan:
        storage.save_hp(db, current, plan["current_hp"], plan.get("max_hp"), plan.get("temp_hp", current["temp_hp"]))
    if values.action == "knockout" and current["actor"] is not None and values.move_initiative:
        if _move_initiative(current["state"], current["target"]["combatant_id"]):
            db.execute("UPDATE combat_sessions SET state_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                       (json.dumps(current["state"]), current["target"]["combat_id"]))
            plan["initiative_moved"] = True
    for slug in ("dying", "wounded", "doomed"):
        if plan[slug] != current[slug]:
            storage.set_condition(db, current, slug, plan[slug])
    if plan["hero_points"] != current["hero_points"]:
        storage.set_hero(db, current, plan["hero_points"])
    if plan["unconscious"] and not old_unconscious and plan["dying"] == 0:
        storage.set_condition(db, current, "unconscious", 1)
    if old_dying > 0 and plan["dying"] == 0 and plan["unconscious"]:
        storage.set_condition(db, current, "unconscious", 1)
    if not plan["unconscious"]:
        storage.remove_own_unconscious(db, current)
    if values.action == "treatment":
        target = current["target"]
        columns = list(target) + ["kind","healer","started_minute","duration_minutes","immunity_until_minute",
                                  "proficiency","dc","degree","dice_total","hp_change","actual_hp_change","override_note"]
        vals = list(target.values()) + [plan["kind"],plan["healer"],current["game_minutes"],plan["duration_minutes"],
                                        plan["immunity_until_minute"],plan["proficiency"],plan["dc"],plan["degree"],
                                        plan["dice_total"],plan["hp_change"],plan["actual_hp_change"],values.override_note.strip()]
        db.execute(f"INSERT INTO healing_treatments({','.join(columns)}) VALUES ({','.join('?' for _ in vals)})", vals)
        if plan["duration_minutes"]:
            _, _, scope_kind, scope_id = storage.target_key(target)
            db.execute("UPDATE healing_clocks SET minutes=minutes+? WHERE scope_kind=? AND scope_id=?",
                       (plan["duration_minutes"], scope_kind, scope_id))
            if plan["actual_hp_change"] > 0 and plan["current_hp"] == current["max_hp"]:
                db.execute("UPDATE healing_profiles SET full_hp_since_minute=? WHERE id=?",
                           (plan["game_minutes_after"], current["profile_id"]))


def page():
    body = """
    <link rel="stylesheet" href="/tools/healing-death/style.css">
    <nav><a class="back-link" href="/">← All tools</a> · <a href="/tools/combat-tracker">Combat Tracker</a> · <a href="/tools/conditions">Conditions Tracker</a></nav>
    <h1>Healing &amp; Death Helper</h1><p>Track healing and death-related bookkeeping.</p>
    <section class="heal-card"><h2>Character status</h2>
      <div class="heal-row"><label>Saved combat<select id="combat"><option value="">Standalone</option></select></label><label>Patient<select id="patient"><option value="">Choose character</option></select></label></div>
      <div id="new-subject" class="heal-row"><label>Standalone name<input id="subject-name" maxlength="120" placeholder="Character name"></label><label>Max HP<input id="subject-max" type="number" min="1" value="20"></label><label>Current HP<input id="subject-hp" type="number" min="0" value="20"></label><button id="create-subject" type="button">Add character</button></div>
      <div id="status" class="heal-status">Choose a character.</div>
      <div id="manual" hidden><h3>Manual adjustments</h3><div class="heal-row"><label>Current HP<input id="manual-hp" type="number" min="0"></label><label>Max HP<input id="manual-max" type="number" min="1"></label><label>Temporary HP<input id="manual-temp" type="number" min="0"></label><button id="save-hp" type="button">Save HP</button></div>
        <div class="heal-row"><label>Condition<select id="status-slug"><option value="dying">Dying</option><option value="wounded">Wounded</option><option value="doomed">Doomed</option><option value="unconscious">Unconscious (0 or 1)</option><option value="hero_points">Hero Points (0–3)</option></select></label><label>Value<input id="status-value" type="number" min="0" max="99" value="0"></label><button id="save-status" type="button">Save value</button></div>
        <div class="heal-row"><strong id="game-time">Game minute 0</strong><label>Advance by minutes<input id="advance-minutes" type="number" min="1" value="10"></label><button id="advance-time" type="button">Advance game time</button><button id="rest-full" type="button">Confirm 10-minute rest at full HP</button></div>
      </div>
    </section>
    <div class="heal-grid"><section class="heal-card"><h2>Emergency actions</h2>
      <div class="heal-group"><h3>Knocked Out</h3><div class="heal-row"><label><input id="ko-critical" type="checkbox"> Attacker critical hit</label><label><input id="ko-own-critical" type="checkbox"> Own critical failure</label><label><input id="ko-nonlethal" type="checkbox"> Nonlethal</label><label><input id="ko-significant" type="checkbox"> Significant NPC or monster</label><label><input id="ko-move" type="checkbox" checked> Offer initiative move</label></div><button id="preview-knockout" type="button">Preview Knocked Out</button></div>
      <div class="heal-group"><h3>Recovery check</h3><p id="recovery-hint" class="hint">Normally at the start of the dying character's turn.</p><div class="heal-row"><label>Natural d20<input id="recovery-roll" type="number" min="1" max="20"></label><label><input id="recovery-hero" type="checkbox"> Use Hero Points if Dying increases</label><button id="preview-recovery" type="button">Preview recovery</button></div></div>
      <div class="heal-group"><h3>Damage while Dying</h3><div class="heal-row"><label><input id="dying-critical" type="checkbox"> Attacker critical hit</label><label><input id="dying-own-critical" type="checkbox"> Own critical failure</label><label><input id="dying-hero" type="checkbox"> Use Hero Points before increase</label><button id="preview-damage" type="button">Preview increase</button></div></div>
      <div class="heal-group"><h3>Administer First Aid: Stabilize</h3><p id="stabilize-hint" class="hint">Two actions and a healer's toolkit; persistent bleed is handled in Conditions Tracker.</p><div class="heal-row"><label>Natural d20<input id="aid-roll" type="number" min="1" max="20"></label><label>Medicine modifier<input id="aid-mod" type="number" value="0"></label><label>Or choose degree<select id="aid-degree"><option value="">Use roll</option><option value="critical_success">Critical success</option><option value="success">Success</option><option value="failure">Failure</option><option value="critical_failure">Critical failure</option></select></label><button id="preview-aid" type="button">Preview Stabilize</button></div></div>
      <button id="preview-hero" type="button">Use Hero Points at turn start</button>
    </section>
    <section class="heal-card"><h2>Healing</h2><div class="heal-group"><h3>Treat Wounds or Battle Medicine</h3><div class="heal-row"><label>Activity<select id="treatment-kind"><option value="treat">Treat Wounds · 10 minutes</option><option value="battle">Battle Medicine · 1 action</option></select></label><label>Healer<input id="healer" maxlength="120" placeholder="Healer name"></label><label>Medicine rank<select id="rank"><option value="trained">Trained</option><option value="expert">Expert</option><option value="master">Master</option><option value="legendary">Legendary</option></select></label><label>DC option<select id="treatment-dc"><option value="15">15 · 2d8 / 4d8</option><option value="20">20 · +10</option><option value="30">30 · +30</option><option value="40">40 · +50</option></select></label></div>
      <div class="heal-row"><label>Natural d20<input id="treatment-roll" type="number" min="1" max="20"></label><label>Medicine modifier<input id="treatment-mod" type="number" value="0"></label><label>Or choose degree<select id="treatment-degree"><option value="">Use roll</option><option value="critical_success">Critical success</option><option value="success">Success</option><option value="failure">Failure</option><option value="critical_failure">Critical failure</option></select></label><label>Rolled dice total<input id="dice-total" type="number" min="1" placeholder="2d8, 4d8, or 1d8"></label></div>
      <div class="heal-row"><label><input id="battle-feat" type="checkbox"> Healer has Battle Medicine</label><label><input id="continue-hour" type="checkbox"> Continue Treat Wounds to 1 hour total; double healing</label><label><input id="override-immunity" type="checkbox"> Override immunity</label><label>Override reason<input id="override-note" maxlength="300" placeholder="Feat or GM ruling"></label></div><button id="preview-treatment" type="button">Preview treatment</button>
      <p id="eligibility" class="hint"></p><div id="treatment-records"></div></div>
      <div class="heal-group"><h3>Manual Healing</h3><div class="heal-row"><label>HP restored<input id="heal-amount" type="number" min="1" value="1"></label><button id="preview-heal" type="button">Preview healing</button></div><p class="hint">A spell or other healing does not immediately remove Wounded. At full HP, confirm 10 minutes of rest separately.</p></div>
    </section></div>
    <section class="heal-card" id="preview-card" hidden><h2>Projected result</h2><div id="preview-result"></div><button id="confirm-action" type="button">Confirm change</button><button id="cancel-preview" type="button">Cancel</button></section>
    <p id="healing-message" role="status"></p>
    <section class="heal-card"><h2>Quick rules reference</h2><p>Recovery is a flat check at turn start, DC 10 + Dying. Critical success improves Dying by 2; critical failure worsens it by 2. Dying ends at 0 and normally raises Wounded. Doomed lowers the death threshold from 4. Heroic Recovery spends every Hero Point and preserves Wounded.</p><p>Treat Wounds normally takes 10 minutes and its one-hour immunity begins when treatment starts. Battle Medicine takes one action and has a separate one-day immunity for each healer and patient. Neither activity rolls dice automatically.</p><p><a href="/tools/rules-reference">Rules Quick Reference</a> · <a href="/tools/conditions">Conditions and persistent bleed</a> · <a href="https://2e.aonprd.com/Rules.aspx?ID=2324" target="_blank" rel="noopener noreferrer">Player Core p. 410: Knocked Out</a> · <a href="https://2e.aonprd.com/Rules.aspx?ID=2325" target="_blank" rel="noopener noreferrer">Player Core p. 411: Dying and Recovery</a> · <a href="https://2e.aonprd.com/Conditions.aspx?ID=99" target="_blank" rel="noopener noreferrer">Player Core p. 447: Wounded</a> · <a href="https://2e.aonprd.com/Skills.aspx?ID=42" target="_blank" rel="noopener noreferrer">Player Core pp. 241–242: First Aid and Treat Wounds</a> · <a href="https://2e.aonprd.com/Feats.aspx?ID=5125" target="_blank" rel="noopener noreferrer">Player Core p. 253: Battle Medicine</a> · <a href="https://2e.aonprd.com/Rules.aspx?ID=2333" target="_blank" rel="noopener noreferrer">Player Core p. 413: Hero Points</a></p></section>
    <script src="/tools/healing-death/app.js" defer></script>
    """
    return layout("Healing & Death", body)


def register(app: FastAPI, database_path: Path) -> None:
    @app.get("/tools/healing-death", response_class=HTMLResponse)
    def healing_page() -> str:
        return page()

    @app.get("/tools/healing-death/style.css")
    def css() -> FileResponse:
        return FileResponse(FOLDER / "style.css", media_type="text/css")

    @app.get("/tools/healing-death/app.js")
    def js() -> FileResponse:
        return FileResponse(FOLDER / "app.js", media_type="text/javascript")

    @app.get("/api/healing-death/targets")
    def targets() -> dict:
        with closing(connect(database_path)) as db:
            subjects = [{"id": ident, "name": name} for ident, name in db.execute("SELECT id,name FROM condition_subjects ORDER BY name,id")]
            combats = [{"id": ident, "name": name, "round": state["round"], "active_id": state["active_id"],
                        "combatants": [{"id": actor["id"], "name": actor["name"], "type": actor["type"]} for actor in state["combatants"]]}
                       for ident, name, raw in db.execute("SELECT id,name,state_json FROM combat_sessions ORDER BY id DESC") for state in [json.loads(raw)]]
            return {"subjects": subjects, "combats": combats}

    @app.post("/api/healing-death/subjects", status_code=201)
    def create_subject(values: NewSubject) -> dict:
        if values.current_hp > values.max_hp or not values.name.strip():
            raise HTTPException(422, "Enter a name and HP between 0 and maximum")
        with closing(connect(database_path)) as db, db:
            ident = db.execute("INSERT INTO condition_subjects(name) VALUES (?)", (values.name.strip(),)).lastrowid
            db.execute("INSERT INTO healing_profiles(subject_id,hero_points,standalone_max_hp,standalone_hp,full_hp_since_minute) VALUES (?,?,?,?,?)",
                       (ident, values.hero_points, values.max_hp, values.current_hp, 0 if values.current_hp == values.max_hp else None))
            return {"id": ident, "name": values.name.strip()}

    @app.get("/api/healing-death/status")
    def status(combat_id: int | None = None, combatant_id: int | None = None, subject_id: int | None = None) -> dict:
        try:
            with closing(connect(database_path)) as db, db:
                return _status(db, storage.load(db, {k:v for k,v in {"combat_id":combat_id,"combatant_id":combatant_id,"subject_id":subject_id}.items() if v is not None}))
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @app.post("/api/healing-death/preview")
    def preview(values: Action) -> dict:
        try:
            with closing(connect(database_path)) as db, db:
                return _plan(db, storage.load(db, _target(values)), values)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @app.post("/api/healing-death/apply")
    def apply(values: Action) -> dict:
        try:
            with closing(connect(database_path)) as db:
                db.execute("BEGIN IMMEDIATE")
                current = storage.load(db, _target(values))
                plan = _plan(db, current, values)
                _apply(db, current, values, plan)
                result = {"result": plan, "status": _status(db, storage.load(db, _target(values)))}
                db.commit()
                return result
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @app.post("/api/healing-death/time")
    def advance_time(values: TimeAdvance) -> dict:
        try:
            with closing(connect(database_path)) as db, db:
                target = _target(values)
                current = storage.load(db, target)
                _, _, kind, ident = storage.target_key(target)
                db.execute("UPDATE healing_clocks SET minutes=minutes+? WHERE scope_kind=? AND scope_id=?", (values.minutes,kind,ident))
                return _status(db, storage.load(db, target))
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @app.get("/api/healing-death/combat/{combat_id}/reminders")
    def combat_reminders(combat_id: int, actor_id: int) -> list[dict]:
        with closing(connect(database_path)) as db, db:
            try:
                current = storage.load(db, {"combat_id":combat_id,"combatant_id":actor_id})
            except ValueError as error:
                raise HTTPException(404, str(error)) from error
            if current["dying"] < 1:
                return []
            return [{"kind":"healing_recovery", "combatant_id":actor_id,
                     "text":f"{current['name']}: Dying {current['dying']}. At this turn's start, attempt a recovery flat check (DC {10 + current['dying']}); Heroic Recovery is available with a Hero Point.",
                     "dc":10 + current["dying"]}]
