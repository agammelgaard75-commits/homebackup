"""Conditions Tracker routes and SQLite persistence.

Integration contract: combatants are addressed by (combat_id, combatant_id), where
combatant_id is the stable id inside Phase 5 state_json. No combatant is copied.
The /api/conditions/combat/{id}/summary endpoint is the Phase 5 read interface.
"""

from contextlib import closing
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import re
import sqlite3

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from master.pages import layout
from shared.database.storage import connect

FOLDER = Path(__file__).resolve().parent


def _load(name: str):
    spec = spec_from_file_location(f"pf2e_conditions_{name}", FOLDER / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {name}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


library = _load("library")
logic = _load("logic")


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid")
    combat_id: int | None = Field(default=None, strict=True, gt=0)
    combatant_id: int | None = Field(default=None, strict=True, gt=0)
    subject_id: int | None = Field(default=None, strict=True, gt=0)


class ConditionInput(Target):
    slug: str
    value: int | None = Field(default=None, strict=True, ge=1, le=99)
    source: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=500)
    temporary: bool = True
    duration_kind: str = "manual"
    controller_id: int | None = Field(default=None, strict=True, gt=0)
    duration_event: str = "end"
    rounds_remaining: int | None = Field(default=None, strict=True, ge=1, le=999)
    custom_duration: str = Field(default="", max_length=160)
    quickened_restriction: str = Field(default="", max_length=160)
    damage_type: str = Field(default="", max_length=60)
    damage_expression: str = Field(default="", max_length=40)
    recovery_dc: int = Field(default=15, strict=True, ge=1, le=100)


class ConditionEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: int | None = Field(default=None, strict=True, ge=1, le=99)
    source: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=500)
    temporary: bool | None = None
    duration_kind: str | None = None
    controller_id: int | None = Field(default=None, strict=True, gt=0)
    duration_event: str | None = None
    rounds_remaining: int | None = Field(default=None, strict=True, ge=1, le=999)
    custom_duration: str | None = Field(default=None, max_length=160)
    quickened_restriction: str | None = Field(default=None, max_length=160)
    damage_type: str | None = Field(default=None, max_length=60)
    damage_expression: str | None = Field(default=None, max_length=40)
    recovery_dc: int | None = Field(default=None, strict=True, ge=1, le=100)


class NewSubject(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class Recovery(BaseModel):
    success: bool
    roll: int | None = Field(default=None, strict=True, ge=1, le=20)
    note: str = Field(default="", max_length=160)


class Reduction(BaseModel):
    amount: int = Field(default=1, strict=True, ge=1, le=99)


FIELDS = ("id", "combat_id", "combatant_id", "subject_id", "slug", "value", "source", "notes",
          "temporary", "duration_kind", "controller_id", "duration_event", "rounds_remaining",
          "custom_duration", "quickened_restriction", "damage_type", "damage_expression", "recovery_dc", "recovery_log")
KINDS = {"manual", "start_turn", "end_turn", "rounds", "recovery", "custom"}


def initialize(database_path: Path) -> None:
    with closing(connect(database_path)) as db, db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS condition_subjects (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS active_conditions (
                id INTEGER PRIMARY KEY,
                combat_id INTEGER REFERENCES combat_sessions(id) ON DELETE CASCADE,
                combatant_id INTEGER,
                subject_id INTEGER REFERENCES condition_subjects(id) ON DELETE CASCADE,
                slug TEXT NOT NULL,
                value INTEGER,
                source TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                temporary INTEGER NOT NULL DEFAULT 1,
                duration_kind TEXT NOT NULL DEFAULT 'manual',
                controller_id INTEGER,
                duration_event TEXT NOT NULL DEFAULT 'end',
                rounds_remaining INTEGER,
                custom_duration TEXT NOT NULL DEFAULT '',
                quickened_restriction TEXT NOT NULL DEFAULT '',
                damage_type TEXT NOT NULL DEFAULT '',
                damage_expression TEXT NOT NULL DEFAULT '',
                recovery_dc INTEGER NOT NULL DEFAULT 15,
                recovery_log TEXT NOT NULL DEFAULT '[]',
                active INTEGER NOT NULL DEFAULT 1,
                CHECK ((combat_id IS NOT NULL AND combatant_id IS NOT NULL AND subject_id IS NULL)
                    OR (combat_id IS NULL AND combatant_id IS NULL AND subject_id IS NOT NULL))
            );
            CREATE INDEX IF NOT EXISTS active_conditions_combat ON active_conditions(combat_id, combatant_id);
            CREATE INDEX IF NOT EXISTS active_conditions_subject ON active_conditions(subject_id);
            CREATE UNIQUE INDEX IF NOT EXISTS active_conditions_one_source_combat
                ON active_conditions(combat_id, combatant_id, slug, source, damage_type)
                WHERE active = 1 AND combat_id IS NOT NULL;
            CREATE UNIQUE INDEX IF NOT EXISTS active_conditions_one_source_standalone
                ON active_conditions(subject_id, slug, source, damage_type)
                WHERE active = 1 AND subject_id IS NOT NULL;
        """)


def _target_clause(target: Target, db):
    if target.subject_id is not None and target.combat_id is None and target.combatant_id is None:
        if db.execute("SELECT 1 FROM condition_subjects WHERE id=?", (target.subject_id,)).fetchone() is None:
            raise HTTPException(404, "Temporary character not found")
        return "subject_id = ?", (target.subject_id,)
    if target.combat_id is not None and target.combatant_id is not None and target.subject_id is None:
        row = db.execute("SELECT state_json FROM combat_sessions WHERE id=?", (target.combat_id,)).fetchone()
        if row is None or not any(actor["id"] == target.combatant_id for actor in json.loads(row[0])["combatants"]):
            raise HTTPException(404, "Combatant not found")
        return "combat_id = ? AND combatant_id = ?", (target.combat_id, target.combatant_id)
    raise HTTPException(422, "Choose one standalone character or one combatant")


def _rows(db, clause: str, params: tuple) -> list[dict]:
    records = db.execute(f"SELECT {', '.join(FIELDS)} FROM active_conditions WHERE active = 1 AND ({clause}) ORDER BY id", params).fetchall()
    return [dict(zip(FIELDS, row), temporary=bool(row[8]), recovery_log=json.loads(row[-1])) for row in records]


def _validate(row: dict, db) -> None:
    definition = library.LIBRARY.get(row["slug"])
    if definition is None:
        raise HTTPException(422, "Choose a verified condition")
    duration_stunned = row["slug"] == "stunned" and row.get("value") is None and row["duration_kind"] != "manual"
    if definition["valued"] != (row.get("value") is not None) and not duration_stunned:
        raise HTTPException(422, "This condition requires a value" if definition["valued"] else "This condition has no numerical value")
    if row["duration_kind"] not in KINDS or row["duration_event"] not in {"start", "end"}:
        raise HTTPException(422, "Choose a valid duration")
    if row["duration_kind"] in {"start_turn", "end_turn", "rounds"} and row["controller_id"] is None:
        raise HTTPException(422, "Choose the creature controlling this duration")
    if row["duration_kind"] == "rounds" and row["rounds_remaining"] is None:
        raise HTTPException(422, "Enter a positive round count")
    if row["duration_kind"] == "custom" and not row["custom_duration"].strip():
        raise HTTPException(422, "Describe the custom duration")
    if row["slug"] == "persistent-damage":
        if not row["damage_type"].strip() or not re.fullmatch(r"(?:[1-9]\d*|[1-9]\d*d[1-9]\d*(?:[+-]\d+)?)", row["damage_expression"].strip(), re.I):
            raise HTTPException(422, "Enter damage type and fixed amount or dice expression (such as 1d6)")
    if row.get("controller_id") is not None and row.get("combat_id") is not None:
        state = json.loads(db.execute("SELECT state_json FROM combat_sessions WHERE id=?", (row["combat_id"],)).fetchone()[0])
        if not any(actor["id"] == row["controller_id"] for actor in state["combatants"]):
            raise HTTPException(422, "Duration controller is not in this combat")


def _view(db, target: Target) -> dict:
    clause, params = _target_clause(target, db)
    rows = _rows(db, clause, params)
    return {"instances": rows, "visible": logic.visible(rows),
            "penalties": logic.penalty_summary(rows), "actions": logic.action_guidance(rows),
            "persistent_groups": logic.persistent_groups(rows), "upcoming": logic.upcoming(rows)}


def page() -> str:
    body = """
    <link rel="stylesheet" href="/tools/conditions/style.css">
    <nav><a class="back-link" href="/">← All tools</a> · <a href="/tools/combat-tracker">Combat Tracker</a> · <a href="/tools/healing-death">Healing &amp; Death Helper</a></nav>
    <h1>Conditions Tracker</h1><p>Keep condition reminders close at hand during play.</p><p>Record sources and durations; confirm changes at the table.</p>
    <div class="condition-grid">
      <section class="condition-card"><h2>Combatant</h2><label>Saved combat<select id="combat"><option value="">Standalone</option></select></label><label>Character or monster<select id="target"></select></label><div class="inline"><input id="subject-name" maxlength="120" placeholder="Temporary character name"><button id="add-subject" type="button">Add</button></div><button id="delete-subject" type="button">Remove standalone character</button><p id="turn-context" class="hint"></p><div id="turn-reminders"></div><h3>Current conditions</h3><div id="active"></div><h3>Penalty and action guidance</h3><div id="guidance"></div><h3>Persistent damage recovery record</h3><div id="recovery-history"></div></section>
      <section class="condition-card"><h2>Apply condition</h2><label>Find condition<input id="search" type="search" placeholder="Search name or effect"></label><label>Condition<select id="condition"></select></label><div id="rule-detail"></div><div class="form-grid"><label>Value<input id="value" type="number" min="1" max="99" value="1"></label><label>Source<input id="source" maxlength="120" placeholder="Spell, creature, or rule"></label><label>Duration<select id="duration"><option value="manual">Until manually removed</option><option value="start_turn">Until start of a creature's turn</option><option value="end_turn">Until end of a creature's turn</option><option value="rounds">Number of rounds</option><option value="recovery">Until recovery succeeds</option><option value="custom">Custom</option></select></label><label>Controlling creature<select id="controller"></select></label><label>Round tick<select id="duration-event"><option value="end">End of turn</option><option value="start">Start of turn</option></select></label><label>Rounds<input id="rounds" type="number" min="1" value="1"></label><label>Custom duration<input id="custom-duration" maxlength="160"></label><label>Notes<input id="notes" maxlength="500"></label><label>Quickened action restriction<input id="quickened-restriction" maxlength="160" placeholder="e.g. Stride or Strike"></label><label>Persistent damage type<input id="damage-type" maxlength="60" placeholder="fire"></label><label>Persistent amount<input id="damage-expression" maxlength="40" placeholder="1d6"></label><label>Recovery DC<input id="recovery-dc" type="number" min="1" value="15"></label></div><label class="check"><input id="temporary" type="checkbox" checked> Temporary</label><button id="apply" type="button">Apply condition</button><p id="message" role="status"></p></section>
    </div>
    <section class="condition-card"><h2>Rules reference</h2><p>Penalties of the same type generally use the worst applicable value. A condition with multiple sources uses the highest value; reducing a valued condition reduces each source. Derived conditions are shown without extra stored records. Durations and recovery remain GM decisions.</p><p><a href="/tools/rules-reference">Rules Quick Reference</a> · <a href="https://2e.aonprd.com/Conditions.aspx" target="_blank" rel="noopener noreferrer">Player Core conditions</a> · <a href="https://2e.aonprd.com/Rules.aspx?ID=2428" target="_blank" rel="noopener noreferrer">Start of turn</a> · <a href="https://2e.aonprd.com/Rules.aspx?ID=2430" target="_blank" rel="noopener noreferrer">End of turn</a></p></section>
    <script src="/tools/conditions/app.js" defer></script>
    """
    return layout("Conditions Tracker", body)


def register(app: FastAPI, database_path: Path) -> None:
    @app.get("/tools/conditions", response_class=HTMLResponse)
    def conditions_page() -> str:
        return page()

    @app.get("/tools/conditions/style.css")
    def css() -> FileResponse:
        return FileResponse(FOLDER / "style.css", media_type="text/css")

    @app.get("/tools/conditions/app.js")
    def js() -> FileResponse:
        return FileResponse(FOLDER / "app.js", media_type="text/javascript")

    @app.get("/api/conditions/library")
    def condition_library(q: str = "") -> list[dict]:
        query = q.strip().lower()
        return [row for row in library.LIBRARY.values() if query in (row["name"] + " " + row["summary"] + " " + row["effects"]).lower()]

    @app.get("/api/conditions/targets")
    def targets() -> dict:
        with closing(connect(database_path)) as db:
            subjects = [{"id": ident, "name": name} for ident, name in db.execute("SELECT id,name FROM condition_subjects ORDER BY name,id")]
            combats = [{"id": ident, "name": name, "round": state["round"], "active_id": state["active_id"],
                        "combatants": [{"id": actor["id"], "name": actor["name"]} for actor in state["combatants"]]}
                       for ident, name, raw in db.execute("SELECT id,name,state_json FROM combat_sessions ORDER BY id DESC")
                       for state in [json.loads(raw)]]
        return {"subjects": subjects, "combats": combats}

    @app.post("/api/conditions/subjects", status_code=201)
    def add_subject(values: NewSubject) -> dict:
        name = values.name.strip()
        if not name:
            raise HTTPException(422, "Enter a name")
        with closing(connect(database_path)) as db, db:
            ident = db.execute("INSERT INTO condition_subjects(name) VALUES (?)", (name,)).lastrowid
        return {"id": ident, "name": name}

    @app.delete("/api/conditions/subjects/{subject_id}", status_code=204)
    def delete_subject(subject_id: int) -> None:
        with closing(connect(database_path)) as db, db:
            if db.execute("DELETE FROM condition_subjects WHERE id=?", (subject_id,)).rowcount == 0:
                raise HTTPException(404, "Temporary character not found")

    @app.get("/api/conditions/active")
    def active(combat_id: int | None = None, combatant_id: int | None = None, subject_id: int | None = None) -> dict:
        with closing(connect(database_path)) as db:
            return _view(db, Target(combat_id=combat_id, combatant_id=combatant_id, subject_id=subject_id))

    @app.post("/api/conditions/active", status_code=201)
    def add_condition(values: ConditionInput) -> dict:
        row = values.model_dump()
        row["source"] = row["source"].strip()
        row["damage_type"] = row["damage_type"].strip().lower()
        row["damage_expression"] = row["damage_expression"].strip().lower()
        with closing(connect(database_path)) as db, db:
            clause, params = _target_clause(values, db)
            _validate(row, db)
            # Reapplying the same source edits its instance. Other sources stay independent.
            existing = db.execute(f"SELECT id FROM active_conditions WHERE active=1 AND ({clause}) AND slug=? AND source=? AND damage_type=?",
                                  (*params, row["slug"], row["source"], row["damage_type"])).fetchone()
            columns = [field for field in FIELDS if field not in {"id", "recovery_log"}]
            if existing:
                db.execute(f"UPDATE active_conditions SET {', '.join(f'{field}=?' for field in columns)} WHERE id=?",
                           (*[row[field] for field in columns], existing[0]))
                ident = existing[0]
            else:
                ident = db.execute(f"INSERT INTO active_conditions({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                                   tuple(row[field] for field in columns)).lastrowid
            return {"id": ident, **_view(db, values)}

    @app.patch("/api/conditions/active/{instance_id}")
    def edit_condition(instance_id: int, values: ConditionEdit) -> dict:
        edits = values.model_dump(exclude_unset=True)
        with closing(connect(database_path)) as db, db:
            rows = _rows(db, "id=?", (instance_id,))
            if not rows:
                raise HTTPException(404, "Condition source not found")
            row = {**rows[0], **edits}
            _validate(row, db)
            if edits:
                try:
                    db.execute(f"UPDATE active_conditions SET {', '.join(f'{key}=?' for key in edits)} WHERE id=?", (*edits.values(), instance_id))
                except sqlite3.IntegrityError as error:
                    raise HTTPException(409, "That source already has this condition; edit it instead") from error
            return _view(db, Target(combat_id=row["combat_id"], combatant_id=row["combatant_id"], subject_id=row["subject_id"]))

    @app.delete("/api/conditions/active/{instance_id}", status_code=204)
    def remove_condition(instance_id: int) -> None:
        with closing(connect(database_path)) as db, db:
            if db.execute("DELETE FROM active_conditions WHERE id=?", (instance_id,)).rowcount == 0:
                raise HTTPException(404, "Condition source not found")

    @app.post("/api/conditions/active/{instance_id}/reduce")
    def reduce_condition(instance_id: int, values: Reduction) -> dict:
        with closing(connect(database_path)) as db, db:
            rows = _rows(db, "id=?", (instance_id,))
            if not rows:
                raise HTTPException(404, "Condition source not found")
            row = rows[0]
            if row["value"] is None:
                raise HTTPException(422, "Condition has no numerical value")
            clause, params = _target_clause(Target(combat_id=row["combat_id"], combatant_id=row["combatant_id"], subject_id=row["subject_id"]), db)
            sources = _rows(db, clause + " AND slug=?", (*params, row["slug"]))
            for source in sources:
                remaining = source["value"] - values.amount
                if remaining > 0:
                    db.execute("UPDATE active_conditions SET value=? WHERE id=?", (remaining, source["id"]))
                else:
                    db.execute("DELETE FROM active_conditions WHERE id=?", (source["id"],))
            return _view(db, Target(combat_id=row["combat_id"], combatant_id=row["combatant_id"], subject_id=row["subject_id"]))

    @app.post("/api/conditions/active/{instance_id}/recovery")
    def record_recovery(instance_id: int, values: Recovery) -> dict:
        with closing(connect(database_path)) as db, db:
            rows = _rows(db, "id=?", (instance_id,))
            if not rows:
                raise HTTPException(404, "Condition source not found")
            row = rows[0]
            if row["slug"] != "persistent-damage":
                raise HTTPException(422, "Recovery log is for persistent damage")
            log = row["recovery_log"] + [values.model_dump()]
            db.execute("UPDATE active_conditions SET recovery_log=?, active=? WHERE id=?",
                       (json.dumps(log), 0 if values.success else 1, instance_id))
            return {"removed": values.success, "recovery_log": log}

    @app.get("/api/conditions/recovery-history")
    def recovery_history(combat_id: int | None = None, combatant_id: int | None = None,
                         subject_id: int | None = None) -> list[dict]:
        with closing(connect(database_path)) as db:
            clause, params = _target_clause(Target(combat_id=combat_id, combatant_id=combatant_id, subject_id=subject_id), db)
            records = db.execute(f"SELECT id,damage_type,damage_expression,source,recovery_log FROM active_conditions WHERE ({clause}) AND slug='persistent-damage' AND recovery_log != '[]' ORDER BY id", params).fetchall()
            return [{"id": ident, "damage_type": damage_type, "damage_expression": amount,
                     "source": source, "checks": json.loads(log)} for ident, damage_type, amount, source, log in records]

    @app.get("/api/conditions/reminders")
    def turn_reminders(event: str, actor_id: int, combat_id: int | None = None,
                       combatant_id: int | None = None, subject_id: int | None = None) -> list[dict]:
        target = Target(combat_id=combat_id, combatant_id=combatant_id, subject_id=subject_id)
        with closing(connect(database_path)) as db:
            clause, params = _target_clause(target, db)
            return logic.reminders(_rows(db, clause, params), event, actor_id,
                                   target.combatant_id if target.combat_id else target.subject_id)

    @app.get("/api/conditions/combat/{combat_id}/summary")
    def combat_summary(combat_id: int) -> dict:
        with closing(connect(database_path)) as db:
            raw = db.execute("SELECT state_json FROM combat_sessions WHERE id=?", (combat_id,)).fetchone()
            if raw is None:
                raise HTTPException(404, "Combat not found")
            state = json.loads(raw[0])
            result = {}
            for actor in state["combatants"]:
                rows = _rows(db, "combat_id=? AND combatant_id=?", (combat_id, actor["id"]))
                result[str(actor["id"])] = {"visible": logic.visible(rows), "actions": logic.action_guidance(rows),
                                            "reminders_start": logic.reminders(rows, "start", actor["id"], actor["id"]),
                                            "reminders_end": logic.reminders(rows, "end", actor["id"], actor["id"])}
            return result
