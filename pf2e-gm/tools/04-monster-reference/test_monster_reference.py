"""Phase 11 monster creation, completeness, and tool handoff."""

import json

import pytest
from fastapi.testclient import TestClient

from master.app import create_app


API = "/api/monster-reference"
MINIMAL = {"name": "Cave Spider", "level": 1, "max_hp": 20}


def test_minimal_gui_and_json_import_share_validation(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "db.sqlite3")) as client:
        page = client.get("/tools/monster-reference")
        assert page.status_code == 200 and "Quick Add" in page.text and "Maximum HP" in page.text
        script = client.get("/tools/monster-reference/app.js").text
        assert "Detailed Editor" in page.text and "Save and continue editing" in script
        created = client.post(API + "/monsters", json=MINIMAL)
        imported = client.post(API + "/import", json=MINIMAL)
        assert created.status_code == imported.status_code == 201
        assert created.json()["completeness"]["level"] == imported.json()[0]["completeness"]["level"] == "Basic"
        monster = created.json()
        assert monster["ac"] is None and monster["perception"] is None and monster["attacks"] == []
        for bad in ({"level": 1, "max_hp": 20}, {"name": "X", "max_hp": 20}, {"name": "X", "level": 1},
                    {"name": "X", "level": 1, "max_hp": 0}, {"name": "X", "level": 1, "max_hp": -2},
                    {"name": "   ", "level": 1, "max_hp": 20}):
            assert client.post(API + "/monsters", json=bad).status_code == 422
            assert client.post(API + "/import", json=bad).status_code == 422


def test_completeness_edits_filters_spells_and_collections(tmp_path):
    path = tmp_path / "db.sqlite3"
    with TestClient(create_app(db_path=path)) as client:
        monster = client.post(API + "/monsters", json=MINIMAL).json()
        mid = monster["id"]
        assert "AC" in monster["completeness"]["missing_for_next"]
        ready = {**MINIMAL, "ac": 16, "fortitude": 0, "reflex": -1, "will": 2,
                 "speeds": [{"type": "land", "feet": 25}], "attacks": [{"name": "Fangs", "modifier": -2}]}
        edited = client.put(f"{API}/monsters/{mid}", json=ready).json()
        assert edited["completeness"]["level"] == "Combat Ready"
        assert edited["reflex"] == -1 and edited["fortitude"] == 0
        detailed = client.put(f"{API}/monsters/{mid}", json={**ready, "traits": ["animal"]}).json()
        assert detailed["completeness"]["level"] == "Detailed"
        assert [m["id"] for m in client.get(API + "/monsters", params={"completeness": "Detailed"}).json()] == [mid]
        lowered = client.put(f"{API}/monsters/{mid}", json={**ready, "reflex": None}).json()
        assert lowered["completeness"]["level"] == "Basic"
        assert "Reflex" in lowered["completeness"]["missing_for_next"]
        spell = client.post(API + "/monsters", json={**ready, "name": "Mage", "attacks": [],
            "spellcasting": [{"name": "Fire spell", "offensive": True}]}).json()
        assert spell["completeness"]["level"] == "Detailed"
        ability = client.post(API + "/monsters", json={**ready, "name": "Howler", "attacks": [],
            "abilities": [{"name": "Howl", "usable_in_combat": True}]}).json()
        assert ability["completeness"]["level"] == "Detailed"
        collection = client.post(API + "/collections", json={"name": "Session 1"}).json()
        assert client.post(f"{API}/collections/{collection['id']}/monsters", json={"monster_id": mid}).status_code == 201
        assert client.get(API + "/collections").json()[0]["monsters"][0]["completeness"]["level"] == "Basic"
        assert client.delete(f"{API}/collections/{collection['id']}/monsters/{mid}").status_code == 204
    with TestClient(create_app(db_path=path)) as client:
        assert client.get(f"{API}/monsters/{mid}").json()["completeness"]["level"] == "Basic"


def test_multiple_entries_roundtrip_duplicate_and_legacy_hp(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "db.sqlite3")) as client:
        value = {**MINIMAL, "attacks": [{"name": "Bite", "modifier": 5}, {"name": "Web", "modifier": 3}],
                 "abilities": [{"name": "Ambush", "usable_in_combat": True}, {"name": "Climb walls"}],
                 "skills": {"Stealth": -1}, "senses": ["darkvision"]}
        created = client.post(API + "/monsters", json=value).json()
        exported = client.get(f"{API}/monsters/{created['id']}/export").json()
        assert exported["schema_version"] == 1 and "completeness" not in exported and "id" not in exported
        copy = client.post(API + "/import", json=exported).json()[0]
        assert copy["attacks"] == created["attacks"] and copy["abilities"] == created["abilities"]
        assert client.post(API + "/import", json={"schema_version": 1, "monsters": [MINIMAL]}).status_code == 201
        legacy = client.post(API + "/import", json={"name": "Legacy", "level": 0, "defenses": {"hp": 9, "ac": 13}}).json()[0]
        assert legacy["max_hp"] == 9 and legacy["ac"] == 13
        assert client.post(API + "/import", json={"name": "Conflict", "level": 1, "max_hp": 20, "defenses": {"hp": 30}}).status_code == 422
        assert client.post(API + "/import", json={"schema_version": 2, **MINIMAL}).status_code == 422
        duplicate = client.post(f"{API}/monsters/{created['id']}/duplicate").json()
        assert duplicate["name"].endswith("(copy)") and duplicate["id"] != created["id"]


def test_basic_monster_encounter_and_combat_copy(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "db.sqlite3")) as client:
        monster = client.post(API + "/monsters", json=MINIMAL).json()
        mid = monster["id"]
        encounter = client.post("/api/encounter-builder/encounters", json={"name": "Web", "party_level": 1,
            "party_size": 4, "target": "Moderate", "creatures": [{"name": "Cave Spider", "level": 1, "quantity": 2, "monster_id": mid}]}).json()
        assert encounter["creatures"][0]["monster_id"] == mid
        combat = client.post("/api/combat-tracker/combats", json={"source_encounter_id": encounter["id"]}).json()
        assert len(combat["combatants"]) == 2
        assert all(a["max_hp"] == a["current_hp"] == 20 and a["monster_id"] == mid for a in combat["combatants"])
        cid = combat["id"]
        client.post(f"/api/combat-tracker/combats/{cid}/command", json={"op": "damage", "combatant_id": 1, "amount": 7})
        assert client.get(f"{API}/monsters/{mid}").json()["max_hp"] == 20
        assert client.get(f"/api/combat-tracker/combats/{cid}").json()["combatants"][0]["current_hp"] == 13
        client.put(f"{API}/monsters/{mid}", json={**MINIMAL, "ac": 15, "fortitude": 0,
            "reflex": -1, "will": 2, "speeds": [{"type": "land", "feet": 25}],
            "attacks": [{"name": "Fangs", "modifier": 4}]}).raise_for_status()
        direct = client.post(f"/api/combat-tracker/combats/{cid}/monsters", json={"monster_id": mid}).json()
        assert direct["combatants"][-1]["current_hp"] == 20
        assert direct["combatants"][-1]["monster_stats"]["ac"] == 15
        assert direct["combatants"][-1]["monster_stats"]["reflex"] == -1
        assert "ac" not in direct["combatants"][0]["monster_stats"]
        assert client.delete(f"{API}/monsters/{mid}").status_code == 204
        fallback = client.post("/api/combat-tracker/combats", json={"source_encounter_id": encounter["id"]}).json()
        assert fallback["combatants"][0]["name"].startswith("Cave Spider")
        assert fallback["combatants"][0]["max_hp"] is None


def test_documented_attack_and_ability_shape_roundtrip(tmp_path):
    value = {
        "schema_version": 1, "name": "Cave Skitter Spider", "level": 1, "max_hp": 20,
        "ac": 16, "fortitude": 7, "reflex": 10, "will": 4, "perception": 7,
        "traits": ["animal"], "senses": ["darkvision"],
        "skills": {"Stealth": 7, "Athletics": 6},
        "speeds": [{"type": "land", "feet": 25}, {"type": "climb", "feet": 20}],
        "attacks": [{"name": "Fangs", "type": "melee", "actions": 1, "bonus": 9,
                     "traits": ["finesse"], "damage": "1d4+2 piercing",
                     "effect": "On a hit, expose the target to venom."}],
        "abilities": [{"name": "Venom", "actions": "passive", "traits": ["poison"],
                       "trigger": None, "requirements": None, "description": "Fortitude save.", "dc": 17},
                      {"name": "Web Tremorsense", "actions": "passive", "traits": [],
                       "trigger": None, "requirements": None, "description": "Sense web vibrations.", "dc": None}],
        "spellcasting": [], "source_book": "Homebrew", "source_page": None,
        "source_url": "", "notes": "Original creature."
    }
    with TestClient(create_app(db_path=tmp_path / "db.sqlite3")) as client:
        page = client.get("/tools/monster-reference/app.js").text
        assert "Attack bonus" in page and "Requirements" in page and "Actions or passive" in page
        imported = client.post(API + "/import", json=value)
        assert imported.status_code == 201, imported.text
        monster = imported.json()[0]
        assert monster["attacks"][0]["bonus"] == 9
        assert monster["attacks"][0]["effect"] == value["attacks"][0]["effect"]
        assert monster["abilities"][0]["dc"] == 17
        assert monster["completeness"]["level"] == "Detailed"
        exported = client.get(f"{API}/monsters/{monster['id']}/export").json()
        assert exported == value
        edited = {**value, "attacks": [{**value["attacks"][0], "bonus": 0}],
                  "abilities": [{**value["abilities"][0], "dc": -1}]}
        updated = client.put(f"{API}/monsters/{monster['id']}", json=edited)
        assert updated.status_code == 200, updated.text
        assert updated.json()["attacks"][0]["bonus"] == 0
        assert updated.json()["abilities"][0]["dc"] == -1
        assert client.post(API + "/monsters", json=value).status_code == 201


def test_legacy_entry_fields_migrate_without_losing_saved_data(tmp_path):
    from shared.database.storage import connect
    from contextlib import closing
    path = tmp_path / "db.sqlite3"
    with TestClient(create_app(db_path=path)) as client:
        old = {**MINIMAL, "attacks": [{"name": "Bite", "modifier": -2, "description": "Old effect"}],
               "abilities": [{"name": "Pounce", "usable_in_combat": True, "description": "Old ability"}]}
        with closing(connect(path)) as db, db:
            db.execute("INSERT INTO monsters(name,level,max_hp,data_json) VALUES (?,?,?,?)",
                       (old["name"], old["level"], old["max_hp"], json.dumps(old)))
        monster = client.get(API + "/monsters/1").json()
        assert monster["attacks"][0]["bonus"] == -2
        assert monster["attacks"][0]["type"] is None and monster["attacks"][0]["actions"] is None
        assert monster["attacks"][0]["effect"] == "Old effect"
        assert monster["abilities"][0]["description"] == "Old ability"
        assert monster["completeness"]["level"] == "Basic"  # Defenses are still missing.
        assert client.get(API + "/monsters/1/export").json()["attacks"][0]["bonus"] == -2


def test_read_only_details_from_combat_keep_saved_monster_snapshot(tmp_path):
    value = {**MINIMAL, "name": "Web Spider", "ac": 16, "fortitude": 7, "reflex": 10,
             "will": 4, "perception": 7, "traits": ["animal"], "senses": ["darkvision"],
             "skills": {"Stealth": 7}, "speeds": [{"type": "climb", "feet": 20}],
             "attacks": [{"name": "Fangs", "type": "melee", "actions": 1, "bonus": 9,
                          "traits": ["finesse"], "damage": "1d4 piercing", "effect": "Venom on a hit"}],
             "abilities": [{"name": "Venom", "actions": "passive", "traits": ["poison"],
                            "trigger": "Fangs hit", "requirements": "Target is living",
                            "description": "Fortitude save", "dc": 17}],
             "spellcasting": [{"name": "Web spell", "description": "Optional magical effect", "offensive": True}],
             "source_book": "Homebrew", "source_page": 3,
             "source_url": "https://example.com/monster", "notes": "GM note <script>alert(1)</script>"}
    with TestClient(create_app(db_path=tmp_path / "db.sqlite3")) as client:
        monster = client.post(API + "/monsters", json=value).json()
        library_url = f"/tools/monster-reference/monsters/{monster['id']}"
        library_page = client.get(library_url)
        assert library_page.status_code == 200
        assert "Read-only monster details" in library_page.text
        assert "Venom on a hit" in library_page.text and "Target is living" in library_page.text
        assert "Web spell" in library_page.text and "https://example.com/monster" in library_page.text
        assert "<script>alert(1)</script>" not in library_page.text
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in library_page.text
        assert 'id="monster-form"' not in library_page.text and "Detailed Editor" not in library_page.text
        combat = client.post("/api/combat-tracker/combats", json={"name": "Spider Fight"}).json()
        cid = combat["id"]
        combat = client.post(f"/api/combat-tracker/combats/{cid}/monsters", json={"monster_id": monster["id"]}).json()
        actor_id = combat["combatants"][0]["id"]
        detail_url = f"/tools/combat-tracker/combats/{cid}/monsters/{actor_id}"
        script = client.get("/tools/combat-tracker/app.js").text
        assert "monsterDetailsLink(item)" in script and detail_url.split("/combats/")[0] in script
        response = client.get(detail_url)
        assert response.status_code == 200
        assert "Combat snapshot from Spider Fight" in response.text
        assert "Venom on a hit" in response.text and "Fortitude save" in response.text
        assert f"/tools/combat-tracker?combat_id={cid}" in response.text
        encounter = client.post("/api/encounter-builder/encounters", json={
            "name": "Web Nest", "party_level": 1, "party_size": 4, "target": "Moderate",
            "creatures": [{"name": "Web Spider", "level": 1, "quantity": 1,
                           "monster_id": monster["id"], "notes": "Combat placement note"}]}).json()
        encounter_combat = client.post("/api/combat-tracker/combats", json={"source_encounter_id": encounter["id"]}).json()
        encounter_detail = client.get(f"/tools/combat-tracker/combats/{encounter_combat['id']}/monsters/1").text
        assert "Combat placement note" in encounter_detail
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in encounter_detail
        client.post(f"/api/combat-tracker/combats/{cid}/command", json={"op": "damage", "combatant_id": actor_id, "amount": 5}).raise_for_status()
        client.put(f"{API}/monsters/{monster['id']}", json={**MINIMAL, "name": "Changed Spider"}).raise_for_status()
        after_edit = client.get(detail_url).text
        assert "Current HP: 15" in after_edit and "Venom on a hit" in after_edit
        assert "Changed Spider" not in after_edit
        client.delete(f"{API}/monsters/{monster['id']}").raise_for_status()
        assert client.get(library_url).status_code == 404
        assert "Venom on a hit" in client.get(detail_url).text
        assert client.get(f"/tools/combat-tracker/combats/{cid}/monsters/999").status_code == 404


def test_manual_monster_has_read_only_combat_detail_page(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "db.sqlite3")) as client:
        combat = client.post("/api/combat-tracker/combats", json={"name": "Manual"}).json()
        cid = combat["id"]
        combat = client.post(f"/api/combat-tracker/combats/{cid}/command", json={
            "op": "add", "name": "Unknown Beast", "type": "monster", "max_hp": 12, "current_hp": 12}).json()
        aid = combat["combatants"][0]["id"]
        page = client.get(f"/tools/combat-tracker/combats/{cid}/monsters/{aid}")
        assert page.status_code == 200
        assert "No library stat block was copied" in page.text
        assert "Unknown Beast" in page.text and "Not entered" in page.text
