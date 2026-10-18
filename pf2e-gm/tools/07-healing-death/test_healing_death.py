"""Phase 7 calculations, source-of-truth integration, and persistence."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from master.app import create_app

HERE = Path(__file__).resolve().parent
spec = spec_from_file_location("healing_rules_tests", HERE / "rules.py")
rules = module_from_spec(spec)
spec.loader.exec_module(rules)


@pytest.mark.parametrize("wounded,critical,nonlethal,expected", [(0,False,False,1),(0,True,False,2),(2,False,False,3),(2,True,False,4),(2,False,True,0)])
def test_knockout_values(wounded,critical,nonlethal,expected):
    assert rules.knockout(wounded,0,critical=critical,nonlethal=nonlethal)["dying"] == expected
    assert rules.knockout(0,0,own_critical_failure=True)["dying"] == 2


def test_recovery_dc_degrees_natural_adjustments_and_boundaries():
    assert rules.recovery(2,0,10)["dc"] == 12
    assert rules.recovery(2,0,10)["dying"] == 3
    assert rules.recovery(2,0,12)["dying"] == 1
    assert rules.recovery(2,0,20)["dying"] == 0  # natural 20 upgrades success
    assert rules.recovery(2,0,1)["dying"] == 4
    assert rules.check_degree(19,3,12) == "critical_success"  # exactly DC+10
    assert rules.check_degree(10,-8,12) == "critical_failure"  # exactly DC-10
    assert rules.check_degree(20,-12,18) == "failure"  # natural 20 is not always critical
    assert rules.check_degree(1,30,20) == "success"  # natural 1 lowers critical success
    with pytest.raises(ValueError): rules.check_degree(0,0,10)


def test_dying_damage_doomed_first_aid_and_death_threshold():
    assert rules.damage_while_dying(2,0)["dying"] == 3
    assert rules.damage_while_dying(2,0,critical=True)["dying"] == 4
    assert rules.damage_while_dying(2,0,own_critical_failure=True)["dying"] == 4
    assert rules.death_threshold(1) == 3
    assert rules.knockout(2,1)["fatal"]
    assert rules.first_aid(2,0,"success")["dc"] == 17
    assert rules.first_aid(2,0,"critical_success")["dying"] == 0
    assert rules.first_aid(2,0,"failure")["dying"] == 2
    assert rules.first_aid(2,0,"critical_failure")["dying"] == 3


@pytest.mark.parametrize("dc,rank,bonus", [(15,"trained",0),(20,"expert",10),(30,"master",30),(40,"legendary",50)])
def test_all_treat_wounds_options(dc,rank,bonus):
    assert rules.treatment_option(rank,dc)["bonus"] == bonus
    assert rules.treatment(rank,dc,"success",9,"treat")["amount"] == 9+bonus
    assert rules.treatment(rank,dc,"critical_success",18,"treat")["amount"] == 18+bonus
    assert rules.treatment(rank,dc,"critical_failure",5,"treat")["hp_change"] == -5
    assert rules.treatment(rank,dc,"failure",None,"treat")["hp_change"] == 0
    if dc>15:
        with pytest.raises(ValueError): rules.treatment_option("trained",dc)


def test_treat_wounds_continuation_and_battle_difference():
    assert rules.treatment("expert",20,"success",8,"treat",True)["amount"] == 36
    assert rules.treatment("expert",20,"critical_success",18,"treat",True)["amount"] == 56
    battle = rules.treatment("expert",20,"success",8,"battle")
    assert battle["amount"] == 18 and battle["immunity_minutes"] == 1440
    assert not battle["removes_wounded_if_hp_restored"]
    with pytest.raises(ValueError): rules.treatment("expert",20,"failure",None,"treat",True)
    with pytest.raises(ValueError): rules.treatment("expert",20,"success",17,"treat")


@pytest.fixture
def client(tmp_path):
    path = tmp_path / "healing.sqlite3"
    with TestClient(create_app(db_path=path)) as test_client:
        yield test_client,path


def new_subject(client,hp=20,maximum=30,hero=0):
    response=client.post("/api/healing-death/subjects",json={"name":"Patient","current_hp":hp,"max_hp":maximum,"hero_points":hero})
    assert response.status_code==201,response.text
    return {"subject_id":response.json()["id"]}


def status(client,target):
    response=client.get("/api/healing-death/status",params=target)
    assert response.status_code==200,response.text
    return response.json()


def apply(client,target,action,**extra):
    response=client.post("/api/healing-death/apply",json={**target,"action":action,**extra})
    assert response.status_code==200,response.text
    return response.json()


def condition_value(client,target,slug):
    data=client.get("/api/conditions/active",params=target).json()
    return next((row["value"] or 1 for row in data["visible"] if row["slug"]==slug and not row["overridden"]),0)


def test_knockout_wounded_doomed_and_condition_sync(client):
    c,_=client;t=new_subject(c,hp=8,hero=1)
    apply(c,t,"manual_status",status_slug="wounded",status_value=2)
    plan=c.post("/api/healing-death/preview",json={**t,"action":"knockout"}).json()
    assert (plan["dying"],plan["current_hp"],plan["fatal"])==(3,0,False)
    assert status(c,t)["current_hp"]==8  # preview did not apply
    result=apply(c,t,"knockout")
    assert result["status"]["dying"]==3
    assert condition_value(c,t,"dying")==3
    assert condition_value(c,t,"unconscious")==1  # derived by Conditions Tracker
    assert apply(c,t,"manual_status",status_slug="doomed",status_value=1)["status"]["at_death_threshold"]
    assert condition_value(c,t,"wounded")==2


def test_nonlethal_recovery_hero_exception_and_stabilize(client):
    c,_=client;t=new_subject(c,hp=6,hero=2)
    apply(c,t,"manual_status",status_slug="wounded",status_value=2)
    apply(c,t,"knockout",nonlethal=True)
    assert (status(c,t)["dying"],status(c,t)["unconscious"])==(0,1)
    apply(c,t,"manual_hp",current_hp=6,max_hp=30,temp_hp=0)
    apply(c,t,"knockout")
    assert status(c,t)["dying"]==3
    hero=apply(c,t,"dying_damage",use_hero_points=True)["status"]
    assert (hero["dying"],hero["wounded"],hero["hero_points"],hero["current_hp"])==(0,2,0,0)
    apply(c,t,"manual_status",status_slug="dying",status_value=2)
    aid=apply(c,t,"stabilize",manual_degree="success")["status"]
    assert (aid["dying"],aid["wounded"],aid["unconscious"])==(0,3,1)
    assert condition_value(c,t,"wounded")==3


def test_recovery_after_restart_and_damage_no_extra_wounded(client):
    c,path=client;t=new_subject(c,hp=0)
    apply(c,t,"manual_status",status_slug="dying",status_value=2)
    apply(c,t,"manual_status",status_slug="wounded",status_value=2)
    assert apply(c,t,"recovery",roll=10)["status"]["dying"]==3
    with TestClient(create_app(db_path=path)) as restarted:
        assert status(restarted,t)["dying"]==3
        result=apply(restarted,t,"dying_damage")["status"]
        assert (result["dying"],result["wounded"],result["at_death_threshold"])==(4,2,True)


def test_treat_wounds_immunity_clock_wounded_and_battle_medicine(client):
    c,path=client;t=new_subject(c,hp=1,maximum=80)
    apply(c,t,"manual_status",status_slug="wounded",status_value=1)
    base={"action":"treatment","healer":"Mira","proficiency":"expert","dc":20,"manual_degree":"success","dice_total":8}
    treated=apply(c,t,**base,status_slug="treat")["status"]
    assert (treated["current_hp"],treated["wounded"],treated["treat_immune_until"],treated["game_minutes"])==(19,0,60,10)
    assert c.post("/api/healing-death/apply",json={**t,**base,"status_slug":"treat"}).status_code==422
    battle=apply(c,t,**base,status_slug="battle",has_battle_medicine=True)["status"]
    assert len(battle["treatments"])==2
    assert battle["treatments"][0]["immunity_until_minute"]==1450
    assert c.post("/api/healing-death/apply",json={**t,**base,"status_slug":"battle","has_battle_medicine":True}).status_code==422
    assert apply(c,t,**{**base,"healer":"Jon"},status_slug="battle",has_battle_medicine=True)["status"]["current_hp"]>battle["current_hp"]
    with TestClient(create_app(db_path=path)) as restarted:
        persisted=status(restarted,t)
        assert persisted["game_minutes"]==10 and len(persisted["treatments"])==3
        restarted.post("/api/healing-death/time",json={**t,"minutes":60})
        assert status(restarted,t)["treat_eligible"]
        assert apply(restarted,t,**base,status_slug="treat")["status"]["game_minutes"]==80


def test_battle_medicine_does_not_remove_wounded_or_treat_immunity(client):
    c,_=client;t=new_subject(c,hp=5,maximum=60)
    apply(c,t,"manual_status",status_slug="wounded",status_value=2)
    battle=apply(c,t,"treatment",status_slug="battle",healer="Mira",proficiency="expert",dc=20,
                 manual_degree="critical_success",dice_total=18,has_battle_medicine=True)["status"]
    assert battle["current_hp"]==33 and battle["wounded"]==2 and battle["treat_eligible"]
    assert c.post("/api/healing-death/apply",json={**t,"action":"treatment","status_slug":"battle","healer":"No feat","proficiency":"trained","dc":15,"manual_degree":"failure","has_battle_medicine":False}).status_code==422


def test_full_hp_rest_and_other_healing_do_not_immediately_remove_wounded(client):
    c,_=client;t=new_subject(c,hp=10,maximum=20)
    apply(c,t,"manual_status",status_slug="wounded",status_value=1)
    healed=apply(c,t,"manual_heal",amount=10)["status"]
    assert healed["wounded"]==1 and healed["current_hp"]==20
    assert c.post("/api/healing-death/apply",json={**t,"action":"rest_full_hp"}).status_code==422
    c.post("/api/healing-death/time",json={**t,"minutes":10})
    assert apply(c,t,"rest_full_hp")["status"]["wounded"]==0


def test_temp_hp_edit_does_not_restart_full_hp_rest_clock(client):
    c,_=client;t=new_subject(c,hp=20,maximum=20)
    apply(c,t,"manual_status",status_slug="wounded",status_value=1)
    c.post("/api/healing-death/time",json={**t,"minutes":7})
    apply(c,t,"manual_hp",current_hp=20,max_hp=20,temp_hp=5)
    c.post("/api/healing-death/time",json={**t,"minutes":3})
    assert apply(c,t,"rest_full_hp")["status"]["wounded"]==0


def test_combat_hp_and_initiative_stay_in_sync(client):
    c,_=client
    combat=c.post("/api/combat-tracker/combats",json={"name":"Ambush"}).json()
    combat_id=combat["id"]
    for name,kind,initiative in [("Goblin","monster",18),("Hero","PC",12)]:
        c.post(f"/api/combat-tracker/combats/{combat_id}/command",json={"op":"add","name":name,"type":kind,"initiative":initiative,"max_hp":20,"current_hp":10})
    t={"combat_id":combat_id,"combatant_id":2}
    assert status(c,t)["current_hp"]==10
    result=apply(c,t,"knockout",move_initiative=True)
    assert result["result"]["initiative_moved"]
    state=c.get(f"/api/combat-tracker/combats/{combat_id}").json()
    assert state["order"]==[2,1] and state["combatants"][1]["current_hp"]==0
    assert condition_value(c,t,"dying")==1
    reminder=c.get(f"/api/healing-death/combat/{combat_id}/reminders",params={"actor_id":2}).json()
    assert reminder[0]["dc"]==11
    healed=apply(c,t,"manual_heal",amount=5)["status"]
    assert healed["dying"]==0 and healed["wounded"]==1
    assert c.get(f"/api/combat-tracker/combats/{combat_id}").json()["combatants"][1]["current_hp"]==5


def test_immunity_override_requires_reason(client):
    c,_=client;t=new_subject(c,hp=5)
    data={"action":"treatment","status_slug":"treat","healer":"A","proficiency":"trained","dc":15,"manual_degree":"failure"}
    apply(c,t,**data)
    assert c.post("/api/healing-death/apply",json={**t,**data,"override_immunity":True}).status_code==422
    assert apply(c,t,**data,override_immunity=True,override_note="Continual Recovery")["status"]["treatments"][0]["override_note"]=="Continual Recovery"
