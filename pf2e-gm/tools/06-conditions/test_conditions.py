"""Phase 6 rules, persistence, reminders, and Phase 5 integration tests."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from master.app import create_app

HERE = Path(__file__).resolve().parent


def module(name):
    spec = spec_from_file_location(f"test_conditions_{name}", HERE / f"{name}.py")
    result = module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


logic = module("logic")
library = module("library")


def sample(slug, ident=1, value=None, **extra):
    return {"id": ident, "slug": slug, "value": value, "damage_type": "", "damage_expression": "",
            "recovery_dc": 15, "duration_kind": "manual", "controller_id": None,
            "duration_event": "end", "rounds_remaining": None, "quickened_restriction": "", **extra}


def test_library_priority_and_verified_links():
    priority = "frightened sickened clumsy enfeebled drained stupefied off-guard prone grabbed restrained immobilized blinded dazzled concealed hidden slowed stunned quickened persistent-damage fatigued".split()
    assert len(library.LIBRARY) >= 35
    for slug in priority:
        row = library.LIBRARY[slug]
        assert row["source_book"] == "Player Core"
        assert 442 <= row["source_page"] <= 447
        assert row["source_url"].startswith("https://2e.aonprd.com/Conditions.aspx?ID=")
        assert row["summary"] and row["effects"] and row["ending"]


def test_grabbed_restrained_prone_and_independent_source():
    rows = [sample("grabbed"), sample("off-guard", 2)]
    current = {row["slug"]: row for row in logic.visible(rows)}
    assert current["off-guard"]["source_ids"] == [2]
    assert current["immobilized"]["implied_by"] == ["grabbed"]
    assert {row["slug"] for row in logic.visible(rows[1:])} == {"off-guard"}
    current = {row["slug"]: row for row in logic.visible(rows + [sample("restrained", 3)])}
    assert current["grabbed"]["overridden"]
    assert "restrained" in current["off-guard"]["implied_by"]
    assert logic.penalty_summary([sample("prone")])["attack_circumstance"] == -2
    assert logic.penalty_summary([sample("prone")])["ac_circumstance"] == -2
    assert {row["slug"]: row for row in logic.visible([sample("dazzled"), sample("blinded",2)])}["dazzled"]["overridden"]
    assert {row["slug"]: row for row in logic.visible([sample("encumbered")])}["clumsy"]["value"] == 1


def test_values_penalty_stacking_and_action_guidance():
    rows = [sample("frightened", 1, 2), sample("frightened", 2, 1), sample("sickened", 3, 1),
            sample("clumsy", 4, 3), sample("off-guard", 5)]
    assert {row["slug"]: row for row in logic.visible(rows)}["frightened"]["value"] == 2
    penalties = logic.penalty_summary(rows)
    assert penalties["all_checks_and_dcs_status"] == -2
    assert penalties["ac_status"] == -3
    assert penalties["ac_circumstance"] == -2
    assert penalties["reflex_status"] == -3
    reduced = logic.reduce_all_sources(rows, "frightened")
    assert [row["value"] for row in reduced if row["slug"] == "frightened"] == [1, 0]
    actions = logic.action_guidance([sample("slowed", 1, 2), sample("stunned", 2, 1),
                                     sample("quickened", 3), sample("quickened", 4)])
    assert (actions["normal_actions"], actions["quickened_extra"], actions["total_guidance"]) == (1, 1, 2)
    assert logic.action_guidance([sample("slowed", 1, 2), sample("stunned", 2, 1)])["normal_actions"] == 1
    assert logic.action_guidance([sample("stunned", 1, None, duration_kind="custom")])["total_guidance"] == 0
    assert logic.action_guidance([sample("stunned", 1, 4), sample("quickened", 2)])["total_guidance"] == 0
    prompts = logic.reminders([sample("stunned", 1, 1), sample("slowed", 2, 2)], "start", 4, 4)
    assert next(row for row in prompts if row["kind"] == "stunned_reduce")["amount"] == 1


def test_turn_timing_and_persistent_overlap():
    rows = [sample("frightened", 1, 2), sample("persistent-damage", 2, damage_type="fire", damage_expression="1d6"),
            sample("persistent-damage", 3, damage_type="fire", damage_expression="4"),
            sample("prone", 4, duration_kind="start_turn", controller_id=8),
            sample("grabbed", 5, duration_kind="rounds", controller_id=8, duration_event="end", rounds_remaining=2)]
    own_end = logic.reminders(rows, "end", 7, 7)
    assert [row["kind"] for row in own_end].count("persistent_choice") == 1
    assert any(row["kind"] == "reduce" for row in own_end)
    assert not any(row["kind"] == "reduce" for row in logic.reminders(rows, "end", 8, 7))
    assert any(row["kind"] == "expiration" for row in logic.reminders(rows, "start", 8, 7))
    assert any(row["kind"] == "round" for row in logic.reminders(rows, "end", 8, 7))
    assert len(logic.upcoming(rows)) == 2
    overlap = logic.persistent_groups(rows)[0]
    assert overlap["gm_choice_needed"] and overlap["active_expression"] is None
    fixed = logic.persistent_groups([sample("persistent-damage", 1, damage_type="fire", damage_expression="2"), sample("persistent-damage", 2, damage_type="fire", damage_expression="5")])[0]
    assert fixed["active_expression"] == "5"


@pytest.fixture
def client(tmp_path):
    path = tmp_path / "conditions.sqlite3"
    with TestClient(create_app(db_path=path)) as test_client:
        yield test_client, path


def combatant(client):
    combat = client.post("/api/combat-tracker/combats", json={"name": "Test battle"}).json()
    result = client.post(f"/api/combat-tracker/combats/{combat['id']}/command",
                         json={"op": "add", "name": "Hero", "type": "PC", "max_hp": 20, "current_hp": 20})
    assert result.status_code == 200
    return combat["id"], result.json()["combatants"][0]["id"]


def active(client, combat_id, actor_id):
    response = client.get("/api/conditions/active", params={"combat_id": combat_id, "combatant_id": actor_id})
    assert response.status_code == 200
    return response.json()


def add(client, combat_id, actor_id, slug, **extra):
    response = client.post("/api/conditions/active", json={"combat_id": combat_id, "combatant_id": actor_id, "slug": slug, **extra})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_api_frightened_edit_sources_and_combat_integration(client):
    c, _ = client
    combat_id, actor_id = combatant(c)
    first = add(c, combat_id, actor_id, "frightened", value=2, source="Dragon", notes="Fear aura",
                duration_kind="end_turn", controller_id=actor_id)
    second = add(c, combat_id, actor_id, "frightened", value=1, source="Spell")
    assert len(active(c, combat_id, actor_id)["instances"]) == 2
    assert add(c, combat_id, actor_id, "frightened", value=2, source="Dragon") == first  # deduplicate one source
    assert c.patch(f"/api/conditions/active/{second}", json={"value": 3}).status_code == 200
    assert active(c, combat_id, actor_id)["visible"][0]["value"] == 3
    summary = c.get(f"/api/conditions/combat/{combat_id}/summary").json()
    assert summary[str(actor_id)]["visible"][0]["value"] == 3
    prompts = c.get("/api/conditions/reminders", params={"combat_id": combat_id, "combatant_id": actor_id, "event": "end", "actor_id": actor_id}).json()
    assert any(p["kind"] == "reduce" for p in prompts)
    assert sum(p["kind"] == "reduce" for p in prompts) == 1
    assert len(active(c, combat_id, actor_id)["instances"]) == 2  # reminder did not mutate
    c.post(f"/api/conditions/active/{first}/reduce", json={"amount": 1})
    assert [row["value"] for row in active(c, combat_id, actor_id)["instances"]] == [1, 2]
    c.post(f"/api/conditions/active/{first}/reduce", json={"amount": 1})
    assert [row["value"] for row in active(c, combat_id, actor_id)["instances"]] == [1]
    c.post(f"/api/conditions/active/{second}/reduce", json={"amount": 1})
    assert not active(c, combat_id, actor_id)["instances"]


def test_api_grabbed_prone_and_persistent_damage(client):
    c, _ = client
    combat_id, actor_id = combatant(c)
    independent = add(c, combat_id, actor_id, "off-guard", source="Flank")
    grabbed = add(c, combat_id, actor_id, "grabbed", source="Spider")
    assert {row["slug"] for row in active(c, combat_id, actor_id)["visible"]} == {"off-guard", "grabbed", "immobilized"}
    restrained = add(c, combat_id, actor_id, "restrained", source="Web")
    assert next(row for row in active(c, combat_id, actor_id)["visible"] if row["slug"] == "grabbed")["overridden"]
    c.delete(f"/api/conditions/active/{restrained}")
    c.delete(f"/api/conditions/active/{grabbed}")
    assert [row["slug"] for row in active(c, combat_id, actor_id)["visible"]] == ["off-guard"]
    assert active(c, combat_id, actor_id)["instances"][0]["id"] == independent
    damage = add(c, combat_id, actor_id, "persistent-damage", source="Flame", damage_type="fire", damage_expression="1d6", duration_kind="recovery")
    prompts = c.get("/api/conditions/reminders", params={"combat_id":combat_id,"combatant_id":actor_id,"event":"end","actor_id":actor_id}).json()
    assert any("1d6" in row["text"] and "DC 15" in row["text"] for row in prompts)
    assert c.post(f"/api/conditions/active/{damage}/recovery", json={"success":False,"roll":4}).json()["removed"] is False
    assert active(c, combat_id, actor_id)["instances"][-1]["recovery_log"][0]["roll"] == 4
    assert c.post(f"/api/conditions/active/{damage}/recovery", json={"success":True,"roll":18}).json()["removed"] is True
    assert all(row["slug"] != "persistent-damage" for row in active(c, combat_id, actor_id)["instances"])
    history = c.get("/api/conditions/recovery-history",params={"combat_id":combat_id,"combatant_id":actor_id}).json()
    assert [row["success"] for row in history[0]["checks"]] == [False, True]


def test_duration_and_restart(client):
    c, path = client
    combat_id, actor_id = combatant(c)
    ident = add(c, combat_id, actor_id, "prone", source="Trip", notes="From giant", duration_kind="rounds",
                controller_id=actor_id, duration_event="start", rounds_remaining=2)
    add(c, combat_id, actor_id, "quickened", source="Spell", quickened_restriction="Stride")
    before = active(c, combat_id, actor_id)
    assert any(row["kind"] == "round" for row in c.get("/api/conditions/reminders", params={"combat_id":combat_id,"combatant_id":actor_id,"event":"start","actor_id":actor_id}).json())
    with TestClient(create_app(db_path=path)) as restarted:
        after = active(restarted, combat_id, actor_id)
        assert after["instances"] == before["instances"]
        assert restarted.get(f"/api/conditions/combat/{combat_id}/summary").json()[str(actor_id)]["visible"]
        assert restarted.patch(f"/api/conditions/active/{ident}", json={"rounds_remaining":1}).status_code == 200


def test_standalone_validation_and_cleanup(client):
    c, _ = client
    subject = c.post("/api/conditions/subjects", json={"name":"Temporary hero"}).json()["id"]
    assert c.post("/api/conditions/active", json={"subject_id":subject,"slug":"sickened","value":1}).status_code == 201
    assert c.get("/api/conditions/active",params={"subject_id":subject}).json()["visible"][0]["value"] == 1
    assert c.post("/api/conditions/active",json={"subject_id":subject,"slug":"frightened"}).status_code == 422
    assert c.post("/api/conditions/active",json={"subject_id":subject,"slug":"prone","value":1}).status_code == 422
    assert c.post("/api/conditions/active",json={"subject_id":subject,"slug":"persistent-damage","damage_type":"fire","damage_expression":"bad dice"}).status_code == 422
    assert c.delete(f"/api/conditions/subjects/{subject}").status_code == 204
    combat_id, actor_id = combatant(c)
    add(c,combat_id,actor_id,"prone")
    assert c.post(f"/api/combat-tracker/combats/{combat_id}/command",json={"op":"remove","combatant_id":actor_id}).status_code == 200
    assert c.get(f"/api/conditions/combat/{combat_id}/summary").json() == {}


def test_multiple_turns_keep_reminders_manual(client):
    c, _ = client
    combat_id, actor_id = combatant(c)
    opponent = c.post(f"/api/combat-tracker/combats/{combat_id}/command",
                      json={"op":"add","name":"Spider","type":"monster","initiative":1}).json()["combatants"][-1]["id"]
    frightened = add(c, combat_id, actor_id, "frightened", value=2, source="Fear")
    add(c, combat_id, actor_id, "slowed", value=2, source="Magic")
    add(c, combat_id, actor_id, "stunned", value=1, source="Blow")
    fire = add(c, combat_id, actor_id, "persistent-damage", damage_type="fire", damage_expression="1d6", source="Flames")
    assert active(c, combat_id, actor_id)["actions"]["normal_actions"] == 1
    for turn in range(3):
        state = c.get(f"/api/combat-tracker/combats/{combat_id}").json()
        if state["active_id"] != actor_id:
            c.post(f"/api/combat-tracker/combats/{combat_id}/command",json={"op":"next_turn"})
        prompts = c.get("/api/conditions/reminders",params={"combat_id":combat_id,"combatant_id":actor_id,"event":"end","actor_id":actor_id}).json()
        assert any(row["kind"] == "persistent" for row in prompts)
        if turn < 2:
            assert any(row["kind"] == "reduce" for row in prompts)
            c.post(f"/api/conditions/active/{frightened}/reduce",json={"amount":1})
        else:
            assert not any(row["kind"] == "reduce" for row in prompts)
        assert any(row["id"] == fire for row in active(c,combat_id,actor_id)["instances"])
        c.post(f"/api/combat-tracker/combats/{combat_id}/command",json={"op":"next_turn"})
        state = c.get(f"/api/combat-tracker/combats/{combat_id}").json()
        assert state["active_id"] == opponent
        c.post(f"/api/combat-tracker/combats/{combat_id}/command",json={"op":"next_turn"})
    state = c.get(f"/api/combat-tracker/combats/{combat_id}").json()
    assert state["round"] >= 4
    assert not any(row["slug"] == "frightened" for row in active(c,combat_id,actor_id)["instances"])


def test_round_duration_counts_on_controller_turn_and_stays_at_zero(client):
    c, path = client
    combat_id, hero_id = combatant(c)
    c.post(f"/api/combat-tracker/combats/{combat_id}/command",
           json={"op": "set_initiative", "combatant_id": hero_id, "initiative": 10})
    opponent = c.post(f"/api/combat-tracker/combats/{combat_id}/command",
                      json={"op": "add", "name": "Spider", "type": "monster", "initiative": 1}).json()["combatants"][-1]["id"]
    condition_id = add(c, combat_id, hero_id, "blinded", source="Spell", duration_kind="rounds",
                       controller_id=hero_id, duration_event="end", rounds_remaining=3)
    add(c, combat_id, hero_id, "dazzled", source="Web", duration_kind="rounds",
        controller_id=opponent, duration_event="start", rounds_remaining=2)
    add(c, combat_id, hero_id, "blinded", source="Other spell", duration_kind="rounds",
        controller_id=opponent, duration_event="end", rounds_remaining=5)
    add(c, combat_id, hero_id, "blinded", source="Ongoing curse")

    def rounds(slug, source):
        return next(row["rounds_remaining"] for row in active(c, combat_id, hero_id)["instances"]
                    if row["slug"] == slug and row["source"] == source)

    summary = c.get(f"/api/conditions/combat/{combat_id}/summary").json()[str(hero_id)]
    blinded = next(row for row in summary["visible"] if row["slug"] == "blinded")
    assert blinded["round_counts"] == [3, 5]
    assert blinded["other_duration_sources"] == 1
    assert rounds("blinded", "Spell") == 3
    # Hero end and Spider start each tick their own controlled durations once.
    c.post(f"/api/combat-tracker/combats/{combat_id}/command", json={"op": "next_turn"})
    assert (rounds("blinded", "Spell"), rounds("dazzled", "Web"), rounds("blinded", "Other spell")) == (2, 1, 5)
    c.post(f"/api/combat-tracker/combats/{combat_id}/command", json={"op": "next_turn"})
    assert (rounds("blinded", "Spell"), rounds("dazzled", "Web"), rounds("blinded", "Other spell")) == (2, 1, 4)
    assert c.post(f"/api/combat-tracker/combats/{combat_id}/command", json={"op":"actions","combatant_id":hero_id,"amount":99}).status_code == 422
    assert rounds("blinded", "Spell") == 2
    for _ in range(4):
        c.post(f"/api/combat-tracker/combats/{combat_id}/command", json={"op": "next_turn"})
    assert rounds("blinded", "Spell") == 0
    assert rounds("dazzled", "Web") == 0
    zero = c.get(f"/api/conditions/combat/{combat_id}/summary").json()[str(hero_id)]["zero_rounds"]
    assert {row["slug"] for row in zero} == {"blinded", "dazzled"}
    assert next(row for row in zero if row["instance_id"] == condition_id)["source"] == "Spell"
    assert all(row["kind"] == "round_expired" and "0 rounds" in row["text"] for row in zero)
    for _ in range(4):
        c.post(f"/api/combat-tracker/combats/{combat_id}/command", json={"op": "next_turn"})
    assert rounds("blinded", "Spell") == 0
    assert rounds("dazzled", "Web") == 0
    assert any(row["id"] == condition_id for row in active(c, combat_id, hero_id)["instances"])
    assert not any(row["kind"] == "round" and row["instance_id"] == condition_id
                   for row in c.get("/api/conditions/reminders", params={"combat_id":combat_id,"combatant_id":hero_id,
                                                                          "event":"end","actor_id":hero_id}).json())
    with TestClient(create_app(db_path=path)) as restarted:
        assert next(row["rounds_remaining"] for row in active(restarted, combat_id, hero_id)["instances"]
                    if row["id"] == condition_id) == 0
        persisted = restarted.get(f"/api/conditions/combat/{combat_id}/summary").json()[str(hero_id)]["zero_rounds"]
        assert any(row["instance_id"] == condition_id for row in persisted)
        assert restarted.delete(f"/api/conditions/active/{condition_id}").status_code == 204
        assert not any(row["instance_id"] == condition_id for row in restarted.get(
            f"/api/conditions/combat/{combat_id}/summary").json()[str(hero_id)]["zero_rounds"])


def test_combat_reminders_are_presented_on_combatants(client):
    c, _ = client
    page = c.get("/tools/combat-tracker").text
    script = c.get("/tools/combat-tracker/app.js").text
    assert 'id="condition-reminders"' not in page
    assert "Turn reminders appear on the affected combatant" in page
    assert 'reminders.dataset.combatantId = String(id)' in script
    assert "conditionSummary[String(item.id)]?.zero_rounds" in script
    assert "Remove condition source" in script


def test_standalone_round_counter_can_be_set_to_zero(client):
    c, _ = client
    subject = c.post("/api/conditions/subjects", json={"name":"Scout"}).json()["id"]
    row = c.post("/api/conditions/active", json={"subject_id":subject,"slug":"blinded",
                   "duration_kind":"rounds","controller_id":subject,"rounds_remaining":1})
    assert row.status_code == 201, row.text
    ident = row.json()["id"]
    assert c.patch(f"/api/conditions/active/{ident}", json={"rounds_remaining":0}).status_code == 200
    current = c.get("/api/conditions/active", params={"subject_id":subject}).json()
    assert current["instances"][0]["rounds_remaining"] == 0
    assert current["visible"][0]["round_counts"] == [0]
