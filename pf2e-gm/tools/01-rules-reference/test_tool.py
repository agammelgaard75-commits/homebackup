from pathlib import Path

from fastapi.testclient import TestClient

from master.app import create_app


def user_entry(**changes) -> dict:
    entry = {
        "name": "Shield note",
        "category": "Combat",
        "summary": "My short table reminder.",
        "reminders": "Ask about positioning.",
        "kind": "note",
        "source_book": "",
        "source_page": None,
        "source_url": "",
    }
    return entry | changes


def test_seed_search_and_categories(tmp_path: Path) -> None:
    with TestClient(create_app(db_path=tmp_path / "rules.sqlite3")) as client:
        response = client.get("/api/rules-reference")
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 10
        assert {item["category"] for item in items} == {
            "Combat", "Actions", "Conditions", "Skills", "Healing and Death",
            "Exploration", "General GM Rules",
        }
        assert all(item["kind"] == "official" for item in items)
        assert all(item["source_book"] and item["source_page"] and item["source_url"] for item in items)
        assert {item["source_book"] for item in items} == {"Player Core", "GM Core", "Monster Core"}

        by_name = client.get("/api/rules-reference", params={"q": "multiple attack"}).json()
        assert [item["name"] for item in by_name["items"]] == ["Multiple Attack Penalty"]
        by_keyword = client.get("/api/rules-reference", params={"q": "healer's toolkit"}).json()
        assert [item["name"] for item in by_keyword["items"]] == ["Treat Wounds"]
        by_category = client.get("/api/rules-reference", params={"category": "Exploration"}).json()
        assert [item["name"] for item in by_category["items"]] == ["Search (Exploration)"]
        combined = client.get("/api/rules-reference", params={"q": "cover", "category": "Combat"}).json()
        assert [item["name"] for item in combined["items"]] == ["Cover"]
        assert client.get("/api/rules-reference", params={"category": "Unknown"}).status_code == 422
        assert client.get("/api/rules-reference", params={"q": "%"}).json()["count"] == 0


def test_create_edit_delete_and_official_protection(tmp_path: Path) -> None:
    with TestClient(create_app(db_path=tmp_path / "rules.sqlite3")) as client:
        created = client.post("/api/rules-reference", json=user_entry())
        assert created.status_code == 201
        entry = created.json()
        assert entry["kind"] == "note"
        assert entry["seed_key"] is None
        assert client.get("/api/rules-reference", params={"q": "positioning"}).json()["count"] == 1

        updated = client.put(
            f"/api/rules-reference/{entry['id']}",
            json=user_entry(name="House shield rule", kind="house_rule", summary="Our table's rule."),
        )
        assert updated.status_code == 200
        assert updated.json()["kind"] == "house_rule"
        assert client.get("/api/rules-reference", params={"q": "House shield"}).json()["count"] == 1

        official_id = client.get("/api/rules-reference").json()["items"][0]["id"]
        assert client.put(f"/api/rules-reference/{official_id}", json=user_entry()).status_code == 403
        assert client.delete(f"/api/rules-reference/{official_id}").status_code == 403
        assert client.post("/api/rules-reference", json=user_entry(kind="official")).status_code == 422
        assert client.post("/api/rules-reference", json=user_entry(source_url="https://example.com/rule")).status_code == 422
        assert client.post("/api/rules-reference", json=user_entry(name="   ")).status_code == 422

        assert client.delete(f"/api/rules-reference/{entry['id']}").status_code == 204
        assert client.get("/api/rules-reference", params={"q": "House shield"}).json()["count"] == 0
        assert client.delete(f"/api/rules-reference/{entry['id']}").status_code == 404


def test_user_entries_persist_after_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "rules.sqlite3"
    with TestClient(create_app(db_path=database_path)) as client:
        created = client.post("/api/rules-reference", json=user_entry(name="Session note"))
        assert created.status_code == 201
        entry_id = created.json()["id"]

    with TestClient(create_app(db_path=database_path)) as client:
        items = client.get("/api/rules-reference").json()["items"]
        assert len(items) == 11
        assert any(item["id"] == entry_id and item["name"] == "Session note" for item in items)
        assert client.get("/tools/rules-reference").status_code == 200
        assert client.get("/tools/rules-reference/style.css").status_code == 200
        assert client.get("/tools/rules-reference/app.js").status_code == 200
