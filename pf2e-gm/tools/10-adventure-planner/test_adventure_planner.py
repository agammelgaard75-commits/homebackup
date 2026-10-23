"""Phase 10 records, nonlinear play, integration, backups, and restart tests."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from master.app import create_app
from shared.database.storage import connect

BASE = "/api/adventure-planner"


@pytest.fixture
def client(tmp_path):
    path = tmp_path / "planner.sqlite3"
    with TestClient(create_app(db_path=path)) as c:
        yield c, path


def request(c, method, path, body=None, status=200):
    response = c.request(method, BASE + path, json=body)
    assert response.status_code == status, response.text
    return None if status == 204 else response.json()


def new_adventure(c, **extra):
    return request(c, "POST", "/adventures", {"title": "The Open Road", **extra}, 201)["adventure"]["id"]


def scene(c, aid, title, **extra):
    return request(c, "POST", f"/adventures/{aid}/scenes", {"title": title, **extra}, 201)["id"]


def snapshot(c, aid):
    return request(c, "GET", f"/adventures/{aid}")


def test_adventure_crud_campaign_party_archive_duplicate(client):
    c, path = client
    with connect(path) as db:
        campaign = db.execute("INSERT INTO campaigns(name) VALUES ('North')").lastrowid
        party = db.execute("INSERT INTO parties(campaign_id,name) VALUES (?,'Heroes')", (campaign,)).lastrowid
    aid = new_adventure(c, campaign_id=campaign, party_id=party, main_objective="Find the bell", expected_players=4)
    assert snapshot(c, aid)["adventure"]["party_id"] == party
    raw = snapshot(c, aid)["adventure"]
    body = {k: raw[k] for k in ("title", "description", "starting_situation", "main_objective", "suggested_level", "expected_players", "estimated_hours", "secrets", "outcomes", "gm_notes", "campaign_id", "party_id")}
    body["description"] = "A short mystery"
    assert request(c, "PATCH", f"/adventures/{aid}", body)["adventure"]["description"] == "A short mystery"
    assert request(c, "POST", f"/adventures/{aid}/archive")["status"] == "archived"
    duplicate = request(c, "POST", f"/adventures/{aid}/duplicate", status=201)
    assert duplicate["adventure"]["title"].endswith("(copy)")
    assert duplicate["adventure"]["party_id"] == party
    request(c, "DELETE", f"/adventures/{aid}", status=204)
    assert c.get(BASE + f"/adventures/{aid}").status_code == 404
    assert snapshot(c, duplicate["adventure"]["id"])["adventure"]["description"] == "A short mystery"


def test_nonlinear_scenes_connections_and_reorder(client):
    c, _ = client
    aid = new_adventure(c)
    ids = [scene(c, aid, f"Scene {i}", duration_minutes=30) for i in range(1, 6)]
    request(c, "POST", f"/adventures/{aid}/scenes/{ids[3]}/select")
    assert [s["status"] for s in snapshot(c, aid)["scenes"]] == ["not_started"] * 3 + ["active", "not_started"]
    fourth = next(s for s in snapshot(c, aid)["scenes"] if s["id"] == ids[3])
    body = {k: fourth[k] for k in ("title", "type", "status", "location", "purpose", "description", "complications", "duration_minutes", "notes")}
    body["status"] = "completed"
    request(c, "PATCH", f"/adventures/{aid}/scenes/{ids[3]}", body)
    assert snapshot(c, aid)["scenes"][1]["status"] == "not_started"
    connection = request(c, "POST", f"/adventures/{aid}/connections", {"from_scene_id": ids[0], "to_scene_id": ids[4], "kind": "alternative_route"}, 201)
    assert connection["kind"] == "alternative_route"
    ordered = request(c, "POST", f"/adventures/{aid}/scenes/reorder", {"scene_ids": ids[::-1]})
    assert [s["id"] for s in ordered] == ids[::-1]
    copy = request(c, "POST", f"/adventures/{aid}/scenes/{ids[0]}/duplicate", status=201)
    assert copy["status"] == "not_started"
    assert c.post(BASE + f"/adventures/{aid}/scenes/reorder", json={"scene_ids": ids}).status_code == 422
    assert snapshot(c, aid)["scenes"][1]["status"] == "completed"


def test_npc_clue_item_and_session_recap(client):
    c, _ = client
    aid = new_adventure(c)
    first = scene(c, aid, "Market", duration_minutes=180)
    second = scene(c, aid, "Tower", duration_minutes=180)
    npc = request(c, "POST", f"/adventures/{aid}/npcs", {"name": "Mira", "role": "Guide", "knows": "The tower route", "scene_ids": [first, second]}, 201)
    assert npc["scene_ids"] == [first, second]
    clue = request(c, "POST", f"/adventures/{aid}/clues", {"name": "Blue sigil", "reveals": "The hidden door", "scene_ids": [first, second]}, 201)
    item = request(c, "POST", f"/adventures/{aid}/items", {"name": "Brass key", "scene_ids": [second]}, 201)
    objective = request(c, "POST", f"/adventures/{aid}/items", {"name": "Find the bell", "kind": "objective", "scene_ids": [second]}, 201)
    sid = request(c, "POST", f"/adventures/{aid}/sessions", {"title": "Session One", "planned_minutes": 300, "scene_ids": [first, second], "next_session_notes": "Prepare the harbor"}, 201)["id"]
    assert snapshot(c, aid)["sessions"][0]["budget"] == {"planned_minutes": 300, "scene_minutes": 360, "buffer_minutes": -60, "over_budget": True}
    request(c, "PATCH", f"/adventures/{aid}/clues/{clue['id']}", {"name": "Blue sigil", "reveals": "The hidden door", "scene_ids": [first, second], "discovered": True, "discovered_scene_id": second, "discovered_session_id": sid})
    request(c, "PATCH", f"/adventures/{aid}/items/{item['id']}", {"name": "Brass key", "scene_ids": [second], "obtained": True, "obtained_session_id": sid})
    for scene_id in [first, second]:
        current = next(s for s in snapshot(c, aid)["scenes"] if s["id"] == scene_id)
        payload = {k: current[k] for k in ("title", "type", "location", "purpose", "description", "complications", "duration_minutes", "notes")}
        request(c, "PATCH", f"/adventures/{aid}/scenes/{scene_id}", {**payload, "status": "completed", "completed_session_id": sid})
    for text in ("Spared the thief", "Took the high path"):
        request(c, "POST", f"/adventures/{aid}/sessions/{sid}/events", {"text": text, "kind": "decision", "scene_id": second}, 201)
    recap = request(c, "GET", f"/adventures/{aid}/sessions/{sid}/recap")["generated"]
    for value in ("Market", "Tower", "Blue sigil", "Brass key", "Spared the thief", "Took the high path", "Find the bell", "Prepare the harbor"):
        assert value in recap
    assert "Mira" not in recap  # No invented NPC interaction.
    assert "Completed encounters" not in recap
    assert len(snapshot(c, aid)["clues"]) == 1
    assert snapshot(c, aid)["clues"][0]["discovered_scene_id"] == second
    assert snapshot(c, aid)["items"][1]["obtained"] == 0
    # Correct a mistaken note without creating a second entry.
    event = snapshot(c, aid)["sessions"][0]["events"][0]
    request(c, "PATCH", f"/adventures/{aid}/sessions/{sid}/events/{event['id']}", {"text": "Spared the scout", "kind": "decision", "scene_id": second})
    assert len(snapshot(c, aid)["sessions"][0]["events"]) == 2
    assert "Spared the scout" in request(c, "GET", f"/adventures/{aid}/sessions/{sid}/recap")["generated"]


def test_encounter_link_missing_and_exports_import_restart(client):
    c, path = client
    encounter = c.post("/api/encounter-builder/encounters", json={"name": "Bridge ambush", "party_level": 5, "party_size": 4, "target": "Moderate", "creatures": [{"name": "Bandit", "level": 5, "quantity": 2}]}).json()
    aid = new_adventure(c, gm_notes="Prepare a bridge")
    sid = scene(c, aid, "Bridge", type="combat", duration_minutes=45)
    link = request(c, "POST", f"/adventures/{aid}/scenes/{sid}/encounters", {"encounter_id": encounter["id"]}, 201)
    assert link["name"] == "Bridge ambush" and link["xp"] == 80
    assert "Moderate" in link["difficulty"]
    assert len(link["creatures"]) == 1
    assert c.get("/tools/combat-tracker").status_code == 200
    assert c.get("/tools/encounter-builder").status_code == 200
    request(c, "POST", f"/adventures/{aid}/npcs", {"name": "Guard", "scene_ids": [sid]}, 201)
    session_id = request(c, "POST", f"/adventures/{aid}/sessions", {"title": "Bridge session", "scene_ids": [sid], "planned_minutes": 60}, 201)["id"]
    request(c, "POST", f"/adventures/{aid}/sessions/{session_id}/events", {"text": "Party crossed", "kind": "note", "scene_id": sid}, 201)
    exported = request(c, "GET", f"/adventures/{aid}/export.json")
    assert "Bridge" in c.get(BASE + f"/adventures/{aid}/export.md").text
    imported = request(c, "POST", "/import", exported, 201)
    assert imported["adventure"]["id"] != aid
    assert imported["npcs"][0]["scene_ids"] == [imported["scenes"][0]["id"]]
    assert imported["sessions"][0]["events"][0]["text"] == "Party crossed"
    assert imported["encounters"][0]["xp"] == 80
    assert c.post(BASE + "/import", json={**exported, "version": 99}).status_code == 422
    assert c.post(BASE + "/import", json={**exported, "scenes": [{"oops": True}]}).status_code == 422
    c.delete(f"/api/encounter-builder/encounters/{encounter['id']}")
    snap = snapshot(c, aid)
    assert snap["scenes"][0]["title"] == "Bridge" and snap["encounters"][0]["missing"]
    with TestClient(create_app(db_path=path)) as restarted:
        after = snapshot(restarted, aid)
        assert after["npcs"][0]["name"] == "Guard"
        assert after["sessions"][0]["events"][0]["text"] == "Party crossed"
        assert after["encounters"][0]["missing"]


def test_dashboard_page_and_assets(client):
    c, _ = client
    assert '/tools/adventure-planner' in c.get('/').text
    page = c.get('/tools/adventure-planner')
    assert page.status_code == 200 and 'Organize adventure preparation and session notes.' in page.text
    assert c.get('/tools/adventure-planner/app.js').status_code == 200
    assert c.get('/tools/adventure-planner/style.css').status_code == 200


def test_import_accepts_display_labels_and_reports_invalid_scene(client):
    c, _ = client
    backup = {
        "version": 1,
        "adventure": {"title": "New adventure", "current_scene_id": None},
        "scenes": [{"id": 1, "title": "Opening", "type": "Investigation", "status": "Not Started"}],
        "npcs": [], "clues": [], "items": [], "connections": [], "encounters": [], "sessions": [],
    }
    imported = request(c, "POST", "/import", backup, 201)
    assert imported["adventure"]["current_scene_id"] is None
    assert imported["scenes"][0]["type"] == "investigation"
    assert imported["scenes"][0]["status"] == "not_started"
    count = len(request(c, "GET", "/adventures"))
    backup["scenes"][0]["type"] = "Social"
    response = c.post(BASE + "/import", json=backup)
    assert response.status_code == 422
    assert "Scene 1 ('Opening'): type 'Social' is invalid" in response.json()["detail"]
    assert len(request(c, "GET", "/adventures")) == count
