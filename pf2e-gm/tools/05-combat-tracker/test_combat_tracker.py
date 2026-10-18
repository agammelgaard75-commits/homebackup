"""Combat timing, bookkeeping, source import, and restart persistence."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from master.app import create_app


FOLDER = Path(__file__).resolve().parent
spec = spec_from_file_location("combat_state_test", FOLDER / "state.py")
logic = module_from_spec(spec)
spec.loader.exec_module(logic)
API = "/api/combat-tracker"


def command(state, op, **fields):
    return logic.apply(state, {"op": op, **fields})


def test_initiative_sort_ties_manual_order_and_changes():
    state = logic.new_combat("Test")
    logic.add_combatant(state, "Fighter", "PC", 18, 30, 30)
    logic.add_combatant(state, "Spider", "monster", 18, 12, 12)
    logic.add_combatant(state, "Bandit", "NPC", 18, 15, 15)
    logic.add_combatant(state, "Cleric", "PC", 12, 25, 25)
    assert [logic.combatant(state, ident)["name"] for ident in state["order"]] == ["Spider", "Bandit", "Fighter", "Cleric"]
    assert state["active_id"] == state["order"][0]
    state = command(state, "move", combatant_id=1, direction="up")
    assert state["order"][1] == 1
    state = command(state, "set_initiative", combatant_id=4, initiative=20)
    assert state["order"][0] == 4
    assert state["active_id"] == 4
    state = command(state, "next_turn")
    assert state["active_id"] == 2
    state = command(state, "set_initiative", combatant_id=1, initiative=30)
    assert state["active_id"] == 2  # editing another result never interrupts the current turn
    assert state["pending"][1] == 1


def test_turns_rounds_reactions_and_no_round_based_refill():
    state = logic.new_combat("Turns")
    logic.add_combatant(state, "A", "PC", 20, 20, 20)
    logic.add_combatant(state, "B", "monster", 10, 20, 20)
    state = command(state, "actions", combatant_id=1, amount=-2)
    state = command(state, "reaction", combatant_id=1, amount=-1)
    state = command(state, "next_turn")
    assert (state["active_id"], state["round"]) == (2, 1)
    assert logic.combatant(state, 1)["reaction_remaining"] == 0
    state = command(state, "reaction", combatant_id=2, amount=-1)
    state = command(state, "next_turn")
    assert (state["active_id"], state["round"]) == (1, 2)
    assert logic.combatant(state, 1)["actions_remaining"] == 3
    assert logic.combatant(state, 1)["reaction_remaining"] == 1
    assert logic.combatant(state, 2)["reaction_remaining"] == 0  # round changed; B's turn has not begun
    assert logic.combatant(state, 2)["actions_remaining"] == 0
    state = command(state, "reaction", combatant_id=2, amount=1)
    state = command(state, "reaction", combatant_id=2, amount=-1)
    assert logic.combatant(state, 2)["reaction_remaining"] == 0
    state = command(state, "next_turn")
    assert logic.combatant(state, 2)["reaction_remaining"] == 1
    assert logic.combatant(state, 2)["actions_remaining"] == 3


def test_adding_or_reordering_after_action_use_does_not_refill():
    state = logic.new_combat("Mid-turn edit")
    logic.add_combatant(state, "A", "PC", 20)
    state = command(state, "actions", combatant_id=1, amount=-1)
    state = command(state, "reaction", combatant_id=1, amount=-1)
    state = command(state, "add", name="B", type="monster", initiative=30)
    assert state["active_id"] == 1
    assert logic.combatant(state, 1)["actions_remaining"] == 2
    assert logic.combatant(state, 1)["reaction_remaining"] == 0
    state = command(state, "set_initiative", combatant_id=2, initiative=10)
    assert state["active_id"] == 1
    assert logic.combatant(state, 1)["actions_remaining"] == 2


def test_delay_reentry_and_full_round_expiration():
    state = logic.new_combat("Delay")
    for name, initiative in [("A", 30), ("B", 20), ("C", 10)]:
        logic.add_combatant(state, name, "PC", initiative, 10, 10)
    state = command(state, "delay")
    assert state["active_id"] == 2 and state["delayed"] == [1]
    assert logic.combatant(state, 1)["reaction_remaining"] == 0
    with pytest.raises(ValueError):
        command(state, "reaction", combatant_id=1, amount=1)
    state = command(state, "reenter", combatant_id=1, after_id=2)
    assert state["pending"] == [2, 1, 3]
    assert state["order"] == [2, 1, 3]
    state = command(state, "next_turn")
    assert state["active_id"] == 1 and state["round"] == 1
    assert logic.combatant(state, 1)["reaction_remaining"] == 1
    state = command(state, "next_turn")
    state = command(state, "next_turn")
    assert state["round"] == 2 and state["active_id"] == 2

    original = logic.new_combat("No reentry")
    logic.add_combatant(original, "A", "PC", 20)
    logic.add_combatant(original, "B", "PC", 10)
    original = command(original, "delay")
    original = command(original, "next_turn")
    assert original["round"] == 2 and original["delayed"] == []
    assert original["active_id"] == 1  # next turn at original initiative


def test_delayed_last_combatant_can_return_early_next_round():
    state = logic.new_combat("Cross-round delay")
    for name, initiative in [("A", 30), ("B", 20), ("C", 10)]:
        logic.add_combatant(state, name, "PC", initiative)
    state = command(state, "next_turn")
    state = command(state, "next_turn")
    assert state["active_id"] == 3
    state = command(state, "delay")
    assert state["round"] == 2 and state["active_id"] == 1 and state["delayed"] == [3]
    state = command(state, "reenter", combatant_id=3, after_id=1)
    assert state["pending"] == [1, 3, 2]
    state = command(state, "next_turn")
    assert state["active_id"] == 3 and state["round"] == 2
    assert state["delayed"] == []

    other = logic.new_combat("Cross-round expiry")
    for name, initiative in [("A", 30), ("B", 20), ("C", 10)]:
        logic.add_combatant(other, name, "PC", initiative)
    other = command(other, "next_turn")
    other = command(other, "next_turn")
    other = command(other, "delay")
    other = command(other, "next_turn")
    assert other["active_id"] == 2 and other["delayed"] == [3]
    other = command(other, "next_turn")
    assert other["active_id"] == 3 and other["delayed"] == []


def test_ready_map_actions_and_manual_override():
    assert [logic.map_penalty(index) for index in range(4)] == [0, -5, -10, -10]
    assert [logic.map_penalty(index, True) for index in range(4)] == [0, -4, -8, -8]
    state = logic.new_combat("MAP")
    logic.add_combatant(state, "A", "PC", 20)
    logic.add_combatant(state, "B", "NPC", 10)
    state = command(state, "attack", combatant_id=1, amount=1)
    state = command(state, "attack", combatant_id=1, amount=1)
    assert logic.map_penalty(logic.combatant(state, 1)["attack_count"], True) == -8
    state = command(state, "attack", combatant_id=1, amount=-1)
    state = command(state, "actions", combatant_id=1, amount=2)
    assert logic.combatant(state, 1)["actions_remaining"] == 5
    before = state["order"].copy()
    state = command(state, "ready", combatant_id=1)
    assert state["order"] == before and state["active_id"] == 2
    assert logic.combatant(state, 1)["attack_count"] == 0
    with pytest.raises(ValueError):
        command(state, "actions", combatant_id=1, amount=1)


def test_damage_healing_temp_hp_zero_and_notes():
    state = logic.new_combat("HP")
    logic.add_combatant(state, "Hero", "PC", 10, 25, 20)
    state = command(state, "set_hp", combatant_id=1, temp_hp=8)
    state = command(state, "damage", combatant_id=1, amount=5)
    assert (logic.combatant(state, 1)["current_hp"], logic.combatant(state, 1)["temp_hp"]) == (20, 3)
    state = command(state, "damage", combatant_id=1, amount=30)
    assert (logic.combatant(state, 1)["current_hp"], logic.combatant(state, 1)["temp_hp"]) == (0, 0)
    state = command(state, "heal", combatant_id=1, amount=50)
    assert logic.combatant(state, 1)["current_hp"] == 25
    state = command(state, "notes", combatant_id=1, notes="Shield raised")
    state = command(state, "add_effect", combatant_id=1, label="Frightened 1", duration="Until next turn")
    state = command(state, "next_turn")
    assert logic.combatant(state, 1)["effects"] == [{"label": "Frightened 1", "duration": "Until next turn"}]
    state = command(state, "remove_effect", combatant_id=1, effect_index=0)
    assert logic.combatant(state, 1)["effects"] == []
    with pytest.raises(ValueError):
        command(state, "set_hp", combatant_id=1, current_hp=26)
    with pytest.raises(ValueError):
        command(state, "damage", combatant_id=1, amount=-1)
    with pytest.raises(ValueError):
        command(state, "actions", combatant_id=1)


def test_duplicate_creature_names():
    state = logic.new_combat("Names")
    state = command(state, "add", name="Spider", type="monster", quantity=3)
    assert [actor["name"] for actor in state["combatants"]] == ["Spider 1", "Spider 2", "Spider 3"]


def test_adding_after_all_combatants_were_removed_starts_a_turn():
    state = logic.new_combat("Repopulate")
    logic.add_combatant(state, "Old", "PC", 10)
    state = command(state, "next_turn")
    state = command(state, "remove", combatant_id=1)
    assert state["active_id"] is None
    state = command(state, "add", name="New", type="NPC", initiative=12)
    assert state["active_id"] == 2
    assert logic.combatant(state, 2)["actions_remaining"] == 3


def test_api_import_save_restart_end_and_delete(tmp_path):
    path = tmp_path / "combat.sqlite3"
    source = {
        "name": "Web cavern", "party_level": 5, "party_size": 4, "target": "Moderate", "notes": "Original notes",
        "creatures": [{"name": "Spider", "level": 3, "quantity": 3, "notes": "From source", "url": ""}],
    }
    with TestClient(create_app(db_path=path)) as client:
        assert "Combat Tracker" in client.get("/").text
        page = client.get("/tools/combat-tracker")
        assert page.status_code == 200 and "Next Turn" in page.text and "Not implemented yet" not in page.text
        assert client.get("/tools/combat-tracker/app.js").status_code == 200
        assert client.get("/tools/combat-tracker/style.css").status_code == 200
        definition = client.post("/api/encounter-builder/encounters", json=source).json()
        assert client.get(f"{API}/encounter-definitions").json()[0]["id"] == definition["id"]
        created = client.post(f"{API}/combats", json={"source_encounter_id": definition["id"]})
        assert created.status_code == 201
        combat = created.json()
        combat_id = combat["id"]
        assert [actor["name"] for actor in combat["combatants"]] == ["Spider 1", "Spider 2", "Spider 3"]
        assert all(actor["max_hp"] is None and actor["initiative"] is None for actor in combat["combatants"])
        assert client.get(f"{API}/combats").json()[0]["id"] == combat_id
        updated = client.post(f"{API}/combats/{combat_id}/command", json={"op": "set_hp", "combatant_id": 1, "max_hp": 20, "current_hp": 20}).json()
        assert updated["combatants"][0]["current_hp"] == 20
        client.post(f"{API}/combats/{combat_id}/command", json={"op": "set_initiative", "combatant_id": 1, "initiative": 18})
        client.post(f"{API}/combats/{combat_id}/command", json={"op": "actions", "combatant_id": 1, "amount": -1})
        client.post(f"{API}/combats/{combat_id}/command", json={"op": "reaction", "combatant_id": 1, "amount": -1})
        client.post(f"{API}/combats/{combat_id}/command", json={"op": "attack", "combatant_id": 1, "amount": 1})
        client.post(f"{API}/combats/{combat_id}/command", json={"op": "notes", "combatant_id": 1, "notes": "Guarding the web"})
        client.post(f"{API}/combats/{combat_id}/command", json={"op": "add_effect", "combatant_id": 1, "label": "Off-guard", "duration": "Until next turn"})
        updated = client.post(f"{API}/combats/{combat_id}/command", json={"op": "rename_combat", "name": "Web cavern in progress"}).json()
        assert updated["name"] == "Web cavern in progress"
        updated = client.post(f"{API}/combats/{combat_id}/command", json={"op": "end"}).json()
        assert updated["status"] == "ended"
        assert client.post(f"{API}/combats/{combat_id}/command", json={"op": "next_turn"}).status_code == 422
        assert client.get(f"{API}/combats/{combat_id}").status_code == 200
        assert client.get(f"{API}/combats/99999").status_code == 404
        assert client.post(f"{API}/combats", json={"source_encounter_id": 99999}).status_code == 404
        assert client.get(f"{API}/combats/{combat_id}").json()["status"] == "ended"
        assert client.get(f"{API}/combats/{combat_id}").json()["combatants"][0]["current_hp"] == 20
        assert client.get(f"/api/encounter-builder/encounters/{definition['id']}").json() == definition
        empty = client.post(f"{API}/combats", json={"name": "Second combat"})
        assert empty.status_code == 201 and empty.json()["combatants"] == []
        second_id = empty.json()["id"]
    with TestClient(create_app(db_path=path)) as client:
        restored = client.get(f"{API}/combats/{combat_id}").json()
        assert restored["status"] == "ended" and restored["combatants"][0]["current_hp"] == 20
        assert (restored["round"], restored["active_id"], restored["order"][0]) == (1, 1, 1)
        first = restored["combatants"][0]
        assert (first["initiative"], first["actions_remaining"], first["reaction_remaining"], first["attack_count"]) == (18, 2, 0, 1)
        assert first["notes"] == "Guarding the web"
        assert first["effects"] == [{"label": "Off-guard", "duration": "Until next turn"}]
        assert len(client.get(f"{API}/combats").json()) == 2
        assert client.post(f"{API}/combats/{combat_id}/command", json={"op": "resume"}).json()["status"] == "active"
        assert client.delete(f"{API}/combats/{combat_id}").status_code == 204
        assert client.delete(f"{API}/combats/{second_id}").status_code == 204
        assert client.get(f"{API}/combats").json() == []


def test_four_pcs_three_monsters_three_rounds_with_restart(tmp_path):
    path = tmp_path / "three_rounds.sqlite3"
    with TestClient(create_app(db_path=path)) as client:
        combat = client.post(f"{API}/combats", json={"name": "Seven combatants"}).json()
        ident = combat["id"]
        for index in range(4):
            response = client.post(f"{API}/combats/{ident}/command", json={"op": "add", "name": f"PC {index + 1}", "type": "PC", "initiative": 25 - index, "max_hp": 30, "current_hp": 30})
            assert response.status_code == 200
        for index in range(3):
            response = client.post(f"{API}/combats/{ident}/command", json={"op": "add", "name": f"Monster {index + 1}", "type": "monster", "initiative": 15 - index, "max_hp": 20, "current_hp": 20})
            assert response.status_code == 200
        state = response.json()
        assert len(state["order"]) == 7
        turns = []
        for _ in range(21):
            turns.append((state["round"], state["active_id"]))
            state = client.post(f"{API}/combats/{ident}/command", json={"op": "next_turn"}).json()
        assert len({actor for round_no, actor in turns if round_no == 1}) == 7
        assert len({actor for round_no, actor in turns if round_no == 2}) == 7
        assert len({actor for round_no, actor in turns if round_no == 3}) == 7
        assert state["round"] == 4 and state["active_id"] == state["order"][0]
    with TestClient(create_app(db_path=path)) as client:
        restored = client.get(f"{API}/combats/{ident}").json()
        assert restored["round"] == 4 and len(restored["combatants"]) == 7
