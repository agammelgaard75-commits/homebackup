"""Shared campaign, party, and PC roster API.

The roster is a template. Running combat HP lives in Combat Tracker until the GM
explicitly copies it back. Other tools should reference member IDs, not duplicate
the roster table.
"""

from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.database.storage import connect


class NamedInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def clean_name(self):
        if not self.name.strip():
            raise ValueError("Enter a name")
        self.name = self.name.strip()
        return self


class PartyInput(NamedInput):
    campaign_id: int = Field(gt=0)


class MemberInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    class_name: str = Field(default="", max_length=80)
    max_hp: int | None = Field(default=None, gt=0)
    current_hp: int | None = Field(default=None, ge=0)
    speed: int | None = Field(default=None, gt=0)
    notes: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def check_hp(self):
        if self.current_hp is not None and (self.max_hp is None or self.current_hp > self.max_hp):
            raise ValueError("Current HP must be between 0 and maximum HP")
        if not self.name.strip():
            raise ValueError("Enter a PC name")
        self.name = self.name.strip()
        self.class_name = self.class_name.strip()
        return self


def _member(row) -> dict:
    return dict(zip(("id", "party_id", "name", "class_name", "max_hp", "current_hp", "speed", "notes"), row))


def members(db, party_id: int) -> list[dict]:
    return [_member(row) for row in db.execute(
        "SELECT id,party_id,name,class_name,max_hp,current_hp,speed,notes FROM party_members WHERE party_id=? ORDER BY id", (party_id,)
    )]


def require_party(db, party_id: int) -> None:
    if db.execute("SELECT 1 FROM parties WHERE id=?", (party_id,)).fetchone() is None:
        raise HTTPException(404, "Party not found")


def register(app: FastAPI, database_path: Path) -> None:
    base = "/api/party-roster"

    @app.get(base + "/campaigns")
    def list_campaigns():
        with closing(connect(database_path)) as db:
            return [{"id": row[0], "name": row[1]} for row in db.execute("SELECT id,name FROM campaigns ORDER BY name COLLATE NOCASE,id")]

    @app.post(base + "/campaigns", status_code=201)
    def create_campaign(values: NamedInput):
        with closing(connect(database_path)) as db, db:
            cursor = db.execute("INSERT INTO campaigns(name) VALUES (?)", (values.name.strip(),))
            return {"id": cursor.lastrowid, "name": values.name.strip()}

    @app.get(base + "/parties")
    def list_parties():
        with closing(connect(database_path)) as db:
            return [{"id": row[0], "campaign_id": row[1], "name": row[2]} for row in db.execute("SELECT id,campaign_id,name FROM parties ORDER BY name COLLATE NOCASE,id")]

    @app.post(base + "/parties", status_code=201)
    def create_party(values: PartyInput):
        with closing(connect(database_path)) as db, db:
            if db.execute("SELECT 1 FROM campaigns WHERE id=?", (values.campaign_id,)).fetchone() is None:
                raise HTTPException(404, "Campaign not found")
            cursor = db.execute("INSERT INTO parties(campaign_id,name) VALUES (?,?)", (values.campaign_id, values.name.strip()))
            return {"id": cursor.lastrowid, "campaign_id": values.campaign_id, "name": values.name.strip()}

    @app.get(base + "/parties/{party_id}/members")
    def list_members(party_id: int):
        with closing(connect(database_path)) as db:
            require_party(db, party_id)
            return members(db, party_id)

    @app.post(base + "/parties/{party_id}/members", status_code=201)
    def add_member(party_id: int, values: MemberInput):
        with closing(connect(database_path)) as db, db:
            require_party(db, party_id)
            cursor = db.execute("INSERT INTO party_members(party_id,name,class_name,max_hp,current_hp,speed,notes) VALUES (?,?,?,?,?,?,?)",
                                (party_id, values.name, values.class_name, values.max_hp, values.current_hp, values.speed, values.notes))
            return next(row for row in members(db, party_id) if row["id"] == cursor.lastrowid)

    @app.put(base + "/members/{member_id}")
    def edit_member(member_id: int, values: MemberInput):
        with closing(connect(database_path)) as db, db:
            row = db.execute("SELECT party_id FROM party_members WHERE id=?", (member_id,)).fetchone()
            if row is None:
                raise HTTPException(404, "PC not found")
            db.execute("UPDATE party_members SET name=?,class_name=?,max_hp=?,current_hp=?,speed=?,notes=? WHERE id=?",
                       (values.name, values.class_name, values.max_hp, values.current_hp, values.speed, values.notes, member_id))
            return next(item for item in members(db, row[0]) if item["id"] == member_id)

    @app.delete(base + "/members/{member_id}", status_code=204)
    def delete_member(member_id: int):
        with closing(connect(database_path)) as db, db:
            if db.execute("DELETE FROM party_members WHERE id=?", (member_id,)).rowcount == 0:
                raise HTTPException(404, "PC not found")
