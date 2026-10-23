"""Local Monster Library, JSON import/export, and session collections."""

from contextlib import closing
from html import escape
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field, ValidationError

from master.pages import layout
from shared.database.storage import connect


FOLDER = Path(__file__).resolve().parent
spec = spec_from_file_location("pf2e_monster_model", FOLDER / "model.py")
model = module_from_spec(spec)
spec.loader.exec_module(model)


class CollectionInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class CollectionMonsterInput(BaseModel):
    monster_id: int = Field(gt=0)


def initialize(database_path: Path) -> None:
    with closing(connect(database_path)) as db, db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS monsters (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                level INTEGER NOT NULL,
                max_hp INTEGER NOT NULL,
                data_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS monster_collections (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS monster_collection_members (
                collection_id INTEGER NOT NULL REFERENCES monster_collections(id) ON DELETE CASCADE,
                monster_id INTEGER NOT NULL REFERENCES monsters(id) ON DELETE CASCADE,
                PRIMARY KEY(collection_id,monster_id)
            );
        """)


def lookup(db, monster_id: int) -> dict | None:
    row = db.execute("SELECT data_json FROM monsters WHERE id=?", (monster_id,)).fetchone()
    return model.Monster.model_validate(json.loads(row[0])).model_dump() if row else None


def _view(db, monster_id: int) -> dict:
    value = lookup(db, monster_id)
    if value is None:
        raise HTTPException(404, "Monster not found")
    return {"id": monster_id, **value, "completeness": model.completeness(value)}


def _insert(db, value: model.Monster) -> int:
    data = value.model_dump()
    cursor = db.execute("INSERT INTO monsters(name,level,max_hp,data_json) VALUES (?,?,?,?)",
                        (data["name"], data["level"], data["max_hp"], json.dumps(data)))
    return cursor.lastrowid


def page() -> str:
    body = """<link rel="stylesheet" href="/tools/monster-reference/style.css">
    <nav><a class="back-link" href="/">← All tools</a></nav><h1>Monster Reference</h1>
    <p>Find and organize monster information for sessions.</p><p>Keep your own Monster Library locally. Missing statistics stay unknown; completeness labels are toolkit guidance only.</p>
    <section class="monster-card"><h2>Quick Add</h2><form id="quick-add" class="monster-grid">
      <label>Name<input name="name" required maxlength="120"></label><label>Level<input name="level" type="number" min="-1" max="25" required></label>
      <label>Maximum HP<input name="max_hp" type="number" min="1" required></label><button>Create monster</button></form>
      <p id="quick-message" role="status"></p></section>
    <section class="monster-card"><h2>Monster Library</h2><div class="monster-grid">
      <label>Search<input id="monster-search" type="search" placeholder="Name or trait"></label>
      <label>Completeness<select id="completeness-filter"><option value="">All</option><option>Basic</option><option>Combat Ready</option><option>Detailed</option></select></label></div>
      <div id="monster-list"></div></section>
    <section id="monster-details" class="monster-card" hidden><h2>Monster Details</h2><div id="detail-header"></div>
      <p id="missing-fields"></p><div class="monster-actions"><button id="quick-edit" type="button">Quick Edit</button><button id="detailed-edit" type="button">Detailed Editor</button>
      <button id="duplicate-monster" type="button">Duplicate Monster</button><button id="export-monster" type="button">Export JSON</button><button id="delete-monster" type="button" class="danger">Delete</button></div>
      <div id="monster-editor"></div><div id="monster-summary"></div></section>
    <section class="monster-card"><h2>JSON import</h2><p>Import a single monster or a version 1 monster backup. The minimum is name, level, and max_hp.</p>
      <input id="monster-import" type="file" accept="application/json,.json"><p id="import-message" role="status"></p></section>
    <section class="monster-card"><h2>Session Monster Collections</h2><form id="collection-add" class="monster-grid"><label>Collection name<input name="name" required maxlength="120" placeholder="Session 4"></label><button>Create collection</button></form>
      <div id="collection-list"></div></section>
    <script src="/tools/monster-reference/app.js" defer></script>"""
    return layout("Monster Library", body)


def detail_page(monster: dict, *, back_href: str, back_label: str, context: str = "", library_href: str = "", combat_notes: str = "") -> str:
    """Render a read-only monster record; combat may pass its saved stat snapshot."""
    def shown(value) -> str:
        return "—" if value is None or value == "" else escape(str(value))

    def line(label: str, value) -> str:
        return f"<div><dt>{escape(label)}</dt><dd>{shown(value)}</dd></div>"

    def section(title: str, content: str) -> str:
        return f'<section class="monster-card monster-detail-section"><h2>{escape(title)}</h2>{content}</section>'

    def terms(values: list) -> str:
        return ", ".join(str(value) for value in values) if values else ""

    def entries(values: list[dict], kind: str) -> str:
        if not values:
            return '<p class="monster-empty">Not entered</p>'
        blocks = []
        for item in values:
            if kind == "attacks":
                rows = [("Type", item.get("type")), ("Actions", item.get("actions")),
                        ("Bonus", item.get("bonus")), ("Traits", terms(item.get("traits") or [])),
                        ("Damage", item.get("damage")), ("Effect", item.get("effect"))]
            elif kind == "abilities":
                rows = [("Actions", item.get("actions")), ("Traits", terms(item.get("traits") or [])),
                        ("Trigger", item.get("trigger")), ("Requirements", item.get("requirements")),
                        ("DC", item.get("dc")), ("Description", item.get("description"))]
            else:
                rows = [("Description", item.get("description")), ("Modifier", item.get("modifier")),
                        ("Damage", item.get("damage")), ("Offensive", "Yes" if item.get("offensive") else "No")]
            blocks.append(f'<article class="monster-detail-entry"><h3>{shown(item.get("name"))}</h3>'
                          f'<dl class="monster-detail-grid">{"".join(line(label, value) for label, value in rows)}</dl></article>')
        return "".join(blocks)

    overview = '<dl class="monster-detail-grid">' + "".join(line(label, monster.get(key)) for label, key in (
        ("Level", "level"), ("Maximum HP", "max_hp"), ("AC", "ac"), ("Fortitude", "fortitude"),
        ("Reflex", "reflex"), ("Will", "will"), ("Perception", "perception"))) + '</dl>'
    traits = '<dl class="monster-detail-grid">' + line("Traits", terms(monster.get("traits") or [])) + line("Senses", terms(monster.get("senses") or [])) + '</dl>'
    skills = monster.get("skills") or {}
    traits += '<h3>Skills</h3>' + ('<dl class="monster-detail-grid">' + "".join(line(name, bonus) for name, bonus in skills.items()) + '</dl>' if skills else '<p class="monster-empty">Not entered</p>')
    speeds = monster.get("speeds") or []
    movement = '<dl class="monster-detail-grid">' + "".join(line(speed.get("type", "Speed"), f'{speed.get("feet")} feet' if speed.get("feet") is not None else None) for speed in speeds) + '</dl>' if speeds else '<p class="monster-empty">Not entered</p>'
    source_url = monster.get("source_url") or ""
    source_link = f'<a href="{escape(source_url, quote=True)}" target="_blank" rel="noopener noreferrer">Open source</a>' if source_url.startswith(("https://", "http://")) else "—"
    source = '<dl class="monster-detail-grid">' + line("Book", monster.get("source_book")) + line("Page", monster.get("source_page")) + f'<div><dt>URL</dt><dd>{source_link}</dd></div>' + '</dl>'
    source += f'<h3>Notes</h3><p class="monster-detail-notes">{shown(monster.get("notes"))}</p>'
    if combat_notes:
        source += f'<h3>Combat notes</h3><p class="monster-detail-notes">{shown(combat_notes)}</p>'
    context_html = f'<p class="monster-detail-context">{escape(context)}</p>' if context else ""
    library_html = f'<p><a href="{escape(library_href, quote=True)}">Open current Monster Library record</a></p>' if library_href else ""
    body = (f'<link rel="stylesheet" href="/tools/monster-reference/style.css">'
            f'<nav><a class="back-link" href="{escape(back_href, quote=True)}">← {escape(back_label)}</a></nav>'
            f'<header class="monster-detail-heading"><h1>{shown(monster.get("name"))}</h1><p>Read-only monster details</p></header>'
            f'{context_html}{library_html}'
            f'{section("Core statistics", overview)}{section("Traits, senses, and skills", traits)}'
            f'{section("Movement", movement)}{section("Attacks", entries(monster.get("attacks") or [], "attacks"))}'
            f'{section("Special abilities", entries(monster.get("abilities") or [], "abilities"))}'
            f'{section("Spellcasting", entries(monster.get("spellcasting") or [], "spellcasting"))}'
            f'{section("Source and GM notes", source)}')
    return layout(str(monster.get("name") or "Monster details"), body)


def register(app: FastAPI, database_path: Path) -> None:
    app.state.monster_lookup = lookup  # Read-only integration for Encounter Builder and Combat Tracker.
    app.state.monster_detail_page = detail_page  # Read-only rendering of combat snapshots.
    base = "/api/monster-reference"

    @app.get("/tools/monster-reference", response_class=HTMLResponse)
    def monster_page(): return page()

    @app.get("/tools/monster-reference/monsters/{monster_id}", response_class=HTMLResponse)
    def monster_detail(monster_id: int):
        with closing(connect(database_path)) as db:
            monster = lookup(db, monster_id)
        if monster is None:
            raise HTTPException(404, "Monster not found")
        return detail_page(monster, back_href="/tools/monster-reference", back_label="Monster Library")

    @app.get("/tools/monster-reference/app.js")
    def js(): return FileResponse(FOLDER / "app.js", media_type="text/javascript")

    @app.get("/tools/monster-reference/style.css")
    def css(): return FileResponse(FOLDER / "style.css", media_type="text/css")

    @app.get(base + "/monsters")
    def list_monsters(completeness: str | None = None, q: str = ""):
        if completeness not in (None, "Basic", "Combat Ready", "Detailed"):
            raise HTTPException(422, "Invalid completeness filter")
        with closing(connect(database_path)) as db:
            ids = [row[0] for row in db.execute("SELECT id FROM monsters ORDER BY name COLLATE NOCASE,id")]
            results = [_view(db, ident) for ident in ids]
        if q:
            query = q.casefold()
            results = [row for row in results if query in row["name"].casefold() or any(query in trait.casefold() for trait in row["traits"])]
        return [row for row in results if completeness is None or row["completeness"]["level"] == completeness]

    @app.post(base + "/monsters", status_code=201)
    def create_monster(value: model.Monster):
        with closing(connect(database_path)) as db, db:
            return _view(db, _insert(db, value))

    @app.get(base + "/monsters/{monster_id}")
    def get_monster(monster_id: int):
        with closing(connect(database_path)) as db:
            return _view(db, monster_id)

    @app.put(base + "/monsters/{monster_id}")
    def edit_monster(monster_id: int, value: model.Monster):
        data = value.model_dump()
        with closing(connect(database_path)) as db, db:
            if lookup(db, monster_id) is None:
                raise HTTPException(404, "Monster not found")
            db.execute("UPDATE monsters SET name=?,level=?,max_hp=?,data_json=? WHERE id=?",
                       (data["name"], data["level"], data["max_hp"], json.dumps(data), monster_id))
            return _view(db, monster_id)

    @app.delete(base + "/monsters/{monster_id}", status_code=204)
    def delete_monster(monster_id: int):
        with closing(connect(database_path)) as db, db:
            if db.execute("DELETE FROM monsters WHERE id=?", (monster_id,)).rowcount == 0:
                raise HTTPException(404, "Monster not found")

    @app.post(base + "/monsters/{monster_id}/duplicate", status_code=201)
    def duplicate_monster(monster_id: int):
        with closing(connect(database_path)) as db, db:
            value = lookup(db, monster_id)
            if value is None:
                raise HTTPException(404, "Monster not found")
            value["name"] += " (copy)"
            return _view(db, _insert(db, model.Monster.model_validate(value)))

    @app.get(base + "/monsters/{monster_id}/export")
    def export_monster(monster_id: int):
        with closing(connect(database_path)) as db:
            value = lookup(db, monster_id)
        if value is None:
            raise HTTPException(404, "Monster not found")
        return {"schema_version": 1, **value}

    @app.post(base + "/import", status_code=201)
    def import_monsters(raw: object = Body(...)):
        try:
            if isinstance(raw, dict) and "monsters" in raw and raw.get("schema_version", 1) != 1:
                raise ValueError("Unsupported monster schema version")
            values = raw.get("monsters") if isinstance(raw, dict) and "monsters" in raw else [raw]
            if not isinstance(values, list) or len(values) > 1000:
                raise ValueError("Expected at most 1000 monsters")
            parsed = [model.Monster.model_validate(model.normalize_import(value)) for value in values]
        except (ValueError, TypeError, ValidationError) as error:
            raise HTTPException(422, f"Invalid monster import: {error}") from None
        with closing(connect(database_path)) as db, db:
            return [_view(db, _insert(db, value)) for value in parsed]

    @app.get(base + "/collections")
    def list_collections():
        with closing(connect(database_path)) as db:
            rows = db.execute("SELECT id,name FROM monster_collections ORDER BY id DESC").fetchall()
            return [{"id": ident, "name": name, "monsters": [_view(db, row[0]) for row in db.execute(
                "SELECT monster_id FROM monster_collection_members WHERE collection_id=? ORDER BY monster_id", (ident,))]} for ident, name in rows]

    @app.post(base + "/collections", status_code=201)
    def create_collection(value: CollectionInput):
        with closing(connect(database_path)) as db, db:
            cursor = db.execute("INSERT INTO monster_collections(name) VALUES (?)", (value.name.strip(),))
            return {"id": cursor.lastrowid, "name": value.name.strip(), "monsters": []}

    @app.post(base + "/collections/{collection_id}/monsters", status_code=201)
    def add_to_collection(collection_id: int, value: CollectionMonsterInput):
        with closing(connect(database_path)) as db, db:
            if db.execute("SELECT 1 FROM monster_collections WHERE id=?", (collection_id,)).fetchone() is None:
                raise HTTPException(404, "Collection not found")
            if lookup(db, value.monster_id) is None:
                raise HTTPException(404, "Monster not found")
            db.execute("INSERT OR IGNORE INTO monster_collection_members(collection_id,monster_id) VALUES (?,?)", (collection_id, value.monster_id))
            return {"collection_id": collection_id, "monster_id": value.monster_id}

    @app.delete(base + "/collections/{collection_id}/monsters/{monster_id}", status_code=204)
    def remove_from_collection(collection_id: int, monster_id: int):
        with closing(connect(database_path)) as db, db:
            if db.execute("DELETE FROM monster_collection_members WHERE collection_id=? AND monster_id=?", (collection_id, monster_id)).rowcount == 0:
                raise HTTPException(404, "Collection monster not found")

    @app.delete(base + "/collections/{collection_id}", status_code=204)
    def delete_collection(collection_id: int):
        with closing(connect(database_path)) as db, db:
            if db.execute("DELETE FROM monster_collections WHERE id=?", (collection_id,)).rowcount == 0:
                raise HTTPException(404, "Collection not found")
