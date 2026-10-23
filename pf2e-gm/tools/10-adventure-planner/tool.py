"""Adventure & Session Planner: local records and narrow links to existing tools."""
from contextlib import closing
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from master.pages import layout
from shared.database.storage import connect

FOLDER = Path(__file__).resolve().parent
spec = spec_from_file_location("pf2e_adventure_logic", FOLDER / "logic.py")
logic = module_from_spec(spec)
spec.loader.exec_module(logic)
spec = spec_from_file_location("pf2e_adventure_encounter_calculator", FOLDER.parent / "03-encounter-builder" / "calculator.py")
encounter_calc = module_from_spec(spec)
spec.loader.exec_module(encounter_calc)

SCENE_TYPES = {"roleplaying", "exploration", "combat", "puzzle", "investigation", "travel", "other"}
SCENE_STATUSES = {"not_started", "active", "completed", "skipped"}
SESSION_STATUSES = {"planned", "active", "completed"}
CONNECTION_TYPES = {"leads_to", "clue_points_to", "alternative_route", "optional_scene"}
ENTITY_TABLES = {"npcs": "adventure_npcs", "clues": "adventure_clues", "items": "adventure_items"}
ENTITY_LINKS = {"npcs": "adventure_scene_npcs", "clues": "adventure_scene_clues", "items": "adventure_scene_items"}
ENTITY_KEYS = {"npcs": "npc_id", "clues": "clue_id", "items": "item_id"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AdventureInput(Strict):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1200)
    starting_situation: str = Field(default="", max_length=1200)
    main_objective: str = Field(default="", max_length=1200)
    suggested_level: int | None = Field(default=None, ge=1, le=20)
    expected_players: int | None = Field(default=None, ge=1, le=12)
    estimated_hours: float | None = Field(default=None, ge=0, le=1000)
    secrets: str = Field(default="", max_length=2000)
    outcomes: str = Field(default="", max_length=2000)
    gm_notes: str = Field(default="", max_length=5000)
    campaign_id: int | None = Field(default=None, gt=0)
    party_id: int | None = Field(default=None, gt=0)


class SceneInput(Strict):
    title: str = Field(min_length=1, max_length=120)
    type: str = "other"
    location: str = Field(default="", max_length=200)
    purpose: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=1200)
    complications: str = Field(default="", max_length=800)
    duration_minutes: int = Field(default=0, ge=0, le=10000)
    notes: str = Field(default="", max_length=3000)
    status: str = "not_started"
    completed_session_id: int | None = None


class NPCInput(Strict):
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(default="", max_length=200)
    personality: str = Field(default="", max_length=500)
    motivation: str = Field(default="", max_length=500)
    knows: str = Field(default="", max_length=800)
    wants: str = Field(default="", max_length=500)
    secret: str = Field(default="", max_length=800)
    status: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=1500)
    external_url: str = Field(default="", max_length=500)
    scene_ids: list[int] = Field(default_factory=list, max_length=100)


class ClueInput(Strict):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    location: str = Field(default="", max_length=200)
    reveals: str = Field(default="", max_length=1000)
    alternatives: str = Field(default="", max_length=500)
    discovered: bool = False
    discovered_scene_id: int | None = None
    discovered_session_id: int | None = None
    notes: str = Field(default="", max_length=1500)
    scene_ids: list[int] = Field(default_factory=list, max_length=100)


class ItemInput(Strict):
    name: str = Field(min_length=1, max_length=120)
    kind: str = "item"
    description: str = Field(default="", max_length=1000)
    starting_location: str = Field(default="", max_length=200)
    current_location: str = Field(default="", max_length=200)
    required: bool = False
    obtained: bool = False
    obtained_session_id: int | None = None
    notes: str = Field(default="", max_length=1500)
    scene_ids: list[int] = Field(default_factory=list, max_length=100)


class SessionInput(Strict):
    title: str = Field(min_length=1, max_length=120)
    number: int | None = Field(default=None, ge=1, le=10000)
    planned_minutes: int = Field(default=0, ge=0, le=10000)
    scene_ids: list[int] = Field(default_factory=list, max_length=100)
    objectives: str = Field(default="", max_length=1500)
    prep_notes: str = Field(default="", max_length=3000)
    actual_notes: str = Field(default="", max_length=3000)
    next_session_notes: str = Field(default="", max_length=3000)
    status: str = "planned"
    summary_markdown: str = Field(default="", max_length=20000)


class EventInput(Strict):
    text: str = Field(min_length=1, max_length=2000)
    kind: str = "note"
    scene_id: int | None = None
    game_time: str = Field(default="", max_length=100)


class ConnectionInput(Strict):
    from_scene_id: int
    to_scene_id: int
    kind: str = "leads_to"


class EncounterLinkInput(Strict):
    encounter_id: int = Field(gt=0)
    completed: bool = False
    completed_session_id: int | None = None


class ReorderInput(Strict):
    scene_ids: list[int] = Field(max_length=500)


class ImportInput(Strict):
    version: int
    adventure: dict
    scenes: list[dict] = Field(max_length=500)
    npcs: list[dict] = Field(max_length=500)
    clues: list[dict] = Field(max_length=500)
    items: list[dict] = Field(max_length=500)
    connections: list[dict] = Field(max_length=1000)
    encounters: list[dict] = Field(max_length=1000)
    sessions: list[dict] = Field(max_length=500)


def _db(path):
    db = connect(path)
    db.row_factory = sqlite3.Row
    return db


def _one(db, sql, args=()):
    row = db.execute(sql, args).fetchone()
    if row is None:
        raise HTTPException(404, "Record not found")
    return dict(row)


def _rows(db, sql, args=()):
    return [dict(row) for row in db.execute(sql, args)]


def _insert(db, table, data):
    keys = list(data)
    marks = ",".join("?" for _ in keys)
    cur = db.execute(f"INSERT INTO {table} ({','.join(keys)}) VALUES ({marks})", tuple(data.values()))
    return cur.lastrowid


def _update(db, table, record_id, data):
    if data:
        db.execute(f"UPDATE {table} SET {','.join(k + '=?' for k in data)} WHERE id=?", (*data.values(), record_id))


def _adventure(db, adventure_id):
    return _one(db, "SELECT * FROM adventures WHERE id=?", (adventure_id,))


def _belongs(db, table, record_id, adventure_id):
    return _one(db, f"SELECT * FROM {table} WHERE id=? AND adventure_id=?", (record_id, adventure_id))


def _validate_party(db, campaign_id, party_id):
    if campaign_id is not None:
        _one(db, "SELECT id FROM campaigns WHERE id=?", (campaign_id,))
    if party_id is not None:
        party = _one(db, "SELECT * FROM parties WHERE id=?", (party_id,))
        if campaign_id is not None and party["campaign_id"] != campaign_id:
            raise HTTPException(422, "Party does not belong to selected campaign")


def _scene_ids(db, adventure_id, scene_ids):
    if len(set(scene_ids)) != len(scene_ids):
        raise HTTPException(422, "Scene IDs must be unique")
    for scene_id in scene_ids:
        _belongs(db, "adventure_scenes", scene_id, adventure_id)


def _session_id(db, adventure_id, session_id):
    if session_id is not None:
        _belongs(db, "adventure_sessions", session_id, adventure_id)


def _import_scene_choice(value: str, allowed: set[str], field: str, scene_id: int, title: str) -> str:
    """Accept the UI's display labels while keeping stored values canonical."""
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"Scene {scene_id} ({title!r}): {field} {value!r} is invalid. Use: {choices}")
    return normalized


def _encounter(db, encounter_id):
    row = db.execute("SELECT * FROM encounters WHERE id=?", (encounter_id,)).fetchone()
    if row is None:
        return {"encounter_id": encounter_id, "missing": True}
    row = dict(row)
    creatures = _rows(db, "SELECT name,level,quantity,notes,url FROM encounter_creatures WHERE encounter_id=? ORDER BY position,id", (encounter_id,))
    try:
        result = encounter_calc.calculate(row["party_level"], row["party_size"], row["target"], creatures)
        xp, comparison = result["total_xp"], result["comparison"]
    except ValueError:
        xp, comparison = None, "Review encounter in Encounter Builder"
    return {"encounter_id": encounter_id, "missing": False, "name": row["name"], "creatures": creatures,
            "xp": xp, "difficulty": comparison, "target": row["target"]}


def _entity_rows(db, adventure_id, entity):
    table, links, key = ENTITY_TABLES[entity], ENTITY_LINKS[entity], ENTITY_KEYS[entity]
    result = _rows(db, f"SELECT * FROM {table} WHERE adventure_id=? ORDER BY id", (adventure_id,))
    for row in result:
        row["scene_ids"] = [r["scene_id"] for r in _rows(db, f"SELECT scene_id FROM {links} WHERE {key}=? ORDER BY scene_id", (row["id"],))]
    return result


def _snapshot(db, adventure_id):
    adventure = _adventure(db, adventure_id)
    adventure["campaign_name"] = (db.execute("SELECT name FROM campaigns WHERE id=?", (adventure["campaign_id"],)).fetchone() or [None])[0]
    adventure["party_name"] = (db.execute("SELECT name FROM parties WHERE id=?", (adventure["party_id"],)).fetchone() or [None])[0]
    scenes = _rows(db, "SELECT * FROM adventure_scenes WHERE adventure_id=? ORDER BY position,id", (adventure_id,))
    npcs, clues, items = (_entity_rows(db, adventure_id, key) for key in ("npcs", "clues", "items"))
    connections = _rows(db, "SELECT c.* FROM adventure_connections c JOIN adventure_scenes s ON s.id=c.from_scene_id WHERE s.adventure_id=? ORDER BY c.id", (adventure_id,))
    encounters = _rows(db, "SELECT l.* FROM adventure_scene_encounters l JOIN adventure_scenes s ON s.id=l.scene_id WHERE s.adventure_id=? ORDER BY l.id", (adventure_id,))
    for link in encounters:
        link.update(_encounter(db, link["encounter_id"]))
    sessions = _rows(db, "SELECT * FROM adventure_sessions WHERE adventure_id=? ORDER BY number,id", (adventure_id,))
    for session in sessions:
        session["scene_ids"] = [r["scene_id"] for r in _rows(db, "SELECT scene_id FROM adventure_session_scenes WHERE session_id=? ORDER BY position", (session["id"],))]
        session["events"] = _rows(db, "SELECT * FROM adventure_events WHERE session_id=? ORDER BY id", (session["id"],))
        durations = [next(s["duration_minutes"] for s in scenes if s["id"] == sid) for sid in session["scene_ids"]]
        session["budget"] = logic.time_budget(session["planned_minutes"], durations)
    return {"version": 1, "adventure": adventure, "scenes": scenes, "npcs": npcs, "clues": clues,
            "items": items, "connections": connections, "encounters": encounters, "sessions": sessions}


def initialize(database_path: Path) -> None:
    with closing(_db(database_path)) as db, db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS adventures (
          id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
          starting_situation TEXT NOT NULL DEFAULT '', main_objective TEXT NOT NULL DEFAULT '',
          suggested_level INTEGER, expected_players INTEGER, estimated_hours REAL,
          secrets TEXT NOT NULL DEFAULT '', outcomes TEXT NOT NULL DEFAULT '', gm_notes TEXT NOT NULL DEFAULT '',
          campaign_id INTEGER REFERENCES campaigns(id) ON DELETE SET NULL,
          party_id INTEGER REFERENCES parties(id) ON DELETE SET NULL,
          status TEXT NOT NULL DEFAULT 'active', current_scene_id INTEGER,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS adventure_scenes (
          id INTEGER PRIMARY KEY, adventure_id INTEGER NOT NULL REFERENCES adventures(id) ON DELETE CASCADE,
          position INTEGER NOT NULL, title TEXT NOT NULL, type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'not_started',
          location TEXT NOT NULL DEFAULT '', purpose TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
          complications TEXT NOT NULL DEFAULT '', duration_minutes INTEGER NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '',
          completed_session_id INTEGER REFERENCES adventure_sessions(id) ON DELETE SET NULL);
        CREATE TABLE IF NOT EXISTS adventure_npcs (
          id INTEGER PRIMARY KEY, adventure_id INTEGER NOT NULL REFERENCES adventures(id) ON DELETE CASCADE,
          name TEXT NOT NULL, role TEXT NOT NULL DEFAULT '', personality TEXT NOT NULL DEFAULT '',
          motivation TEXT NOT NULL DEFAULT '', knows TEXT NOT NULL DEFAULT '', wants TEXT NOT NULL DEFAULT '',
          secret TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', external_url TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS adventure_clues (
          id INTEGER PRIMARY KEY, adventure_id INTEGER NOT NULL REFERENCES adventures(id) ON DELETE CASCADE,
          name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '',
          reveals TEXT NOT NULL DEFAULT '', alternatives TEXT NOT NULL DEFAULT '', discovered INTEGER NOT NULL DEFAULT 0,
          discovered_scene_id INTEGER REFERENCES adventure_scenes(id) ON DELETE SET NULL,
          discovered_session_id INTEGER REFERENCES adventure_sessions(id) ON DELETE SET NULL, notes TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS adventure_items (
          id INTEGER PRIMARY KEY, adventure_id INTEGER NOT NULL REFERENCES adventures(id) ON DELETE CASCADE,
          name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'item', description TEXT NOT NULL DEFAULT '',
          starting_location TEXT NOT NULL DEFAULT '', current_location TEXT NOT NULL DEFAULT '',
          required INTEGER NOT NULL DEFAULT 0, obtained INTEGER NOT NULL DEFAULT 0,
          obtained_session_id INTEGER REFERENCES adventure_sessions(id) ON DELETE SET NULL,
          notes TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS adventure_scene_npcs (
          scene_id INTEGER NOT NULL REFERENCES adventure_scenes(id) ON DELETE CASCADE,
          npc_id INTEGER NOT NULL REFERENCES adventure_npcs(id) ON DELETE CASCADE, PRIMARY KEY(scene_id,npc_id));
        CREATE TABLE IF NOT EXISTS adventure_scene_clues (
          scene_id INTEGER NOT NULL REFERENCES adventure_scenes(id) ON DELETE CASCADE,
          clue_id INTEGER NOT NULL REFERENCES adventure_clues(id) ON DELETE CASCADE, PRIMARY KEY(scene_id,clue_id));
        CREATE TABLE IF NOT EXISTS adventure_scene_items (
          scene_id INTEGER NOT NULL REFERENCES adventure_scenes(id) ON DELETE CASCADE,
          item_id INTEGER NOT NULL REFERENCES adventure_items(id) ON DELETE CASCADE, PRIMARY KEY(scene_id,item_id));
        CREATE TABLE IF NOT EXISTS adventure_connections (
          id INTEGER PRIMARY KEY, from_scene_id INTEGER NOT NULL REFERENCES adventure_scenes(id) ON DELETE CASCADE,
          to_scene_id INTEGER NOT NULL REFERENCES adventure_scenes(id) ON DELETE CASCADE, kind TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS adventure_scene_encounters (
          id INTEGER PRIMARY KEY, scene_id INTEGER NOT NULL REFERENCES adventure_scenes(id) ON DELETE CASCADE,
          encounter_id INTEGER NOT NULL, completed INTEGER NOT NULL DEFAULT 0,
          completed_session_id INTEGER REFERENCES adventure_sessions(id) ON DELETE SET NULL,
          UNIQUE(scene_id,encounter_id));
        CREATE TABLE IF NOT EXISTS adventure_sessions (
          id INTEGER PRIMARY KEY, adventure_id INTEGER NOT NULL REFERENCES adventures(id) ON DELETE CASCADE,
          title TEXT NOT NULL, number INTEGER, planned_minutes INTEGER NOT NULL DEFAULT 0,
          objectives TEXT NOT NULL DEFAULT '', prep_notes TEXT NOT NULL DEFAULT '', actual_notes TEXT NOT NULL DEFAULT '',
          next_session_notes TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'planned', summary_markdown TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS adventure_session_scenes (
          session_id INTEGER NOT NULL REFERENCES adventure_sessions(id) ON DELETE CASCADE,
          scene_id INTEGER NOT NULL REFERENCES adventure_scenes(id) ON DELETE CASCADE,
          position INTEGER NOT NULL, PRIMARY KEY(session_id,scene_id));
        CREATE TABLE IF NOT EXISTS adventure_events (
          id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES adventure_sessions(id) ON DELETE CASCADE,
          scene_id INTEGER REFERENCES adventure_scenes(id) ON DELETE SET NULL,
          text TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'note', game_time TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        """)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(adventure_sessions)")}
        if "next_session_notes" not in columns:
            db.execute("ALTER TABLE adventure_sessions ADD COLUMN next_session_notes TEXT NOT NULL DEFAULT ''")


def register(app: FastAPI, database_path: Path) -> None:
    base = "/api/adventure-planner"

    @app.get("/tools/adventure-planner", response_class=HTMLResponse)
    def page():
        body = '<link rel="stylesheet" href="/tools/adventure-planner/style.css"><div id="planner"><h1>Adventure Planner</h1><p>Organize adventure preparation and session notes.</p><div id="app"></div></div><script src="/tools/adventure-planner/app.js" defer></script>'
        return layout("Adventure Planner", body)

    @app.get("/tools/adventure-planner/style.css")
    def css(): return FileResponse(FOLDER / "style.css", media_type="text/css")

    @app.get("/tools/adventure-planner/app.js")
    def js(): return FileResponse(FOLDER / "app.js", media_type="text/javascript")

    @app.get(base + "/options")
    def options():
        with closing(_db(database_path)) as db:
            return {"campaigns": _rows(db, "SELECT id,name FROM campaigns ORDER BY name"),
                    "parties": _rows(db, "SELECT id,campaign_id,name FROM parties ORDER BY name"),
                    "encounters": _rows(db, "SELECT id,name FROM encounters ORDER BY name")}

    @app.get(base + "/adventures")
    def list_adventures():
        with closing(_db(database_path)) as db:
            return _rows(db, "SELECT id,title,status,campaign_id,party_id,current_scene_id FROM adventures ORDER BY updated_at DESC,id DESC")

    @app.post(base + "/adventures", status_code=201)
    def create_adventure(values: AdventureInput):
        with closing(_db(database_path)) as db, db:
            data = values.model_dump()
            _validate_party(db, data["campaign_id"], data["party_id"])
            aid = _insert(db, "adventures", data)
            return _snapshot(db, aid)

    @app.get(base + "/adventures/{adventure_id}")
    def get_adventure(adventure_id: int):
        with closing(_db(database_path)) as db:
            return _snapshot(db, adventure_id)

    @app.patch(base + "/adventures/{adventure_id}")
    def edit_adventure(adventure_id: int, values: AdventureInput):
        with closing(_db(database_path)) as db, db:
            _adventure(db, adventure_id)
            data = values.model_dump()
            _validate_party(db, data["campaign_id"], data["party_id"])
            _update(db, "adventures", adventure_id, data)
            db.execute("UPDATE adventures SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (adventure_id,))
            return _snapshot(db, adventure_id)

    @app.post(base + "/adventures/{adventure_id}/archive")
    def archive(adventure_id: int):
        with closing(_db(database_path)) as db, db:
            row = _adventure(db, adventure_id)
            status = "active" if row["status"] == "archived" else "archived"
            db.execute("UPDATE adventures SET status=? WHERE id=?", (status, adventure_id))
            return {"status": status}

    @app.delete(base + "/adventures/{adventure_id}", status_code=204)
    def delete_adventure(adventure_id: int):
        with closing(_db(database_path)) as db, db:
            _adventure(db, adventure_id)
            db.execute("DELETE FROM adventures WHERE id=?", (adventure_id,))

    @app.post(base + "/adventures/{adventure_id}/scenes", status_code=201)
    def create_scene(adventure_id: int, values: SceneInput):
        with closing(_db(database_path)) as db, db:
            _adventure(db, adventure_id)
            data = values.model_dump()
            if data["type"] not in SCENE_TYPES or data["status"] not in SCENE_STATUSES:
                raise HTTPException(422, "Invalid scene type or status")
            _session_id(db, adventure_id, data["completed_session_id"])
            position = db.execute("SELECT COALESCE(MAX(position),0)+1 FROM adventure_scenes WHERE adventure_id=?", (adventure_id,)).fetchone()[0]
            sid = _insert(db, "adventure_scenes", {"adventure_id": adventure_id, "position": position, **data})
            return _belongs(db, "adventure_scenes", sid, adventure_id)

    @app.patch(base + "/adventures/{adventure_id}/scenes/{scene_id}")
    def edit_scene(adventure_id: int, scene_id: int, values: SceneInput):
        with closing(_db(database_path)) as db, db:
            _belongs(db, "adventure_scenes", scene_id, adventure_id)
            data = values.model_dump()
            if data["type"] not in SCENE_TYPES or data["status"] not in SCENE_STATUSES:
                raise HTTPException(422, "Invalid scene type or status")
            _session_id(db, adventure_id, data["completed_session_id"])
            _update(db, "adventure_scenes", scene_id, data)
            return _belongs(db, "adventure_scenes", scene_id, adventure_id)

    @app.delete(base + "/adventures/{adventure_id}/scenes/{scene_id}", status_code=204)
    def delete_scene(adventure_id: int, scene_id: int):
        with closing(_db(database_path)) as db, db:
            _belongs(db, "adventure_scenes", scene_id, adventure_id)
            db.execute("UPDATE adventures SET current_scene_id=NULL WHERE id=? AND current_scene_id=?", (adventure_id, scene_id))
            db.execute("UPDATE adventure_clues SET discovered_scene_id=NULL WHERE discovered_scene_id=?", (scene_id,))
            db.execute("DELETE FROM adventure_scenes WHERE id=?", (scene_id,))

    @app.post(base + "/adventures/{adventure_id}/scenes/{scene_id}/duplicate", status_code=201)
    def duplicate_scene(adventure_id: int, scene_id: int):
        with closing(_db(database_path)) as db, db:
            row = _belongs(db, "adventure_scenes", scene_id, adventure_id)
            data = {k: v for k, v in row.items() if k not in {"id", "position", "adventure_id"}}
            data["title"] += " (copy)"
            data["status"] = "not_started"
            data["completed_session_id"] = None
            pos = db.execute("SELECT COALESCE(MAX(position),0)+1 FROM adventure_scenes WHERE adventure_id=?", (adventure_id,)).fetchone()[0]
            new_id = _insert(db, "adventure_scenes", {"adventure_id": adventure_id, "position": pos, **data})
            for entity in ENTITY_TABLES:
                table = ENTITY_LINKS[entity]
                key = ENTITY_KEYS[entity]
                db.execute(f"INSERT INTO {table}(scene_id,{key}) SELECT ?,{key} FROM {table} WHERE scene_id=?", (new_id, scene_id))
            return _belongs(db, "adventure_scenes", new_id, adventure_id)

    @app.post(base + "/adventures/{adventure_id}/scenes/reorder")
    def reorder(adventure_id: int, values: ReorderInput):
        with closing(_db(database_path)) as db, db:
            existing = [r["id"] for r in _rows(db, "SELECT id FROM adventure_scenes WHERE adventure_id=?", (adventure_id,))]
            if len(values.scene_ids) != len(existing) or set(values.scene_ids) != set(existing):
                raise HTTPException(422, "Supply every scene exactly once")
            for position, scene_id in enumerate(values.scene_ids, 1):
                db.execute("UPDATE adventure_scenes SET position=? WHERE id=?", (position, scene_id))
            return _snapshot(db, adventure_id)["scenes"]

    @app.post(base + "/adventures/{adventure_id}/scenes/{scene_id}/select")
    def select_scene(adventure_id: int, scene_id: int):
        with closing(_db(database_path)) as db, db:
            scene = _belongs(db, "adventure_scenes", scene_id, adventure_id)
            db.execute("UPDATE adventures SET current_scene_id=? WHERE id=?", (scene_id, adventure_id))
            if scene["status"] == "not_started":
                db.execute("UPDATE adventure_scenes SET status='active' WHERE id=?", (scene_id,))
            return _snapshot(db, adventure_id)

    @app.post(base + "/adventures/{adventure_id}/connections", status_code=201)
    def add_connection(adventure_id: int, values: ConnectionInput):
        with closing(_db(database_path)) as db, db:
            _scene_ids(db, adventure_id, [values.from_scene_id, values.to_scene_id])
            if values.kind not in CONNECTION_TYPES or values.from_scene_id == values.to_scene_id:
                raise HTTPException(422, "Invalid connection")
            cid = _insert(db, "adventure_connections", values.model_dump())
            return _one(db, "SELECT * FROM adventure_connections WHERE id=?", (cid,))

    @app.delete(base + "/adventures/{adventure_id}/connections/{connection_id}", status_code=204)
    def delete_connection(adventure_id: int, connection_id: int):
        with closing(_db(database_path)) as db, db:
            _one(db, "SELECT c.id FROM adventure_connections c JOIN adventure_scenes s ON s.id=c.from_scene_id WHERE c.id=? AND s.adventure_id=?", (connection_id, adventure_id))
            db.execute("DELETE FROM adventure_connections WHERE id=?", (connection_id,))

    def save_entity(db, adventure_id, entity, values, record_id=None):
        _adventure(db, adventure_id)
        data = values.model_dump()
        scene_ids = data.pop("scene_ids")
        _scene_ids(db, adventure_id, scene_ids)
        if entity == "clues":
            discovered_scene_id = data["discovered_scene_id"]
            if discovered_scene_id is not None:
                _belongs(db, "adventure_scenes", discovered_scene_id, adventure_id)
                data["discovered"] = True
            data["discovered"] = int(data["discovered"])
            _session_id(db, adventure_id, data["discovered_session_id"])
        if entity == "items":
            if data["kind"] not in {"item", "objective"}:
                raise HTTPException(422, "Invalid item kind")
            data["required"] = int(data["required"])
            data["obtained"] = int(data["obtained"])
            _session_id(db, adventure_id, data["obtained_session_id"])
        table, links, key = ENTITY_TABLES[entity], ENTITY_LINKS[entity], ENTITY_KEYS[entity]
        if record_id is None:
            record_id = _insert(db, table, {"adventure_id": adventure_id, **data})
        else:
            _belongs(db, table, record_id, adventure_id)
            _update(db, table, record_id, data)
            db.execute(f"DELETE FROM {links} WHERE {key}=?", (record_id,))
        for scene_id in scene_ids:
            db.execute(f"INSERT INTO {links}(scene_id,{key}) VALUES (?,?)", (scene_id, record_id))
        return next(row for row in _entity_rows(db, adventure_id, entity) if row["id"] == record_id)

    for entity, model in (("npcs", NPCInput), ("clues", ClueInput), ("items", ItemInput)):
        def make_routes(entity=entity, model=model):
            async def create(adventure_id: int, values: model):
                with closing(_db(database_path)) as db, db:
                    return save_entity(db, adventure_id, entity, values)
            async def edit(adventure_id: int, record_id: int, values: model):
                with closing(_db(database_path)) as db, db:
                    return save_entity(db, adventure_id, entity, values, record_id)
            async def delete(adventure_id: int, record_id: int):
                with closing(_db(database_path)) as db, db:
                    _belongs(db, ENTITY_TABLES[entity], record_id, adventure_id)
                    db.execute(f"DELETE FROM {ENTITY_TABLES[entity]} WHERE id=?", (record_id,))
            app.add_api_route(base + f"/adventures/{{adventure_id}}/{entity}", create, methods=["POST"], status_code=201)
            app.add_api_route(base + f"/adventures/{{adventure_id}}/{entity}/{{record_id}}", edit, methods=["PATCH"])
            app.add_api_route(base + f"/adventures/{{adventure_id}}/{entity}/{{record_id}}", delete, methods=["DELETE"], status_code=204)
        make_routes()

    @app.post(base + "/adventures/{adventure_id}/scenes/{scene_id}/encounters", status_code=201)
    def link_encounter(adventure_id: int, scene_id: int, values: EncounterLinkInput):
        with closing(_db(database_path)) as db, db:
            _belongs(db, "adventure_scenes", scene_id, adventure_id)
            if _encounter(db, values.encounter_id)["missing"]:
                raise HTTPException(422, "Encounter does not exist")
            _session_id(db, adventure_id, values.completed_session_id)
            try:
                lid = _insert(db, "adventure_scene_encounters", {"scene_id": scene_id, **values.model_dump()})
            except sqlite3.IntegrityError:
                raise HTTPException(409, "Encounter already linked") from None
            return next(r for r in _snapshot(db, adventure_id)["encounters"] if r["id"] == lid)

    @app.patch(base + "/adventures/{adventure_id}/scenes/{scene_id}/encounters/{link_id}")
    def edit_encounter_link(adventure_id: int, scene_id: int, link_id: int, values: EncounterLinkInput):
        with closing(_db(database_path)) as db, db:
            _belongs(db, "adventure_scenes", scene_id, adventure_id)
            _one(db, "SELECT * FROM adventure_scene_encounters WHERE id=? AND scene_id=?", (link_id, scene_id))
            if _encounter(db, values.encounter_id)["missing"]:
                raise HTTPException(422, "Encounter does not exist")
            _session_id(db, adventure_id, values.completed_session_id)
            _update(db, "adventure_scene_encounters", link_id, values.model_dump())
            return next(r for r in _snapshot(db, adventure_id)["encounters"] if r["id"] == link_id)

    @app.delete(base + "/adventures/{adventure_id}/scenes/{scene_id}/encounters/{link_id}", status_code=204)
    def unlink_encounter(adventure_id: int, scene_id: int, link_id: int):
        with closing(_db(database_path)) as db, db:
            _belongs(db, "adventure_scenes", scene_id, adventure_id)
            _one(db, "SELECT id FROM adventure_scene_encounters WHERE id=? AND scene_id=?", (link_id, scene_id))
            db.execute("DELETE FROM adventure_scene_encounters WHERE id=?", (link_id,))

    def save_session(db, adventure_id, values, session_id=None):
        _adventure(db, adventure_id)
        data = values.model_dump()
        scene_ids = data.pop("scene_ids")
        _scene_ids(db, adventure_id, scene_ids)
        if data["status"] not in SESSION_STATUSES:
            raise HTTPException(422, "Invalid session status")
        if session_id is None:
            session_id = _insert(db, "adventure_sessions", {"adventure_id": adventure_id, **data})
        else:
            _belongs(db, "adventure_sessions", session_id, adventure_id)
            _update(db, "adventure_sessions", session_id, data)
            db.execute("DELETE FROM adventure_session_scenes WHERE session_id=?", (session_id,))
        for pos, scene_id in enumerate(scene_ids, 1):
            db.execute("INSERT INTO adventure_session_scenes(session_id,scene_id,position) VALUES (?,?,?)", (session_id, scene_id, pos))
        return next(s for s in _snapshot(db, adventure_id)["sessions"] if s["id"] == session_id)

    @app.post(base + "/adventures/{adventure_id}/sessions", status_code=201)
    def create_session(adventure_id: int, values: SessionInput):
        with closing(_db(database_path)) as db, db:
            return save_session(db, adventure_id, values)

    @app.patch(base + "/adventures/{adventure_id}/sessions/{session_id}")
    def edit_session(adventure_id: int, session_id: int, values: SessionInput):
        with closing(_db(database_path)) as db, db:
            return save_session(db, adventure_id, values, session_id)

    @app.delete(base + "/adventures/{adventure_id}/sessions/{session_id}", status_code=204)
    def delete_session(adventure_id: int, session_id: int):
        with closing(_db(database_path)) as db, db:
            _belongs(db, "adventure_sessions", session_id, adventure_id)
            db.execute("DELETE FROM adventure_sessions WHERE id=?", (session_id,))

    @app.post(base + "/adventures/{adventure_id}/sessions/{session_id}/events", status_code=201)
    def add_event(adventure_id: int, session_id: int, values: EventInput):
        with closing(_db(database_path)) as db, db:
            _belongs(db, "adventure_sessions", session_id, adventure_id)
            if values.scene_id is not None:
                _belongs(db, "adventure_scenes", values.scene_id, adventure_id)
            if values.kind not in {"note", "decision", "npc", "unexpected", "objective", "encounter"}:
                raise HTTPException(422, "Invalid event type")
            eid = _insert(db, "adventure_events", {"session_id": session_id, **values.model_dump()})
            return _one(db, "SELECT * FROM adventure_events WHERE id=?", (eid,))

    @app.patch(base + "/adventures/{adventure_id}/sessions/{session_id}/events/{event_id}")
    def edit_event(adventure_id: int, session_id: int, event_id: int, values: EventInput):
        with closing(_db(database_path)) as db, db:
            _belongs(db, "adventure_sessions", session_id, adventure_id)
            _one(db, "SELECT id FROM adventure_events WHERE id=? AND session_id=?", (event_id, session_id))
            if values.scene_id is not None:
                _belongs(db, "adventure_scenes", values.scene_id, adventure_id)
            if values.kind not in {"note", "decision", "npc", "unexpected", "objective", "encounter"}:
                raise HTTPException(422, "Invalid event type")
            _update(db, "adventure_events", event_id, values.model_dump())
            return _one(db, "SELECT * FROM adventure_events WHERE id=?", (event_id,))

    @app.delete(base + "/adventures/{adventure_id}/sessions/{session_id}/events/{event_id}", status_code=204)
    def delete_event(adventure_id: int, session_id: int, event_id: int):
        with closing(_db(database_path)) as db, db:
            _belongs(db, "adventure_sessions", session_id, adventure_id)
            _one(db, "SELECT id FROM adventure_events WHERE id=? AND session_id=?", (event_id, session_id))
            db.execute("DELETE FROM adventure_events WHERE id=?", (event_id,))

    @app.get(base + "/adventures/{adventure_id}/sessions/{session_id}/recap")
    def get_recap(adventure_id: int, session_id: int):
        with closing(_db(database_path)) as db:
            snapshot = _snapshot(db, adventure_id)
            session = next((s for s in snapshot["sessions"] if s["id"] == session_id), None)
            if session is None:
                raise HTTPException(404, "Session not found")
            scenes = [s for s in snapshot["scenes"] if s["id"] in session["scene_ids"] and s["completed_session_id"] in (None, session_id)]
            clues = [c for c in snapshot["clues"] if c["discovered"] and (c["discovered_session_id"] == session_id or (c["discovered_session_id"] is None and c["discovered_scene_id"] in session["scene_ids"]))]
            items = [i for i in snapshot["items"] if (i["obtained_session_id"] == session_id or (i["obtained_session_id"] is None and (not i["scene_ids"] or set(i["scene_ids"]) & set(session["scene_ids"]))))]
            encounters = [e for e in snapshot["encounters"] if e["scene_id"] in session["scene_ids"] and e["completed_session_id"] in (None, session_id)]
            return {"generated": logic.recap(session, scenes, clues, items, session["events"], encounters),
                    "saved": session["summary_markdown"]}

    @app.get(base + "/adventures/{adventure_id}/sessions/{session_id}/recap.md", response_class=PlainTextResponse)
    def recap_markdown(adventure_id: int, session_id: int):
        data = get_recap(adventure_id, session_id)
        return data["saved"] or data["generated"]

    @app.get(base + "/adventures/{adventure_id}/export.json")
    def export_json(adventure_id: int):
        with closing(_db(database_path)) as db:
            return _snapshot(db, adventure_id)

    @app.get(base + "/adventures/{adventure_id}/export.md", response_class=PlainTextResponse)
    def export_markdown(adventure_id: int):
        with closing(_db(database_path)) as db:
            return logic.markdown(_snapshot(db, adventure_id))

    def import_snapshot(db, value):
        if value.version != 1:
            raise HTTPException(422, "Unsupported backup version")
        try:
            original = value.adventure
            adventure = AdventureInput.model_validate({k: original.get(k) for k in AdventureInput.model_fields if k in original})
            data = adventure.model_dump()
            # References are preserved where the local records still exist.
            if data["campaign_id"] and not db.execute("SELECT 1 FROM campaigns WHERE id=? AND name=?", (data["campaign_id"], original.get("campaign_name"))).fetchone():
                data["campaign_id"] = None
            if data["party_id"] and not db.execute("SELECT 1 FROM parties WHERE id=? AND name=?", (data["party_id"], original.get("party_name"))).fetchone():
                data["party_id"] = None
            _validate_party(db, data["campaign_id"], data["party_id"])
            aid = _insert(db, "adventures", data)
            if original.get("status") in {"active", "archived"}:
                db.execute("UPDATE adventures SET status=? WHERE id=?", (original["status"], aid))
            mapping = {}
            pending_scene_sessions = {}
            for raw in value.scenes:
                old = raw["id"]
                if old in mapping: raise ValueError("Duplicate scene ID")
                scene = SceneInput.model_validate({k: raw[k] for k in SceneInput.model_fields if k in raw})
                scene_data = scene.model_dump()
                scene_data["type"] = _import_scene_choice(scene.type, SCENE_TYPES, "type", old, scene.title)
                scene_data["status"] = _import_scene_choice(scene.status, SCENE_STATUSES, "status", old, scene.title)
                pending_scene_sessions[old] = scene_data.pop("completed_session_id")
                new = _insert(db, "adventure_scenes", {"adventure_id": aid, "position": len(mapping)+1, **scene_data})
                mapping[old] = new
            if original.get("current_scene_id") in mapping:
                db.execute("UPDATE adventures SET current_scene_id=? WHERE id=?", (mapping[original["current_scene_id"]], aid))
            entity_map = {}
            pending_entity_sessions = []
            for entity, model in (("npcs", NPCInput), ("clues", ClueInput), ("items", ItemInput)):
                emap = {}
                for raw in getattr(value, entity):
                    old = raw["id"]
                    if old in emap: raise ValueError("Duplicate record ID")
                    payload = {k: raw[k] for k in model.model_fields if k in raw}
                    payload["scene_ids"] = [mapping[s] for s in raw.get("scene_ids", [])]
                    if entity == "clues" and payload.get("discovered_scene_id") is not None:
                        payload["discovered_scene_id"] = mapping[payload["discovered_scene_id"]]
                    session_field = {"clues": "discovered_session_id", "items": "obtained_session_id"}.get(entity)
                    if session_field:
                        old_session = payload.get(session_field)
                        payload[session_field] = None
                    result = save_entity(db, aid, entity, model.model_validate(payload))
                    emap[old] = result["id"]
                    if session_field and old_session is not None:
                        pending_entity_sessions.append((entity, result["id"], session_field, old_session))
                entity_map[entity] = emap
            for raw in value.connections:
                source, target = mapping[raw["from_scene_id"]], mapping[raw["to_scene_id"]]
                if source == target or raw["kind"] not in CONNECTION_TYPES: raise ValueError("Invalid connection")
                _insert(db, "adventure_connections", {"from_scene_id": source, "to_scene_id": target, "kind": raw["kind"]})
            pending_encounter_sessions = []
            for raw in value.encounters:
                link_id = _insert(db, "adventure_scene_encounters", {"scene_id": mapping[raw["scene_id"]],
                        "encounter_id": int(raw["encounter_id"]), "completed": int(bool(raw.get("completed", False)))})
                if raw.get("completed_session_id") is not None:
                    pending_encounter_sessions.append((link_id, raw["completed_session_id"]))
            session_mapping = {}
            for raw in value.sessions:
                if len(raw.get("events", [])) > 5000:
                    raise ValueError("Too many session events")
                payload = {k: raw[k] for k in SessionInput.model_fields if k in raw}
                payload["scene_ids"] = [mapping[s] for s in raw.get("scene_ids", [])]
                session = save_session(db, aid, SessionInput.model_validate(payload))
                session_mapping[raw["id"]] = session["id"]
                for event in raw.get("events", []):
                    e = EventInput.model_validate({k: event[k] for k in EventInput.model_fields if k in event})
                    edata = e.model_dump()
                    if edata["scene_id"] is not None:
                        edata["scene_id"] = mapping[edata["scene_id"]]
                    _insert(db, "adventure_events", {"session_id": session["id"], **edata})
            for old_scene, old_session in pending_scene_sessions.items():
                if old_session is not None:
                    db.execute("UPDATE adventure_scenes SET completed_session_id=? WHERE id=?", (session_mapping[old_session], mapping[old_scene]))
            for entity, record_id, field, old_session in pending_entity_sessions:
                db.execute(f"UPDATE {ENTITY_TABLES[entity]} SET {field}=? WHERE id=?", (session_mapping[old_session], record_id))
            for link_id, old_session in pending_encounter_sessions:
                db.execute("UPDATE adventure_scene_encounters SET completed_session_id=? WHERE id=?", (session_mapping[old_session], link_id))
            return aid
        except (KeyError, ValueError, TypeError, sqlite3.IntegrityError, ValidationError) as exc:
            raise HTTPException(422, f"Malformed adventure backup: {exc}") from None

    @app.post(base + "/import", status_code=201)
    def import_json(value: ImportInput):
        with closing(_db(database_path)) as db, db:
            aid = import_snapshot(db, value)
            return _snapshot(db, aid)

    @app.post(base + "/adventures/{adventure_id}/duplicate", status_code=201)
    def duplicate(adventure_id: int):
        with closing(_db(database_path)) as db, db:
            raw = _snapshot(db, adventure_id)
            raw["adventure"]["title"] += " (copy)"
            raw["adventure"]["status"] = "active"
            aid = import_snapshot(db, ImportInput.model_validate(raw))
            return _snapshot(db, aid)
