"""GM Core XP tables, encounter guidance, and local persistence."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from master.app import create_app


FOLDER = Path(__file__).resolve().parent
spec = spec_from_file_location("encounter_calculator_test", FOLDER / "calculator.py")
calculator = module_from_spec(spec)
spec.loader.exec_module(calculator)
API = "/api/encounter-builder"


@pytest.mark.parametrize("relative,xp", [(-4, 10), (-3, 15), (-2, 20), (-1, 30), (0, 40), (1, 60), (2, 80), (3, 120), (4, 160)])
def test_every_relative_creature_level(relative, xp):
    assert calculator.creature_xp(5, 5 + relative) == xp


def test_unsupported_relative_levels():
    assert calculator.creature_xp(5, 0) is None
    assert calculator.creature_xp(5, 10) is None
    result = calculator.calculate(5, 4, "Moderate", [{"name": "Too strong", "level": 10, "quantity": 1}])
    assert result["total_xp"] is None
    assert result["remaining_xp"] is None
    assert "unsupported" in result["comparison"].lower()
    assert any("supported" in warning for warning in result["warnings"])


@pytest.mark.parametrize("difficulty,base,adjustment", [
    ("Trivial", 40, 10), ("Low", 60, 20), ("Moderate", 80, 20),
    ("Severe", 120, 30), ("Extreme", 160, 40),
])
def test_all_budgets_and_party_sizes(difficulty, base, adjustment):
    for party_size in range(2, 9):
        assert calculator.budget(difficulty, party_size) == base + (party_size - 4) * adjustment


def test_published_examples_a_and_d_and_quantity_change():
    creatures = [{"name": "Equal", "level": 5, "quantity": 1}, {"name": "Lower", "level": 1, "quantity": 4}]
    a = calculator.calculate(5, 4, "Moderate", creatures)
    assert (a["total_xp"], a["adjusted_target"], a["remaining_xp"]) == (80, 80, 0)
    assert a["comparison"] == "Matches Moderate target."
    assert [group["xp_total"] for group in a["creatures"]] == [40, 40]
    creatures[1]["quantity"] = 5
    d = calculator.calculate(5, 4, "Moderate", creatures)
    assert (d["total_xp"], d["difference_from_target"], d["remaining_xp"]) == (90, 10, -10)
    assert "Between Moderate (80 XP) and Severe (120 XP)" in d["comparison"]
    assert any("exceeds" in warning for warning in d["warnings"])
    assert "custom award" in d["award_guidance"]
    creatures.pop()
    assert calculator.calculate(5, 4, "Moderate", creatures)["total_xp"] == 40


@pytest.mark.parametrize("party_size,expected", [(3, 60), (5, 100)])
def test_published_examples_b_and_c_award_independent_of_party_size(party_size, expected):
    result = calculator.calculate(6 if party_size == 3 else 5, party_size, "Moderate", [])
    assert result["adjusted_target"] == expected
    assert result["standard_award_xp"] == 80
    assert "80 XP to each character" in result["award_guidance"]


def test_trivial_award_and_templates():
    trivial = calculator.calculate(5, 4, "Trivial", [])
    assert trivial["standard_award_xp"] is None
    assert "normally award no XP" in trivial["award_guidance"]
    assert {item["id"] for item in calculator.available_templates(1)} == {"two_equal", "strong_and_equal"}
    assert {item["id"] for item in calculator.available_templates(3)} == {"two_equal", "equal_and_four_weak", "strong_and_equal"}
    for item in calculator.available_templates(5):
        result = calculator.calculate(5, 4, "Moderate", item["creatures"])
        assert result["total_xp"] in {80, 120}


def test_api_validation_and_page(tmp_path):
    with TestClient(create_app(db_path=tmp_path / "encounters.sqlite3")) as client:
        page = client.get("/tools/encounter-builder")
        assert page.status_code == 200
        assert "Encounter Builder" in page.text and "Not implemented yet" not in page.text
        assert client.get("/tools/encounter-builder/app.js").status_code == 200
        assert client.get("/tools/encounter-builder/style.css").status_code == 200
        assert client.post(f"{API}/calculate", json={"party_level": 0}).status_code == 422
        assert client.post(f"{API}/calculate", json={"party_size": 9}).status_code == 422
        assert client.post(f"{API}/calculate", json={"target": "Impossible"}).status_code == 422
        assert client.post(f"{API}/calculate", json={"creatures": [{"name": "X", "level": -2, "quantity": 1}]}).status_code == 422
        assert client.post(f"{API}/calculate", json={"creatures": [{"name": "X", "level": 1, "quantity": 0}]}).status_code == 422
        assert client.post(f"{API}/calculate", json={"creatures": [{"name": "X", "level": 1, "quantity": 1, "url": "javascript:alert(1)"}]}).status_code == 422
        assert client.get(f"{API}/templates?party_level=0").status_code == 422


def test_save_load_edit_duplicate_delete_and_restart(tmp_path):
    path = tmp_path / "encounters.sqlite3"
    payload = {
        "name": "Bridge ambush", "party_level": 5, "party_size": 4, "target": "Moderate", "notes": "Fog on bridge",
        "creatures": [{"name": "Guard", "level": 5, "quantity": 1, "notes": "Watchful", "url": "https://example.org/guard"}],
    }
    with TestClient(create_app(db_path=path)) as client:
        created = client.post(f"{API}/encounters", json=payload)
        assert created.status_code == 201
        original_id = created.json()["id"]
        assert client.get(f"{API}/encounters/{original_id}").json()["creatures"] == payload["creatures"]
        assert len(client.get(f"{API}/encounters").json()) == 1
        payload["name"] = "Bridge ambush revised"
        payload["party_size"] = 5
        payload["creatures"][0]["quantity"] = 2
        updated = client.put(f"{API}/encounters/{original_id}", json=payload)
        assert updated.status_code == 200
        assert updated.json()["party_size"] == 5
        assert updated.json()["creatures"][0]["quantity"] == 2
        copy = client.post(f"{API}/encounters/{original_id}/duplicate")
        assert copy.status_code == 201
        copy_id = copy.json()["id"]
        assert copy_id != original_id
        assert copy.json()["name"].endswith("(copy)")
        assert client.delete(f"{API}/encounters/{original_id}").status_code == 204
        assert client.get(f"{API}/encounters/{original_id}").status_code == 404
    with TestClient(create_app(db_path=path)) as client:
        saved = client.get(f"{API}/encounters/{copy_id}")
        assert saved.status_code == 200
        assert saved.json()["creatures"][0]["quantity"] == 2
        assert client.delete(f"{API}/encounters/{copy_id}").status_code == 204
        assert client.get(f"{API}/encounters").json() == []
