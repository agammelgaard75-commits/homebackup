"""Local Combat Tracker page and automatically persisted command API."""

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
spec = spec_from_file_location("pf2e_combat_state", FOLDER / "state.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load combat state logic")
logic = module_from_spec(spec)
spec.loader.exec_module(logic)


class NewCombat(BaseModel):
    name: str = Field(default="New combat", max_length=120)
    source_encounter_id: int | None = Field(default=None, strict=True, gt=0)


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: str
    combatant_id: int | None = Field(default=None, strict=True)
    after_id: int | None = Field(default=None, strict=True)
    name: str | None = None
    type: str | None = None
    initiative: int | None = Field(default=None, strict=True)
    max_hp: int | None = Field(default=None, strict=True)
    current_hp: int | None = Field(default=None, strict=True)
    temp_hp: int | None = Field(default=None, strict=True)
    quantity: int | None = Field(default=None, strict=True)
    amount: int | None = Field(default=None, strict=True)
    direction: str | None = None
    notes: str | None = None
    label: str | None = None
    duration: str | None = None
    effect_index: int | None = Field(default=None, strict=True)


def initialize(database_path: Path) -> None:
    with closing(connect(database_path)) as connection, connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS combat_sessions (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                source_encounter_id INTEGER,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)


def _view(combat_id: int, state: dict) -> dict:
    view = {**state, "id": combat_id}
    view["combatants"] = [
        {**actor, "map_standard": logic.map_penalty(actor["attack_count"]), "map_agile": logic.map_penalty(actor["attack_count"], True)}
        for actor in state["combatants"]
    ]
    return view


def page() -> str:
    body = """
    <link rel="stylesheet" href="/tools/combat-tracker/style.css">
    <nav aria-label="Breadcrumb"><a class="back-link" href="/">← All tools</a></nav>
    <header class="combat-heading"><h1>Combat Tracker</h1><p>Track combat turns and session state.</p></header>
    <section class="combat-card setup-card">
      <div class="setup-grid">
        <label>New combat name<input id="new-name" maxlength="120" value="New combat"></label>
        <button id="new-combat" type="button">Create empty combat</button>
        <label>Phase 4 encounter<select id="source-list"><option value="">Choose saved encounter</option></select></label>
        <button id="import-combat" type="button">Create from encounter</button>
        <label>Saved combats<select id="combat-list"><option value="">Choose saved combat</option></select></label>
        <button id="load-combat" type="button">Load combat</button>
      </div>
    </section>
    <section id="exploration-handoff" class="combat-card" hidden><h2>Exploration handoff</h2><div id="exploration-handoff-list"></div><p class="hint">Review these reminders before entering initiative. No bonus or condition is applied automatically.</p></section>
    <div id="workspace" hidden>
      <section class="combat-card combat-toolbar">
        <div><label>Encounter name<input id="combat-name" maxlength="120"></label><span id="combat-status"></span></div>
        <div class="toolbar-buttons"><button id="rename-combat" type="button">Rename</button><button id="save-combat" type="button">Save now</button><button id="end-combat" type="button">End encounter</button><button id="resume-combat" type="button" hidden>Resume</button><a id="combat-rewards" href="/tools/treasure-xp" hidden>Open reward screen</a><button id="delete-combat" type="button" class="danger">Delete saved combat</button></div>
      </section>
      <section class="combat-card turn-banner">
        <div><span>Round</span><strong id="round-number">1</strong></div>
        <div><span>Active combatant</span><strong id="active-name">—</strong></div>
        <button id="next-turn" type="button" class="next-turn">Next Turn</button>
      </section>
      <section class="combat-card" aria-live="polite"><h2>Turn and condition reminders</h2><div id="condition-reminders"><p class="hint">No turn reminders.</p></div></section>
      <div class="combat-grid">
        <div>
          <section class="combat-card">
            <h2>Initiative order</h2><p class="hint">Highest first. Enemies normally win ties against PCs. Use arrows for manual order changes; edits save automatically.</p>
            <div id="initiative-list"></div>
            <h3>Delayed combatants</h3><div id="delayed-list"></div>
          </section>
          <section class="combat-card">
            <h2>Add combatants</h2>
            <div class="add-grid"><label>Name<input id="add-name" maxlength="120" placeholder="Spider"></label><label>Type<select id="add-type"><option>PC</option><option>NPC</option><option selected>monster</option></select></label><label>Quantity<input id="add-quantity" type="number" min="1" max="100" value="1"></label><label>Initiative<input id="add-initiative" type="number" placeholder="Optional"></label><label>Max HP<input id="add-max-hp" type="number" min="1" placeholder="Optional"></label><label>Current HP<input id="add-current-hp" type="number" min="0" placeholder="Optional"></label></div>
            <button id="add-combatant" type="button">Add combatant</button>
          </section>
        </div>
        <div>
          <section class="combat-card active-card"><h2>Current turn</h2><div id="active-controls"></div></section>
          <section class="combat-card"><h2>Selected combatant</h2><div id="selected-detail"></div></section>
        </div>
      </div>
    </div>
    <p id="combat-message" role="status"></p>
    <aside class="combat-card"><h2>Rules and reminders</h2>
      <p>Actions and reactions refresh at the start of that combatant's turn. Free actions do not use normal actions. Ready keeps initiative; use the Ready control only after choosing the readied action. Delay can change initiative when the combatant returns. Effect durations stay as written until you edit them.</p>
      <p>MAP counts any attack-trait action, including attacks other than Strikes. Choose the standard or agile value for the attack being made now. Some abilities change MAP. At 0 HP, consult the appropriate dying or knockout rules; this tracker makes no death decision.</p>
      <p><a href="/tools/rules-reference">Rules Quick Reference</a> · <a href="https://2e.aonprd.com/Rules.aspx?ID=2263" target="_blank" rel="noopener noreferrer">Player Core: Encounter Mode and Turns</a> · <a href="https://2e.aonprd.com/Rules.aspx?ID=2289" target="_blank" rel="noopener noreferrer">Player Core: Multiple Attack Penalty</a> · <a href="https://2e.aonprd.com/Rules.aspx?ID=2545" target="_blank" rel="noopener noreferrer">GM Core: Running Encounters</a> · <a href="https://2e.aonprd.com/Rules.aspx?ID=2324" target="_blank" rel="noopener noreferrer">Player Core: Getting Knocked Out</a></p>
    </aside>
    <script src="/tools/combat-tracker/app.js" defer></script>
    """
    return layout("Combat Tracker", body)


def register(app: FastAPI, database_path: Path) -> None:
    @app.get("/tools/combat-tracker", response_class=HTMLResponse)
    def combat_page() -> str:
        return page()

    @app.get("/tools/combat-tracker/style.css")
    def style() -> FileResponse:
        return FileResponse(FOLDER / "style.css", media_type="text/css")

    @app.get("/tools/combat-tracker/app.js")
    def script() -> FileResponse:
        return FileResponse(FOLDER / "app.js", media_type="text/javascript")

    @app.get("/api/combat-tracker/encounter-definitions")
    def encounter_definitions() -> list[dict]:
        with closing(connect(database_path)) as connection:
            rows = connection.execute("SELECT id, name FROM encounters ORDER BY name COLLATE NOCASE, id").fetchall()
        return [{"id": ident, "name": name} for ident, name in rows]

    @app.get("/api/combat-tracker/combats")
    def list_combats() -> list[dict]:
        with closing(connect(database_path)) as connection:
            rows = connection.execute("SELECT id, name, status, updated_at FROM combat_sessions ORDER BY updated_at DESC, id DESC").fetchall()
        return [dict(zip(("id", "name", "status", "updated_at"), row)) for row in rows]

    @app.post("/api/combat-tracker/combats", status_code=201)
    def create_combat(values: NewCombat) -> dict:
        try:
            state = logic.new_combat(values.name, values.source_encounter_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        with closing(connect(database_path)) as connection, connection:
            if values.source_encounter_id is not None:
                row = connection.execute("SELECT name FROM encounters WHERE id = ?", (values.source_encounter_id,)).fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Saved encounter not found")
                state["name"] = row[0]
                groups = connection.execute("SELECT name, quantity, notes FROM encounter_creatures WHERE encounter_id = ? ORDER BY position, id", (values.source_encounter_id,)).fetchall()
                for name, quantity, notes in groups:
                    for _ in range(quantity):
                        logic.add_combatant(state, name, "monster", notes=notes)
            cursor = connection.execute(
                "INSERT INTO combat_sessions (name, status, source_encounter_id, state_json) VALUES (?, ?, ?, ?)",
                (state["name"], state["status"], state["source_encounter_id"], json.dumps(state)),
            )
            ident = cursor.lastrowid
        return _view(ident, state)

    @app.get("/api/combat-tracker/combats/{combat_id}")
    def get_combat(combat_id: int) -> dict:
        with closing(connect(database_path)) as connection:
            row = connection.execute("SELECT state_json FROM combat_sessions WHERE id = ?", (combat_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Combat not found")
        return _view(combat_id, json.loads(row[0]))

    @app.post("/api/combat-tracker/combats/{combat_id}/command")
    def command(combat_id: int, values: Command) -> dict:
        with closing(connect(database_path)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute("SELECT state_json FROM combat_sessions WHERE id = ?", (combat_id,)).fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Combat not found")
                state = logic.apply(json.loads(row[0]), values.model_dump(exclude_unset=True))
                if values.op == "remove" and connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='active_conditions'").fetchone():
                    connection.execute("DELETE FROM active_conditions WHERE combat_id=? AND combatant_id=?", (combat_id, values.combatant_id))
                if values.op == "remove" and connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='healing_profiles'").fetchone():
                    connection.execute("DELETE FROM healing_profiles WHERE combat_id=? AND combatant_id=?", (combat_id, values.combatant_id))
                    connection.execute("DELETE FROM healing_treatments WHERE combat_id=? AND combatant_id=?", (combat_id, values.combatant_id))
                connection.execute(
                    "UPDATE combat_sessions SET name = ?, status = ?, state_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (state["name"], state["status"], json.dumps(state), combat_id),
                )
                connection.commit()
            except ValueError as error:
                connection.rollback()
                raise HTTPException(status_code=422, detail=str(error)) from error
            except Exception:
                connection.rollback()
                raise
        return _view(combat_id, state)

    @app.delete("/api/combat-tracker/combats/{combat_id}", status_code=204)
    def delete_combat(combat_id: int) -> None:
        with closing(connect(database_path)) as connection, connection:
            cursor = connection.execute("DELETE FROM combat_sessions WHERE id = ?", (combat_id,))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Combat not found")
            if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='healing_clocks'").fetchone():
                connection.execute("DELETE FROM healing_clocks WHERE scope_kind='combat' AND scope_id=?", (combat_id,))
