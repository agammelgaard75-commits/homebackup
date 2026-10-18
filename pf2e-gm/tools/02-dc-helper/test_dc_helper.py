from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from master.app import create_app


spec = spec_from_file_location("tested_dc_calculator", Path(__file__).with_name("calculator.py"))
calculator = module_from_spec(spec)
spec.loader.exec_module(calculator)


def test_every_simple_dc() -> None:
    expected = {"Untrained": 10, "Trained": 15, "Expert": 20, "Master": 30, "Legendary": 40}
    assert {name: calculator.base_dc("simple", proficiency=name) for name in expected} == expected


def test_every_level_dc_matches_gm_core_table() -> None:
    # GM Core p. 52, Table 10-5: https://2e.aonprd.com/Rules.aspx?ID=2629
    expected = (
        14, 15, 16, 18, 19, 20, 22, 23, 24, 26, 27, 28, 30,
        31, 32, 34, 35, 36, 38, 39, 40, 42, 44, 46, 48, 50,
    )
    assert len(expected) == 26
    for level, dc in enumerate(expected):
        assert calculator.base_dc("level", level=level) == dc


@pytest.mark.parametrize("name,amount", [
    ("Incredibly easy", -10), ("Very easy", -5), ("Easy", -2),
    ("Standard", 0), ("Hard", 2), ("Very hard", 5), ("Incredibly hard", 10),
])
def test_each_adjustment(name: str, amount: int) -> None:
    assert calculator.adjusted_dc(20, name) == (amount, 20 + amount)


def test_manual_dc_and_all_degrees_at_boundaries() -> None:
    assert calculator.base_dc("manual", manual_dc=17) == 17
    assert calculator.check_result(10, 10, 10) == (20, 10, "Critical success")
    assert calculator.check_result(10, 0, 10) == (10, 0, "Success")
    assert calculator.check_result(10, -1, 10) == (9, -1, "Failure")
    assert calculator.check_result(10, -10, 10) == (0, -10, "Critical failure")
    assert calculator.check_result(10, -9, 10) == (1, -9, "Failure")
    assert calculator.check_result(10, 9, 10) == (19, 9, "Success")


def test_natural_20_and_1_shift_only_one_degree() -> None:
    assert calculator.check_result(20, 0, 50) == (20, -30, "Failure")
    assert calculator.check_result(20, 0, 30) == (20, -10, "Failure")
    assert calculator.check_result(20, 0, 25) == (20, -5, "Success")
    assert calculator.check_result(1, 20, 10) == (21, 11, "Success")
    assert calculator.check_result(1, 10, 10) == (11, 1, "Failure")
    assert calculator.check_result(1, 0, 10) == (1, -9, "Critical failure")


@pytest.mark.parametrize("call", [
    lambda: calculator.base_dc("simple", proficiency="Novice"),
    lambda: calculator.base_dc("level", level=-1),
    lambda: calculator.base_dc("level", level=26),
    lambda: calculator.base_dc("level", level=True),
    lambda: calculator.base_dc("manual", manual_dc=0),
    lambda: calculator.base_dc("manual", manual_dc=-5),
    lambda: calculator.base_dc("manual", manual_dc=2.5),
    lambda: calculator.base_dc("unknown"),
    lambda: calculator.adjusted_dc(20, "Impossible"),
    lambda: calculator.check_result(0, 0, 15),
    lambda: calculator.check_result(21, 0, 15),
    lambda: calculator.check_result(10, 0.5, 15),
])
def test_calculator_rejects_invalid_inputs(call) -> None:
    with pytest.raises(ValueError):
        call()


def test_local_api_and_page(tmp_path: Path) -> None:
    with TestClient(create_app(db_path=tmp_path / "test.sqlite3")) as client:
        page = client.get("/tools/dc-helper")
        assert page.status_code == 200
        for text in ("Simple", "Level-based", "Manual", "Secret check", "Optional check result calculator"):
            assert text in page.text
        for rule_id in (2628, 2629, 2630, 2263):
            assert f"Rules.aspx?ID={rule_id}" in page.text
        assert '/tools/rules-reference' in page.text
        assert client.get("/tools/dc-helper/style.css").status_code == 200
        assert client.get("/tools/dc-helper/app.js").status_code == 200

        response = client.post("/api/dc-helper/calculate", json={
            "mode": "level", "level": 15, "difficulty": "Hard", "skill": "Athletics",
            "roll": 20, "modifier": 0,
        })
        assert response.status_code == 200
        assert response.json()["base_dc"] == 34
        assert response.json()["adjustment"] == 2
        assert response.json()["final_dc"] == 36
        assert response.json()["check"] == {
            "total": 20, "total_text": "20", "difference": -16,
            "difference_text": "-16", "degree": "Failure",
        }

        simple = {"mode": "simple", "proficiency": "Expert", "difficulty": "Standard"}
        first = client.post("/api/dc-helper/calculate", json=simple | {"skill": "Stealth"}).json()
        second = client.post("/api/dc-helper/calculate", json=simple | {"skill": "Perception"}).json()
        assert first["final_dc"] == second["final_dc"] == 20
        manual = client.post("/api/dc-helper/calculate", json={"mode": "manual", "manual_dc": "27"})
        assert manual.status_code == 200
        assert manual.json()["final_dc"] == 27
        large = "123456789012345678901234567890"
        large_response = client.post("/api/dc-helper/calculate", json={"mode": "manual", "manual_dc": large})
        assert large_response.status_code == 200
        assert large_response.json()["final_dc_text"] == large
        pending = client.post("/api/dc-helper/calculate", json={"roll": 12}).json()
        assert pending["check"] is None and pending["check_pending"] is True


@pytest.mark.parametrize("payload", [
    {"mode": "level", "level": -1}, {"mode": "level", "level": 26},
    {"mode": "manual"}, {"mode": "manual", "manual_dc": 0},
    {"mode": "manual", "manual_dc": "1.5"}, {"mode": "missing"},
    {"proficiency": "Novice"}, {"difficulty": "Impossible"},
    {"skill": "Not a skill"}, {"roll": 0}, {"roll": 21},
    {"modifier": 1.5},
])
def test_api_input_validation(tmp_path: Path, payload: dict) -> None:
    with TestClient(create_app(db_path=tmp_path / "test.sqlite3")) as client:
        assert client.post("/api/dc-helper/calculate", json=payload).status_code == 422
