"""Encounter Builder routes and SQLite persistence."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field, field_validator

from master.pages import layout
from shared.database.storage import connect


FOLDER = Path(__file__).resolve().parent
spec = spec_from_file_location("pf2e_encounter_calculator", FOLDER / "calculator.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load encounter calculator")
calculator = module_from_spec(spec)
spec.loader.exec_module(calculator)


class Creature(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    level: int = Field(strict=True, ge=-1, le=25)
    quantity: int = Field(strict=True, ge=1)
    notes: str = Field(default="", max_length=1000)
    url: str = Field(default="", max_length=500)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a creature name")
        return value.strip()

    @field_validator("url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        if value and (urlparse(value).scheme not in {"http", "https"} or not urlparse(value).netloc):
            raise ValueError("Use an http or https creature URL")
        return value


class EncounterInput(BaseModel):
    party_level: int = Field(default=1, strict=True, ge=1, le=20)
    party_size: int = Field(default=4, strict=True, ge=2, le=8)
    target: str = "Moderate"
    creatures: list[Creature] = Field(default_factory=list)

    @field_validator("target")
    @classmethod
    def valid_target(cls, value: str) -> str:
        if value not in calculator.BASE_BUDGETS:
            raise ValueError("Choose a listed difficulty")
        return value


class SavedEncounter(EncounterInput):
    name: str = Field(min_length=1, max_length=120)
    notes: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter an encounter name")
        return value.strip()


def initialize(database_path: Path) -> None:
    with connect(database_path) as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS encounters (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                party_level INTEGER NOT NULL,
                party_size INTEGER NOT NULL,
                target TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS encounter_creatures (
                id INTEGER PRIMARY KEY,
                encounter_id INTEGER NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                name TEXT NOT NULL,
                level INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT ''
            );
        """)


def page() -> str:
    levels = "".join(f'<option value="{n}">{n}</option>' for n in range(1, 21))
    sizes = "".join(f'<option value="{n}"{" selected" if n == 4 else ""}>{n}</option>' for n in range(2, 9))
    difficulties = "".join(f'<option value="{name}"{" selected" if name == "Moderate" else ""}>{name}</option>' for name in calculator.BASE_BUDGETS)
    body = f"""
    <link rel="stylesheet" href="/tools/encounter-builder/style.css">
    <nav aria-label="Breadcrumb"><a class="back-link" href="/">← All tools</a></nav>
    <header class="encounter-heading"><div><h1>Encounter Builder</h1><p>Plan encounters for a campaign and party.</p><p>Use PF2e Remaster GM Core XP targets.</p></div></header>
    <div class="encounter-layout">
      <section class="encounter-card" aria-labelledby="party-heading">
        <h2 id="party-heading">Party and target</h2>
        <div class="field-grid">
          <label>Party level<select id="party-level">{levels}</select></label>
          <label>Number of characters<select id="party-size">{sizes}</select></label>
          <label>Desired difficulty<select id="target">{difficulties}</select></label>
        </div>
        <p class="muted">All characters are assumed to be the same level. The budget changes with party size; the standard XP award does not.</p>
      </section>
      <section class="encounter-card" aria-labelledby="creatures-heading">
        <h2 id="creatures-heading">Creatures</h2>
        <div class="template-row"><label>Quick template<select id="template"><option value="">Choose a template</option></select></label><button id="apply-template" type="button">Use template</button></div>
        <div id="creature-list" class="creature-list"></div>
        <button id="add-creature" type="button">Add creature</button>
        <p class="muted">Enter creatures manually. Levels outside party level −4 to +4 have no supported XP value.</p>
      </section>
      <section class="encounter-card summary-card" aria-labelledby="summary-heading">
        <h2 id="summary-heading">Encounter XP</h2>
        <div class="summary-grid">
          <div class="total-box"><span>Total creature XP</span><strong id="total-xp" aria-live="polite">0</strong></div>
          <div><span>Selected target</span><strong id="selected-target">Moderate</strong></div>
          <div><span>Adjusted target XP</span><strong id="adjusted-target">80</strong></div>
          <div><span>Remaining before target</span><strong id="remaining-xp">80</strong></div>
          <div><span>Difference from target</span><strong id="difference-xp">−80</strong></div>
        </div>
        <p id="comparison" class="comparison"></p>
        <h3>Compare with all targets</h3><div id="budget-list" class="budget-list"></div>
        <h3>XP awards</h3><p id="award-guidance"></p>
        <p class="muted">The adjusted budget is for building this encounter. The standard award shown above is per character, with no division by party size. For other creature totals, consult GM Core XP Awards.</p>
        <h3>GM reminders</h3><ul id="warnings"></ul>
        <p id="calculation-error" class="error" role="alert" hidden></p>
      </section>
      <section class="encounter-card" aria-labelledby="save-heading">
        <h2 id="save-heading">Save or load</h2>
        <div class="save-fields"><label>Encounter name<input id="encounter-name" type="text" maxlength="120" placeholder="Bridge ambush"></label><label>Encounter notes<textarea id="encounter-notes" rows="2" maxlength="2000"></textarea></label></div>
        <div class="save-actions"><button id="save-encounter" type="button">Save new</button><button id="resave-encounter" type="button" disabled>Save changes</button><button id="duplicate-encounter" type="button" disabled>Duplicate</button><button id="delete-encounter" type="button" disabled>Delete</button></div>
        <label>Saved encounters<select id="saved-list"><option value="">Choose saved encounter</option></select></label>
        <button id="load-encounter" type="button">Load selected</button>
        <p id="save-status" role="status"></p>
      </section>
    </div>
    <aside class="encounter-card sources-card"><h2>Rules and scope</h2>
      <p>XP targets guide encounter design; encounters between targets do not have a published exact difficulty cutoff. Creature abilities, terrain, and tactics matter too.</p>
      <p><a href="/tools/rules-reference">Rules Quick Reference</a> · <a href="https://2e.aonprd.com/Rules.aspx?ID=2716" target="_blank" rel="noopener noreferrer">GM Core: Encounter Design</a> · <a href="https://2e.aonprd.com/Rules.aspx?ID=2649" target="_blank" rel="noopener noreferrer">GM Core: XP Awards</a> · <a href="https://2e.aonprd.com/Rules.aspx?ID=2652" target="_blank" rel="noopener noreferrer">GM Core: Party Size</a></p>
    </aside>
    <script src="/tools/encounter-builder/app.js" defer></script>
    """
    return layout("Encounter Builder", body)


def _row_to_encounter(connection, row) -> dict:
    creatures = connection.execute(
        "SELECT name, level, quantity, notes, url FROM encounter_creatures WHERE encounter_id = ? ORDER BY position, id",
        (row[0],),
    ).fetchall()
    return {
        "id": row[0], "name": row[1], "party_level": row[2], "party_size": row[3],
        "target": row[4], "notes": row[5],
        "creatures": [dict(zip(("name", "level", "quantity", "notes", "url"), item)) for item in creatures],
    }


def _insert_creatures(connection, encounter_id: int, creatures: list[Creature]) -> None:
    connection.executemany(
        "INSERT INTO encounter_creatures (encounter_id, position, name, level, quantity, notes, url) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(encounter_id, index, item.name, item.level, item.quantity, item.notes, item.url) for index, item in enumerate(creatures)],
    )


def register(app: FastAPI, database_path: Path) -> None:
    @app.get("/tools/encounter-builder", response_class=HTMLResponse)
    def encounter_page() -> str:
        return page()

    @app.get("/tools/encounter-builder/style.css")
    def style() -> FileResponse:
        return FileResponse(FOLDER / "style.css", media_type="text/css")

    @app.get("/tools/encounter-builder/app.js")
    def script() -> FileResponse:
        return FileResponse(FOLDER / "app.js", media_type="text/javascript")

    @app.post("/api/encounter-builder/calculate")
    def calculate_route(values: EncounterInput) -> dict:
        return calculator.calculate(values.party_level, values.party_size, values.target, [item.model_dump() for item in values.creatures])

    @app.get("/api/encounter-builder/templates")
    def templates(party_level: int = 1) -> list[dict]:
        try:
            return calculator.available_templates(party_level)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/api/encounter-builder/encounters")
    def list_encounters() -> list[dict]:
        with connect(database_path) as connection:
            rows = connection.execute("SELECT id, name, party_level, party_size, target FROM encounters ORDER BY name COLLATE NOCASE, id").fetchall()
        return [dict(zip(("id", "name", "party_level", "party_size", "target"), row)) for row in rows]

    @app.get("/api/encounter-builder/encounters/{encounter_id}")
    def get_encounter(encounter_id: int) -> dict:
        with connect(database_path) as connection:
            row = connection.execute("SELECT id, name, party_level, party_size, target, notes FROM encounters WHERE id = ?", (encounter_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Encounter not found")
            return _row_to_encounter(connection, row)

    @app.post("/api/encounter-builder/encounters", status_code=201)
    def create_encounter(values: SavedEncounter) -> dict:
        with connect(database_path) as connection:
            cursor = connection.execute(
                "INSERT INTO encounters (name, party_level, party_size, target, notes) VALUES (?, ?, ?, ?, ?)",
                (values.name, values.party_level, values.party_size, values.target, values.notes),
            )
            encounter_id = cursor.lastrowid
            _insert_creatures(connection, encounter_id, values.creatures)
        return get_encounter(encounter_id)

    @app.put("/api/encounter-builder/encounters/{encounter_id}")
    def update_encounter(encounter_id: int, values: SavedEncounter) -> dict:
        with connect(database_path) as connection:
            cursor = connection.execute(
                "UPDATE encounters SET name = ?, party_level = ?, party_size = ?, target = ?, notes = ? WHERE id = ?",
                (values.name, values.party_level, values.party_size, values.target, values.notes, encounter_id),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Encounter not found")
            connection.execute("DELETE FROM encounter_creatures WHERE encounter_id = ?", (encounter_id,))
            _insert_creatures(connection, encounter_id, values.creatures)
        return get_encounter(encounter_id)

    @app.post("/api/encounter-builder/encounters/{encounter_id}/duplicate", status_code=201)
    def duplicate_encounter(encounter_id: int) -> dict:
        source = get_encounter(encounter_id)
        source.pop("id")
        source["name"] += " (copy)"
        return create_encounter(SavedEncounter(**source))

    @app.delete("/api/encounter-builder/encounters/{encounter_id}", status_code=204)
    def delete_encounter(encounter_id: int) -> None:
        with connect(database_path) as connection:
            cursor = connection.execute("DELETE FROM encounters WHERE id = ?", (encounter_id,))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Encounter not found")
