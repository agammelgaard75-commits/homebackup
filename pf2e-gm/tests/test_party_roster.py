"""Shared PC templates and their explicit Combat Tracker handoff."""

from fastapi.testclient import TestClient

from master.app import create_app


ROSTER = "/api/party-roster"
COMBAT = "/api/combat-tracker"


def test_party_roster_import_is_idempotent_and_hp_sync_is_explicit(tmp_path):
    path = tmp_path / "party.sqlite3"
    with TestClient(create_app(db_path=path)) as client:
        campaign = client.post(ROSTER + "/campaigns", json={"name": "The Road"}).json()
        party = client.post(ROSTER + "/parties", json={"name": "Heroes", "campaign_id": campaign["id"]}).json()
        url = f"{ROSTER}/parties/{party['id']}/members"
        fighter = client.post(url, json={"name": "Ari", "class_name": "Fighter", "max_hp": 30, "current_hp": 27, "speed": 25, "notes": "Shield"}).json()
        wizard = client.post(url, json={"name": "Bea", "class_name": "Wizard", "max_hp": 18, "current_hp": 18}).json()
        assert fighter["class_name"] == "Fighter" and wizard["id"] != fighter["id"]
        assert client.post(url, json={"name": "Bad", "max_hp": 10, "current_hp": 11}).status_code == 422

        encounter = client.post("/api/encounter-builder/encounters", json={
            "name": "Cave", "party_level": 2, "party_size": 2, "target": "Low", "notes": "",
            "creatures": [{"name": "Spider", "level": 0, "quantity": 1, "notes": "", "url": ""}],
        }).json()
        created = client.post(COMBAT + "/combats", json={"source_encounter_id": encounter["id"], "party_id": party["id"]})
        assert created.status_code == 201
        combat = created.json()
        actors = combat["combatants"]
        assert [(a["name"], a["type"]) for a in actors] == [("Spider", "monster"), ("Ari", "PC"), ("Bea", "PC")]
        assert actors[1]["initiative"] is None and actors[1]["current_hp"] == 27
        assert actors[1]["class_name"] == "Fighter" and actors[1]["party_member_id"] == fighter["id"]
        cid = combat["id"]
        assert client.post(f"{COMBAT}/combats/{cid}/party/{party['id']}").json()["added"] == 0
        client.post(f"{COMBAT}/combats/{cid}/command", json={"op": "damage", "combatant_id": actors[1]["id"], "amount": 7})
        assert client.get(url).json()[0]["current_hp"] == 27
        assert client.post(f"{COMBAT}/combats/{cid}/sync-party-hp").json()["updated"][0]["current_hp"] == 20
        assert client.get(url).json()[0]["current_hp"] == 20
        assert client.get("/tools/adventure-planner").status_code == 200
        assert client.get("/tools/combat-tracker").status_code == 200

    with TestClient(create_app(db_path=path)) as client:
        assert client.get(url).json()[0]["class_name"] == "Fighter"
        assert client.get(f"{COMBAT}/combats/{cid}").json()["combatants"][1]["current_hp"] == 20
        updated = client.put(f"{ROSTER}/members/{fighter['id']}", json={"name": "Ari", "class_name": "Champion", "max_hp": 32, "current_hp": 32}).json()
        assert updated["class_name"] == "Champion"
        assert client.delete(f"{ROSTER}/members/{wizard['id']}").status_code == 204
        assert len(client.get(url).json()) == 1
        assert len(client.get(f"{COMBAT}/combats/{cid}").json()["combatants"]) == 3


def test_add_missing_pcs_to_existing_combat_and_reject_other_party(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "db.sqlite3")) as client:
        campaign = client.post(ROSTER + "/campaigns", json={"name": "Campaign"}).json()
        first = client.post(ROSTER + "/parties", json={"name": "One", "campaign_id": campaign["id"]}).json()
        second = client.post(ROSTER + "/parties", json={"name": "Two", "campaign_id": campaign["id"]}).json()
        client.post(f"{ROSTER}/parties/{first['id']}/members", json={"name": "A", "class_name": "Rogue"})
        combat = client.post(COMBAT + "/combats", json={"name": "Started"}).json()
        cid = combat["id"]
        client.post(f"{COMBAT}/combats/{cid}/command", json={"op": "add", "name": "Enemy", "type": "monster"})
        imported = client.post(f"{COMBAT}/combats/{cid}/party/{first['id']}").json()
        assert imported["added"] == 1
        assert imported["combat"]["combatants"][1]["class_name"] == "Rogue"
        assert client.post(f"{COMBAT}/combats/{cid}/party/{second['id']}").status_code == 422
        client.post(f"{ROSTER}/parties/{first['id']}/members", json={"name": "B", "class_name": "Bard"})
        assert client.post(f"{COMBAT}/combats/{cid}/party/{first['id']}").json()["added"] == 1
        assert client.post(f"{COMBAT}/combats/{cid}/party/{first['id']}").json()["added"] == 0
