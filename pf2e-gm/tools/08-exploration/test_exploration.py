"""Phase 8 travel, persistence, shared-clock, and combat handoff tests."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from master.app import create_app
from shared.database.storage import connect

HERE=Path(__file__).resolve().parent
spec=spec_from_file_location('exploration_rules_tests',HERE/'rules.py')
rules=module_from_spec(spec);spec.loader.exec_module(rules)


def member(ident=1,activity='normal',speed=25,con=0,**extra):
    return dict(dict(id=ident,name=f'PC {ident}',activity=activity,speed=speed,con_modifier=con,
                     skill='',expert_rank='',expert_id=None),**extra)


def test_activity_library_verified_scout_avoid_defend_and_limits():
    entries={x['slug']:x for x in rules.library()}
    assert len(entries)==12
    assert entries['scout']['page']==439 and '+1 circumstance' in entries['scout']['encounter']
    assert entries['avoid']['page']==438 and 'Stealth' in entries['avoid']['encounter']
    assert 'Half' in entries['defend']['movement']
    assert '150 ft/min' in entries['search']['movement']
    assert entries['custom']['page'] is None


def test_scout_avoid_travel_and_terrain():
    normal=rules.travel([member()],minutes=1)
    assert normal['party_fpm']==250 and normal['distance_feet']==250
    assert rules.travel([member(activity='scout')],minutes=1)['party_fpm']==125
    assert rules.travel([member(activity='avoid')],minutes=1)['party_fpm']==125
    assert rules.travel([member()],terrain='difficult',minutes=1)['party_fpm']==125
    assert rules.travel([member()],terrain='greater',minutes=3)['distance_feet']==250


def test_party_slowest_search_detect_caps_and_manual_override():
    group=[member(1,speed=40),member(2,activity='scout',speed=25)]
    assert rules.travel(group)['party_fpm']==125
    assert rules.travel([member(activity='search',speed=100)],search_mode='before')['party_fpm']==150
    assert rules.travel([member(activity='detect',speed=100)],detect_mode='auras')['party_fpm']==300
    assert rules.travel(group,override_fpm=200)['party_fpm']==200
    assert rules.travel([member(activity='track')])['party_fpm'] is None
    assert rules.travel([member(activity='track')],override_fpm=75)['party_fpm']==75


def test_hustle_limit_group_lowest_and_follow_expert():
    group=[member(1,activity='hustle',con=3),member(2,activity='hustle',con=1)]
    result=rules.travel(group,minutes=20)
    assert result['party_fpm']==500 and result['group_hustle_limit_minutes']==10
    assert result['warnings']
    assert rules.hustle_limit(-2)==10
    leader=member(1,activity='avoid',expert_rank='expert')
    follower=member(2,activity='follow',expert_id=1,skill='Stealth')
    assert rules.travel([leader,follower])['party_fpm']==125
    with pytest.raises(ValueError):rules.travel([member(activity='follow')])


def test_encounter_scout_party_bonus_and_three_reminders():
    party=[member(1,activity='scout'),member(2,activity='defend'),member(3,activity='avoid'),member(4)]
    reminders=rules.encounter_reminders(party)
    assert sum('+1 circumstance' in text for text in reminders)==1
    assert any('shield' in text for text in reminders)
    assert any('Stealth for initiative' in text for text in reminders)
    assert not any('undetected' in text for text in reminders)


@pytest.fixture
def client(tmp_path):
    path=tmp_path/'exploration.sqlite3'
    with TestClient(create_app(db_path=path)) as c:yield c,path


def new_session(c,**data):
    response=c.post('/api/exploration/sessions',json={'name':'Ruins',**data})
    assert response.status_code==201,response.text
    return response.json()['id']


def add(c,sid,name,activity='normal',speed=25,con=0):
    r=c.post(f'/api/exploration/sessions/{sid}/members',json={'name':name,'activity':activity,'speed':speed,'con_modifier':con})
    assert r.status_code==201,r.text
    return r.json()['id']


def test_session_members_activity_notes_log_and_restart(client):
    c,path=client;sid=new_session(c)
    mid=add(c,sid,'Amiri')
    changed=c.patch(f'/api/exploration/sessions/{sid}/members/{mid}',json={'activity':'avoid','notes':'Watch the corridor','skill':'Stealth','speed':30})
    assert changed.status_code==200
    assert changed.json()['members'][0]['activity']=='avoid'
    assert c.post(f'/api/exploration/sessions/{sid}/log',json={'event':'Secret door','note':'Behind statue'}).status_code==201
    with TestClient(create_app(db_path=path)) as restarted:
        saved=restarted.get(f'/api/exploration/sessions/{sid}').json()
        assert saved['members'][0]['notes']=='Watch the corridor'
        assert saved['log'][0]['event']=='Secret door'
        assert restarted.post(f'/api/exploration/sessions/{sid}/travel',json={'minutes':1}).json()['party_fpm']==150
        assert restarted.delete(f'/api/exploration/sessions/{sid}/members/{mid}').status_code==204
        assert restarted.get(f'/api/exploration/sessions/{sid}').json()['members']==[]


def test_shared_combat_clock_and_healing_after_restart(client):
    c,path=client
    combat=c.post('/api/combat-tracker/combats',json={'name':'Party'}).json();cid=combat['id']
    hero=c.post(f'/api/combat-tracker/combats/{cid}/command',json={'op':'add','name':'Hero','type':'PC','max_hp':20,'current_hp':20}).json()['combatants'][0]
    sid=new_session(c,linked_combat_id=cid)
    assert c.post(f'/api/exploration/sessions/{sid}/import-pcs').json()['added']==1
    assert c.post(f'/api/exploration/sessions/{sid}/import-pcs').json()['added']==0
    c.post(f'/api/exploration/sessions/{sid}/clock',json={'minutes':30})
    target={'combat_id':cid,'combatant_id':hero['id']}
    assert c.get('/api/healing-death/status',params=target).json()['game_minutes']==30
    with TestClient(create_app(db_path=path)) as restarted:
        assert restarted.get(f'/api/exploration/sessions/{sid}').json()['game_minutes']==30
        assert restarted.get('/api/healing-death/status',params=target).json()['game_minutes']==30
        restarted.post(f'/api/exploration/sessions/{sid}/clock',json={'minutes':12,'correction':True})
        assert restarted.get('/api/healing-death/status',params=target).json()['game_minutes']==12
        assert restarted.get(f'/api/exploration/sessions/{sid}').json()['log'][0]['event']=='Game time corrected'


def test_party_name_and_combat_transition_read_only(client):
    c,path=client
    with connect(path) as db:
        campaign=db.execute("INSERT INTO campaigns(name) VALUES ('Quest')").lastrowid
        party=db.execute("INSERT INTO parties(campaign_id,name) VALUES (?,?)",(campaign,'Heroes')).lastrowid
    sid=new_session(c,party_id=party)
    assert c.get(f'/api/exploration/sessions/{sid}').json()['party_name']=='Heroes'
    for name,activity in [('Scout','scout'),('Shield','defend'),('Sneak','avoid'),('Mage','repeat')]:add(c,sid,name,activity)
    check=c.get(f'/api/exploration/sessions/{sid}/encounter').json()
    assert len(check['reminders'])==4 and any('+1 circumstance' in x for x in check['reminders'])
    assert any('shield' in x for x in check['reminders']) and any('Stealth' in x for x in check['reminders'])
    assert c.get('/tools/combat-tracker',params={'exploration_id':sid}).status_code==200
    assert c.get('/api/combat-tracker/combats').json()==[]


def test_validation_and_clock_separate_session(client):
    c,_=client;sid=new_session(c)
    assert c.post(f'/api/exploration/sessions/{sid}/members',json={'name':'X','activity':'invented'}).status_code==422
    add(c,sid,'Tracker','track')
    assert c.post(f'/api/exploration/sessions/{sid}/travel',json={}).json()['party_fpm'] is None
    assert c.post(f'/api/exploration/sessions/{sid}/travel',json={'override_fpm':40}).json()['party_fpm']==40
    assert c.post(f'/api/exploration/sessions/{sid}/clock',json={'minutes':0}).status_code==422
    assert c.post(f'/api/exploration/sessions/{sid}/clock',json={'minutes':-1,'correction':True}).status_code==422


def test_recorded_hustle_accumulates_with_time_and_activity_log(client):
    c,path=client;sid=new_session(c)
    mid=add(c,sid,'Runner','hustle',con=2)
    first=c.post(f'/api/exploration/sessions/{sid}/travel/record',json={'minutes':12}).json()
    assert first['session']['game_minutes']==12
    assert first['session']['members'][0]['hustle_used_minutes']==12
    second=c.post(f'/api/exploration/sessions/{sid}/travel/record',json={'minutes':10}).json()
    assert second['travel']['warnings']
    assert second['session']['members'][0]['hustle_used_minutes']==22
    changed=c.patch(f'/api/exploration/sessions/{sid}/members/{mid}',json={'activity':'scout'}).json()
    assert changed['log'][0]['event']=='Runner: Scout'
    with TestClient(create_app(db_path=path)) as restarted:
        saved=restarted.get(f'/api/exploration/sessions/{sid}').json()
        assert saved['game_minutes']==22 and saved['members'][0]['hustle_used_minutes']==22
