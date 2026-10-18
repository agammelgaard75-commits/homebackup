"""Phase 9 published table, reward ledger, XP, and integration tests."""
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from master.app import create_app
from shared.database.storage import connect

HERE=Path(__file__).resolve().parent
spec=spec_from_file_location('reward_rules_tests',HERE/'rules.py')
rules=module_from_spec(spec);spec.loader.exec_module(rules)


@pytest.mark.parametrize('level,total,currency,extra',[
 (1,175,40,10),(2,300,70,18),(3,500,120,30),(4,850,200,50),(5,1350,320,80),
 (6,2000,500,125),(7,2900,720,180),(8,4000,1000,250),(9,5700,1400,350),
 (10,8000,2000,500),(11,11500,2800,700),(12,16500,4000,1000),(13,25000,6000,1500),
 (14,36500,9000,2250),(15,54500,13000,3250),(16,82500,20000,5000),
 (17,128000,30000,7500),(18,208000,48000,12000),(19,355000,80000,20000),(20,490000,140000,35000)])
def test_full_published_treasure_table(level,total,currency,extra):
    g=rules.treasure_guideline(level,4)
    assert (g['total_value_gp'],g['base_currency_gp'],g['currency_per_additional_pc_gp'])==(total,currency,extra)
    assert sum(g['permanent'].values())==4
    assert sum(g['consumable'].values())==(5 if level==1 else 6)


def test_level_five_item_allocations_party_size_and_nonaddition():
    four=rules.treasure_guideline(5,4)
    assert four['permanent']=={6:2,5:2}
    assert four['consumable']=={6:2,5:2,4:2}
    assert four['total_value_gp']==1350 and four['suggested_currency_gp']==320
    five=rules.treasure_guideline(5,5)
    assert five['extra_permanent_count']==1 and five['extra_permanent_level_options']==[5,6]
    assert five['extra_consumable']=={5:1,6:1} and five['suggested_currency_gp']==400
    assert five['total_value_gp']==1350  # Currency is not added to this approximate total.
    three=rules.treasure_guideline(5,3)
    assert three['smaller_party_reduction']==1 and three['suggested_currency_gp']==240
    assert 'may subtract' in three['note']


@pytest.mark.parametrize('offset,simple,complex',[
 (-4,2,10),(-3,3,15),(-2,4,20),(-1,6,30),(0,8,40),(1,12,60),(2,16,80),(3,24,120),(4,32,160)])
def test_all_hazard_xp_values(offset,simple,complex):
    assert rules.hazard_xp(10,10+offset,'simple')==simple
    assert rules.hazard_xp(10,10+offset,'complex')==complex


def test_advancement_methods_and_carryover():
    assert rules.ACCOMPLISHMENT=={'minor':10,'moderate':30,'major':80}
    for method,threshold in [('standard',1000),('fast',800),('slow',1200)]:
        p=rules.progress(5,threshold,method)
        assert p['ready'] and p['remaining']==0
        assert rules.level_up(5,threshold+30,method)==(6,30)
    assert rules.progress(5,950,'standard')['remaining']==50
    assert rules.level_up(5,950,'milestone')==(6,950)
    assert rules.progress(5,0,'milestone')['threshold'] is None
    with pytest.raises(ValueError):rules.level_up(5,950,'standard')
    with pytest.raises(ValueError):rules.level_up(20,2000,'standard')


@pytest.fixture
def client(tmp_path):
    path=tmp_path/'rewards.sqlite3'
    with TestClient(create_app(db_path=path)) as c:yield c,path


def make_tracker(c,**extra):
    response=c.post('/api/treasure-xp/trackers',json={'name':'Heroes','level':5,'party_size':4,**extra})
    assert response.status_code==201,response.text
    return response.json()['id']


def add_reward(c,tid,**extra):
    body={'name':'Chest in Spider Cavern','category':'currency','quantity':1,'value_gp':'50','status':'planned',**extra}
    r=c.post(f'/api/treasure-xp/trackers/{tid}/treasure',json=body)
    assert r.status_code==201,r.text
    return r.json()


def test_existing_shared_party_single_xp_tracker(client):
    c,path=client
    with connect(path) as db:
        campaign=db.execute("INSERT INTO campaigns(name) VALUES ('Quest')").lastrowid
        party=db.execute("INSERT INTO parties(campaign_id,name) VALUES (?,?)",(campaign,'Knights')).lastrowid
    one=make_tracker(c,party_id=party)
    two=make_tracker(c,party_id=party)
    assert one==two
    assert len(c.get('/api/treasure-xp/trackers').json())==1
    assert c.get(f'/api/treasure-xp/trackers/{one}').json()['name']=='Knights'


def test_treasure_plan_award_correction_baseline_and_history(client):
    c,path=client;tid=make_tracker(c)
    r=add_reward(c,tid,category='permanent',item_level=6,quantity=2,value_gp='12.50',description='Two unnamed items')
    overview=c.get(f'/api/treasure-xp/trackers/{tid}/overview').json()
    assert overview['planned_gp']==25 and overview['awarded_gp']==0
    award=c.patch(f'/api/treasure-xp/trackers/{tid}/treasure/{r["id"]}',json={'status':'awarded','quantity':3})
    assert award.status_code==200
    changes_before=len(c.get(f'/api/treasure-xp/trackers/{tid}/history').json()['treasure'])
    assert c.patch(f'/api/treasure-xp/trackers/{tid}/treasure/{r["id"]}',json={'status':'awarded'}).status_code==200
    assert len(c.get(f'/api/treasure-xp/trackers/{tid}/history').json()['treasure'])==changes_before
    overview=c.get(f'/api/treasure-xp/trackers/{tid}/overview').json()
    assert overview['awarded_gp']==37.5 and overview['awarded_item_levels']['permanent']['6']==3
    assert overview['remaining_suggested_gp']==1312.5
    add_reward(c,tid,category='valuable',value_gp='50',status='awarded')
    c.patch(f'/api/treasure-xp/trackers/{tid}',json={'baseline_gp':'100','baseline_currency_gp':'40','baseline_confirmed':True})
    overview=c.get(f'/api/treasure-xp/trackers/{tid}/overview').json()
    assert overview['awarded_gp']==187.5 and overview['currency_awarded_gp']==90
    assert not any('Prior treasure' in text for text in overview['warnings'])
    history=c.get(f'/api/treasure-xp/trackers/{tid}/history').json()['treasure']
    assert any(row['event_type']=='treasure_corrected' for row in history)
    with TestClient(create_app(db_path=path)) as restarted:
        assert restarted.get(f'/api/treasure-xp/trackers/{tid}/overview').json()['awarded_gp']==187.5
        assert len(restarted.get(f'/api/treasure-xp/trackers/{tid}/treasure').json())==2


def test_moderate_accomplishment_and_level_confirmation(client):
    c,path=client;tid=make_tracker(c,current_xp=950)
    award=c.post(f'/api/treasure-xp/trackers/{tid}/xp',json={'kind':'accomplishment','accomplishment':'major','description':'Alliance','session_label':'Session 7'})
    assert award.status_code==201,award.text
    assert award.json()['amount_xp']==80 and award.json()['tracker']['current_xp']==1030
    assert award.json()['tracker']['progress']['ready']
    level=c.post(f'/api/treasure-xp/trackers/{tid}/level-up')
    assert level.status_code==200
    assert level.json()['level']==6 and level.json()['current_xp']==30
    with TestClient(create_app(db_path=path)) as restarted:
        assert restarted.get(f'/api/treasure-xp/trackers/{tid}').json()['current_xp']==30
        assert restarted.get(f'/api/treasure-xp/trackers/{tid}/history').json()['xp'][0]['amount_xp']==80


def test_all_accomplishment_types_and_reversal(client):
    c,_=client;tid=make_tracker(c,party_size=5)
    for kind,amount in rules.ACCOMPLISHMENT.items():
        r=c.post(f'/api/treasure-xp/trackers/{tid}/xp',json={'kind':'accomplishment','accomplishment':kind})
        assert r.status_code==201 and r.json()['amount_xp']==amount
    assert c.get(f'/api/treasure-xp/trackers/{tid}').json()['current_xp']==120
    first=c.get(f'/api/treasure-xp/trackers/{tid}/history').json()['xp'][-1]
    undo=c.post(f'/api/treasure-xp/trackers/{tid}/xp/{first["id"]}/reverse',json={'reason':'Entered twice'})
    assert undo.status_code==200 and undo.json()['tracker']['current_xp']==110
    assert c.post(f'/api/treasure-xp/trackers/{tid}/xp/{first["id"]}/reverse',json={'reason':'Again'}).status_code==409
    assert c.get(f'/api/treasure-xp/trackers/{tid}/history').json()['xp'][0]['reverses_id']==first['id']


def test_hazard_award_and_milestone(client):
    c,_=client;tid=make_tracker(c)
    award=c.post(f'/api/treasure-xp/trackers/{tid}/xp',json={'kind':'hazard','hazard_kind':'simple','hazard_level':5})
    assert award.status_code==201 and award.json()['amount_xp']==8
    assert c.post(f'/api/treasure-xp/trackers/{tid}/xp',json={'kind':'hazard','hazard_kind':'simple','hazard_level':20}).status_code==422
    c.patch(f'/api/treasure-xp/trackers/{tid}',json={'method':'milestone'})
    assert c.post(f'/api/treasure-xp/trackers/{tid}/xp',json={'kind':'custom','amount_xp':10}).status_code==422
    level=c.post(f'/api/treasure-xp/trackers/{tid}/level-up').json()
    assert level['level']==6 and level['current_xp']==8


def test_encounter_import_exact_target_not_adjusted_budget_duplicate_guard(client):
    c,path=client;tid=make_tracker(c,party_size=3,level=6)
    encounter=c.post('/api/encounter-builder/encounters',json={'name':'Guard patrol','party_level':6,'party_size':3,'target':'Moderate',
        'creatures':[{'name':'Guard','level':7,'quantity':1}]}).json()
    eid=encounter['id']
    preview=c.get(f'/api/treasure-xp/encounters/{eid}/preview').json()
    assert preview['calculation']['adjusted_target']==60 and preview['suggested_xp']==80
    body={'kind':'encounter','encounter_id':eid,'description':'Guard patrol'}
    first=c.post(f'/api/treasure-xp/trackers/{tid}/xp',json=body)
    assert first.status_code==201 and first.json()['amount_xp']==80
    assert c.post(f'/api/treasure-xp/trackers/{tid}/xp',json=body).status_code==409
    assert c.post(f'/api/treasure-xp/trackers/{tid}/xp/{first.json()["id"]}/reverse',json={'reason':'Wrong award'}).status_code==200
    assert c.post(f'/api/treasure-xp/trackers/{tid}/xp',json=body).status_code==409
    corrected=c.post(f'/api/treasure-xp/trackers/{tid}/xp',json={**body,'amount_xp':70,'allow_reaward':True,'notes':'GM correction'})
    assert corrected.status_code==201 and corrected.json()['tracker']['current_xp']==70
    assert c.post(f'/api/treasure-xp/trackers/{tid}/xp',json={**body,'allow_reaward':True,'notes':'Try again'}).status_code==409
    with TestClient(create_app(db_path=path)) as restarted:
        assert restarted.get(f'/api/treasure-xp/trackers/{tid}').json()['current_xp']==70
        assert len(restarted.get(f'/api/treasure-xp/trackers/{tid}/history').json()['xp'])==3


def test_custom_encounter_needs_manual_award_and_combat_link(client):
    c,_=client;tid=make_tracker(c)
    encounter=c.post('/api/encounter-builder/encounters',json={'name':'Between targets','party_level':5,'party_size':4,'target':'Moderate',
        'creatures':[{'name':'Foe','level':5,'quantity':1},{'name':'Weak','level':1,'quantity':5}]}).json()
    preview=c.get(f'/api/treasure-xp/encounters/{encounter["id"]}/preview').json()
    assert preview['calculation']['total_xp']==90 and preview['suggested_xp'] is None
    assert c.post(f'/api/treasure-xp/trackers/{tid}/xp',json={'kind':'encounter','encounter_id':encounter['id']}).status_code==422
    combat=c.post('/api/combat-tracker/combats',json={'source_encounter_id':encounter['id']}).json()
    combat=c.post(f'/api/combat-tracker/combats/{combat["id"]}/command',json={'op':'end'})
    assert combat.status_code==200 and 'Open reward screen' in c.get('/tools/combat-tracker').text
    assert c.get('/tools/treasure-xp',params={'combat_id':combat.json()['id']}).status_code==200
    reward=add_reward(c,tid,encounter_id=encounter['id'])
    assert reward['encounter_id']==encounter['id']


def test_validation_and_manual_baseline(client):
    c,_=client;tid=make_tracker(c)
    assert c.post(f'/api/treasure-xp/trackers/{tid}/treasure',json={'name':'X','category':'permanent','value_gp':'2'}).status_code==422
    assert c.post(f'/api/treasure-xp/trackers/{tid}/treasure',json={'name':'X','category':'currency','value_gp':'2.123'}).status_code==422
    assert c.patch(f'/api/treasure-xp/trackers/{tid}',json={'baseline_gp':'10','baseline_currency_gp':'20'}).status_code==422
    assert c.post(f'/api/treasure-xp/trackers/{tid}/xp',json={'kind':'custom','amount_xp':0}).status_code==201
