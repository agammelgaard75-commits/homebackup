"""Local Rules Quick Reference routes and SQLite repository.

The master loads this module by convention from the tool's folder. Official
examples are seeded once; user entries remain separate and editable.
"""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field, field_validator

from master.pages import layout
from shared.database.storage import connect


FOLDER = Path(__file__).resolve().parent
CATEGORIES = (
    "Combat", "Actions", "Conditions", "Skills", "Healing and Death",
    "Exploration", "General GM Rules",
)
Category = Literal[
    "Combat", "Actions", "Conditions", "Skills", "Healing and Death",
    "Exploration", "General GM Rules",
]
Kind = Literal["note", "house_rule"]


class UserEntry(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: Category
    summary: str = Field(min_length=1, max_length=600)
    reminders: str = Field(default="", max_length=600)
    kind: Kind
    source_book: str = Field(default="", max_length=120)
    source_page: int | None = Field(default=None, ge=1)
    source_url: str = Field(default="", max_length=300)

    @field_validator("name", "summary", "reminders", "source_book", "source_url")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("name", "summary")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value:
            raise ValueError("This field cannot be blank")
        return value

    @field_validator("source_url")
    @classmethod
    def require_aon_url(cls, value: str) -> str:
        if value:
            parsed = urlparse(value)
            if parsed.scheme != "https" or parsed.netloc != "2e.aonprd.com":
                raise ValueError("Use an https://2e.aonprd.com link")
        return value


def initialize(database_path: Path) -> None:
    """Create the reference table and add missing official examples."""
    with closing(connect(database_path)) as connection, connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS rule_references (
                id INTEGER PRIMARY KEY,
                seed_key TEXT UNIQUE,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                summary TEXT NOT NULL,
                reminders TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL CHECK (kind IN ('official', 'note', 'house_rule')),
                source_book TEXT NOT NULL DEFAULT '',
                source_page INTEGER,
                source_url TEXT NOT NULL DEFAULT ''
            )
        """)
        seeds = json.loads((FOLDER / "seed.json").read_text(encoding="utf-8"))
        for entry in seeds:
            connection.execute("""
                INSERT OR IGNORE INTO rule_references
                (seed_key, name, category, summary, reminders, kind, source_book, source_page, source_url)
                VALUES (?, ?, ?, ?, ?, 'official', ?, ?, ?)
            """, (
                entry["key"], entry["name"], entry["category"], entry["summary"],
                entry["reminders"], entry["source_book"], entry["source_page"], entry["source_url"],
            ))


def list_entries(database_path: Path, query: str = "", category: str = "") -> list[dict]:
    if category and category not in CATEGORIES:
        raise ValueError("Unknown category")
    sql = "SELECT * FROM rule_references WHERE 1=1"
    parameters: list[str] = []
    if category:
        sql += " AND category = ?"
        parameters.append(category)
    if query.strip():
        escaped = query.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        sql += " AND lower(name || ' ' || summary || ' ' || reminders) LIKE ? ESCAPE '\\'"
        parameters.append(f"%{escaped}%")
    sql += " ORDER BY CASE kind WHEN 'official' THEN 0 ELSE 1 END, name COLLATE NOCASE, id"
    with closing(connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(sql, parameters)]


def get_entry(database_path: Path, entry_id: int) -> dict | None:
    with closing(connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT * FROM rule_references WHERE id = ?", (entry_id,)).fetchone()
        return dict(row) if row else None


def create_entry(database_path: Path, entry: UserEntry) -> dict:
    with closing(connect(database_path)) as connection, connection:
        cursor = connection.execute("""
            INSERT INTO rule_references
            (name, category, summary, reminders, kind, source_book, source_page, source_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.name, entry.category, entry.summary, entry.reminders, entry.kind,
            entry.source_book, entry.source_page, entry.source_url,
        ))
        entry_id = cursor.lastrowid
    return get_entry(database_path, entry_id)


def update_entry(database_path: Path, entry_id: int, entry: UserEntry) -> dict:
    current = get_entry(database_path, entry_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Reference not found")
    if current["kind"] == "official":
        raise HTTPException(status_code=403, detail="Official examples are read-only")
    with closing(connect(database_path)) as connection, connection:
        connection.execute("""
            UPDATE rule_references SET name=?, category=?, summary=?, reminders=?, kind=?,
                source_book=?, source_page=?, source_url=? WHERE id=? AND kind != 'official'
        """, (
            entry.name, entry.category, entry.summary, entry.reminders, entry.kind,
            entry.source_book, entry.source_page, entry.source_url, entry_id,
        ))
    return get_entry(database_path, entry_id)


def delete_entry(database_path: Path, entry_id: int) -> None:
    current = get_entry(database_path, entry_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Reference not found")
    if current["kind"] == "official":
        raise HTTPException(status_code=403, detail="Official examples are read-only")
    with closing(connect(database_path)) as connection, connection:
        connection.execute("DELETE FROM rule_references WHERE id=? AND kind != 'official'", (entry_id,))


def page() -> str:
    options = "".join(f'<option value="{category}">{category}</option>' for category in CATEGORIES)
    body = f"""
    <link rel="stylesheet" href="/tools/rules-reference/style.css">
    <nav aria-label="Breadcrumb"><a class="back-link" href="/">← All tools</a></nav>
    <div class="rules-heading">
      <div><h1>Rules Quick Reference</h1><p>Find concise pointers to commonly used rules and their official sources.</p><p>Follow the source link for the full rule.</p></div>
      <button type="button" id="new-entry">Add my entry</button>
    </div>
    <div class="rules-controls">
      <label>Search rules<input type="search" id="rule-query" placeholder="Name or keyword" autocomplete="off"></label>
      <label>Category<select id="rule-category"><option value="">All categories</option>{options}</select></label>
    </div>
    <p id="rule-count" role="status" aria-live="polite"></p>
    <div id="rules-list" class="rules-list"></div>
    <section id="entry-panel" class="entry-panel" hidden aria-labelledby="form-title">
      <h2 id="form-title">Add my entry</h2>
      <p>Choose Personal note or House rule. Sources you enter are shown as user supplied and unverified.</p>
      <form id="entry-form">
        <label>Name<input name="name" required maxlength="120"></label>
        <div class="form-pair">
          <label>Category<select name="category" required>{options}</select></label>
          <label>Entry type<select name="kind" required><option value="note">Personal note</option><option value="house_rule">House rule</option></select></label>
        </div>
        <label>Short explanation<textarea name="summary" required maxlength="600" rows="3"></textarea></label>
        <label>Exceptions or reminders<textarea name="reminders" maxlength="600" rows="2"></textarea></label>
        <div class="form-pair">
          <label>Source book, if known<input name="source_book" maxlength="120"></label>
          <label>Page, if known<input name="source_page" type="number" min="1"></label>
        </div>
        <label>Archives of Nethys link, if known<input name="source_url" type="url" maxlength="300" placeholder="https://2e.aonprd.com/..."></label>
        <p id="form-error" class="form-error" role="alert" hidden></p>
        <div class="form-actions"><button type="submit">Save entry</button><button type="button" id="cancel-entry" class="secondary">Cancel</button></div>
      </form>
    </section>
    <script src="/tools/rules-reference/app.js" defer></script>
    """
    return layout("Rules Quick Reference", body)


def register(app: FastAPI, database_path: Path) -> None:
    """Install this tool's page, assets, and API before the master fallback route."""

    @app.get("/tools/rules-reference", response_class=HTMLResponse)
    def rules_page() -> str:
        return page()

    @app.get("/tools/rules-reference/style.css")
    def style() -> FileResponse:
        return FileResponse(FOLDER / "style.css", media_type="text/css")

    @app.get("/tools/rules-reference/app.js")
    def script() -> FileResponse:
        return FileResponse(FOLDER / "app.js", media_type="text/javascript")

    @app.get("/api/rules-reference")
    def search(q: str = Query(default="", max_length=200), category: str = "") -> dict:
        try:
            items = list_entries(database_path, q, category)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"items": items, "count": len(items)}

    @app.post("/api/rules-reference", status_code=201)
    def create(entry: UserEntry) -> dict:
        return create_entry(database_path, entry)

    @app.put("/api/rules-reference/{entry_id}")
    def update(entry_id: int, entry: UserEntry) -> dict:
        return update_entry(database_path, entry_id, entry)

    @app.delete("/api/rules-reference/{entry_id}", status_code=204)
    def delete(entry_id: int) -> None:
        delete_entry(database_path, entry_id)
