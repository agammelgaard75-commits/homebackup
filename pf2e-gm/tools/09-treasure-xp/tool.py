"""Treasure & XP Helper: local reward ledger with narrow Encounter Builder integration."""
from contextlib import closing
from decimal import Decimal
from importlib.util import module_from_spec,spec_from_file_location
import json
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI,HTTPException
from fastapi.responses import HTMLResponse,FileResponse
from pydantic import BaseModel,ConfigDict,Field

from master.pages import layout
from shared.database.storage import connect

FOLDER=Path(__file__).resolve().parent

def _module(name,path):
    spec=spec_from_file_location(name,path);module=module_from_spec(spec);spec.loader.exec_module(module);return module

rules=_module('pf2e_reward_rules',FOLDER/'rules.py')
encounter_calc=_module('pf2e_reward_encounter_calculator',FOLDER.parent/'03-encounter-builder'/'calculator.py')
CATEGORIES={'permanent','consumable','currency','valuable','other'}
STATUSES={'planned','awarded','missed'}

def _cp(value:Decimal)->int:
    if value<0 or value>Decimal('100000000') or value.as_tuple().exponent < -2:
        raise ValueError('GP value must be nonnegative, at most two decimal places, and within range')
    return int(value*100)

class TrackerInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=1,max_length=120)
    party_id:int|None=Field(default=None,strict=True,gt=0)
    level:int=Field(default=1,strict=True,ge=1,le=20)
    party_size:int=Field(default=4,strict=True,ge=1,le=12)
    current_xp:int=Field(default=0,strict=True,ge=0)
    method:str='standard'

class TrackerEdit(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str|None=Field(default=None,min_length=1,max_length=120)
    level:int|None=Field(default=None,strict=True,ge=1,le=20)
    party_size:int|None=Field(default=None,strict=True,ge=1,le=12)
    current_xp:int|None=Field(default=None,strict=True,ge=0)
    method:str|None=None
    baseline_gp:Decimal|None=None
    baseline_currency_gp:Decimal|None=None
    baseline_confirmed:bool|None=None

class TreasureInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=1,max_length=120)
    category:str
    item_level:int|None=Field(default=None,strict=True,ge=0,le=25)
    quantity:int=Field(default=1,strict=True,ge=1,le=10000)
    value_gp:Decimal=Decimal(0)
    source_book:str=Field(default='',max_length=120)
    source_page:int|None=Field(default=None,strict=True,ge=1)
    url:str=Field(default='',max_length=500)
    description:str=Field(default='',max_length=1000)
    encounter_id:int|None=Field(default=None,strict=True,gt=0)
    status:str='planned'
    session_label:str=Field(default='',max_length=120)
    notes:str=Field(default='',max_length=500)

class TreasureEdit(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str|None=Field(default=None,min_length=1,max_length=120)
    category:str|None=None
    item_level:int|None=Field(default=None,strict=True,ge=0,le=25)
    quantity:int|None=Field(default=None,strict=True,ge=1,le=10000)
    value_gp:Decimal|None=None
    source_book:str|None=Field(default=None,max_length=120)
    source_page:int|None=Field(default=None,strict=True,ge=1)
    url:str|None=Field(default=None,max_length=500)
    description:str|None=Field(default=None,max_length=1000)
    encounter_id:int|None=Field(default=None,strict=True,gt=0)
    status:str|None=None
    session_label:str|None=Field(default=None,max_length=120)
    notes:str|None=Field(default=None,max_length=500)

class XPAward(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:str
    description:str=Field(default='',max_length=500)
    amount_xp:int|None=Field(default=None,strict=True,ge=0)
    accomplishment:str|None=None
    hazard_kind:str|None=None
    hazard_level:int|None=Field(default=None,strict=True)
    encounter_id:int|None=Field(default=None,strict=True,gt=0)
    session_label:str=Field(default='',max_length=120)
    notes:str=Field(default='',max_length=500)
    allow_reaward:bool=False

class Reversal(BaseModel):
    reason:str=Field(min_length=1,max_length=500)


def initialize(database_path:Path)->None:
    with closing(connect(database_path)) as db,db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS reward_trackers(
                id INTEGER PRIMARY KEY,party_id INTEGER UNIQUE REFERENCES parties(id) ON DELETE CASCADE,
                name TEXT NOT NULL,level INTEGER NOT NULL,party_size INTEGER NOT NULL,current_xp INTEGER NOT NULL,
                method TEXT NOT NULL,baseline_cp INTEGER NOT NULL DEFAULT 0,baseline_currency_cp INTEGER NOT NULL DEFAULT 0,
                baseline_confirmed INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS treasure_rewards(
                id INTEGER PRIMARY KEY,tracker_id INTEGER NOT NULL REFERENCES reward_trackers(id) ON DELETE CASCADE,
                name TEXT NOT NULL,category TEXT NOT NULL,item_level INTEGER,quantity INTEGER NOT NULL,value_cp_each INTEGER NOT NULL,
                source_book TEXT NOT NULL DEFAULT '',source_page INTEGER,url TEXT NOT NULL DEFAULT '',description TEXT NOT NULL DEFAULT '',
                encounter_id INTEGER REFERENCES encounters(id) ON DELETE SET NULL,status TEXT NOT NULL,
                session_label TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',awarded_party_level INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS xp_transactions(
                id INTEGER PRIMARY KEY,tracker_id INTEGER NOT NULL REFERENCES reward_trackers(id) ON DELETE CASCADE,
                kind TEXT NOT NULL,description TEXT NOT NULL,amount_xp INTEGER NOT NULL,party_level INTEGER NOT NULL,
                encounter_id INTEGER REFERENCES encounters(id) ON DELETE SET NULL,reverses_id INTEGER UNIQUE REFERENCES xp_transactions(id),
                session_label TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE INDEX IF NOT EXISTS xp_transactions_tracker ON xp_transactions(tracker_id,id);
            CREATE INDEX IF NOT EXISTS treasure_rewards_tracker ON treasure_rewards(tracker_id,id);
            CREATE TABLE IF NOT EXISTS reward_events(
                id INTEGER PRIMARY KEY,tracker_id INTEGER NOT NULL REFERENCES reward_trackers(id) ON DELETE CASCADE,
                event_type TEXT NOT NULL,description TEXT NOT NULL,party_level INTEGER NOT NULL,
                treasure_id INTEGER,encounter_id INTEGER REFERENCES encounters(id) ON DELETE SET NULL,
                session_label TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',before_json TEXT,after_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        ''')


def _tracker(db,ident):
    row=db.execute('SELECT id,party_id,name,level,party_size,current_xp,method,baseline_cp,baseline_currency_cp,baseline_confirmed FROM reward_trackers WHERE id=?',(ident,)).fetchone()
    if row is None:raise HTTPException(404,'Reward tracker not found')
    fields=('id','party_id','name','level','party_size','current_xp','method','baseline_cp','baseline_currency_cp','baseline_confirmed')
    result=dict(zip(fields,row))
    if result['party_id']:
        party=db.execute('SELECT name FROM parties WHERE id=?',(result['party_id'],)).fetchone()
        if party:result['name']=party[0]
    result['baseline_gp']=result.pop('baseline_cp')/100
    result['baseline_currency_gp']=result.pop('baseline_currency_cp')/100
    result['baseline_confirmed']=bool(result['baseline_confirmed'])
    result['progress']=rules.progress(result['level'],result['current_xp'],result['method'])
    return result


def _treasure(row):
    fields=('id','tracker_id','name','category','item_level','quantity','value_cp_each','source_book','source_page','url','description','encounter_id','status','session_label','notes','awarded_party_level','created_at','updated_at')
    data=dict(zip(fields,row));data['value_gp']=data.pop('value_cp_each')/100
    data['total_gp']=round(data['value_gp']*data['quantity'],2)
    return data


def _rewards(db,tracker_id):
    return [_treasure(row) for row in db.execute('SELECT id,tracker_id,name,category,item_level,quantity,value_cp_each,source_book,source_page,url,description,encounter_id,status,session_label,notes,awarded_party_level,created_at,updated_at FROM treasure_rewards WHERE tracker_id=? ORDER BY id DESC',(tracker_id,))]


def _overview(tracker,rewards):
    guideline=rules.treasure_guideline(tracker['level'],tracker['party_size'])
    awarded=[r for r in rewards if r['status']=='awarded']
    planned=[r for r in rewards if r['status']=='planned']
    awarded_gp=round(tracker['baseline_gp']+sum(r['total_gp'] for r in awarded),2)
    planned_gp=round(sum(r['total_gp'] for r in planned),2)
    currency_gp=round(tracker['baseline_currency_gp']+sum(r['total_gp'] for r in awarded if r['category'] in {'currency','valuable'}),2)
    counts={'permanent':{},'consumable':{}}
    for r in awarded:
        if r['category'] in counts and r['item_level'] is not None:
            bucket=counts[r['category']];bucket[r['item_level']]=bucket.get(r['item_level'],0)+r['quantity']
    warnings=[]
    if not tracker['baseline_confirmed']:warnings.append('Prior treasure has not been confirmed. Enter earlier awards or set a baseline before treating remaining treasure as a complete balance.')
    if awarded_gp>guideline['total_value_gp']*1.25:warnings.append('Awarded value is well above the four-character guideline for this level; review if intended.')
    if awarded_gp<guideline['total_value_gp']*.5:warnings.append('Awarded value is below half the four-character guideline; this can be normal early in a level.')
    return dict(guideline=guideline,planned_gp=planned_gp,awarded_gp=awarded_gp,
                remaining_suggested_gp=round(guideline['total_value_gp']-awarded_gp,2),
                currency_awarded_gp=currency_gp,currency_remaining_gp=round(guideline['suggested_currency_gp']-currency_gp,2),
                awarded_item_levels=counts,permanent_awarded=sum(counts['permanent'].values()),
                consumables_awarded=sum(counts['consumable'].values()),warnings=warnings)


def _event(db,tracker,event_type,description,before=None,after=None,treasure_id=None,encounter_id=None,session_label='',notes=''):
    db.execute('INSERT INTO reward_events(tracker_id,event_type,description,party_level,treasure_id,encounter_id,session_label,notes,before_json,after_json) VALUES (?,?,?,?,?,?,?,?,?,?)',
               (tracker['id'],event_type,description,tracker['level'],treasure_id,encounter_id,session_label,notes,
                json.dumps(before) if before is not None else None,json.dumps(after) if after is not None else None))


def _valid_reward(data,db):
    if data['category'] not in CATEGORIES or data['status'] not in STATUSES:raise ValueError('Choose a listed category and status')
    if data['category'] in {'permanent','consumable'} and data['item_level'] is None:raise ValueError('Enter the item level for a permanent item or consumable')
    if not data['name'].strip():raise ValueError('Enter a reward name')
    if data['url'] and (urlparse(data['url']).scheme not in {'http','https'} or not urlparse(data['url']).netloc):raise ValueError('Use an http or https reference URL')
    if data['encounter_id'] and not db.execute('SELECT 1 FROM encounters WHERE id=?',(data['encounter_id'],)).fetchone():raise ValueError('Saved encounter not found')
    _cp(Decimal(str(data['value_gp'])))


def _encounter(db,encounter_id):
    row=db.execute('SELECT id,name,party_level,party_size,target FROM encounters WHERE id=?',(encounter_id,)).fetchone()
    if row is None:raise HTTPException(404,'Saved encounter not found')
    fields=('id','name','party_level','party_size','target');info=dict(zip(fields,row))
    creatures=[dict(level=level,quantity=qty,name=name) for name,level,qty in db.execute('SELECT name,level,quantity FROM encounter_creatures WHERE encounter_id=? ORDER BY position,id',(encounter_id,))]
    try:calculation=encounter_calc.calculate(info['party_level'],info['party_size'],info['target'],creatures)
    except ValueError as error:raise HTTPException(422,str(error)) from error
    suggestion=calculation['standard_award_xp'] if calculation['total_xp']==calculation['adjusted_target'] else None
    return dict(**info,calculation=calculation,suggested_xp=suggestion,
                note='Standard award applies when the saved encounter matches its selected adjusted target. For custom totals, set an award using GM Core guidance; XP is per character, never divided by party size.')


def _award_amount(db,tracker,values):
    if values.kind=='accomplishment':
        if values.accomplishment not in rules.ACCOMPLISHMENT:raise ValueError('Choose minor, moderate, or major accomplishment')
        reference=rules.ACCOMPLISHMENT[values.accomplishment]
    elif values.kind=='hazard':
        if values.hazard_level is None or values.hazard_kind is None:raise ValueError('Choose hazard kind and level')
        reference=rules.hazard_xp(tracker['level'],values.hazard_level,values.hazard_kind)
    elif values.kind=='encounter':
        if values.encounter_id is None:raise ValueError('Choose a saved encounter')
        reference=_encounter(db,values.encounter_id)['suggested_xp']
    elif values.kind=='custom':reference=None
    else:raise ValueError('Choose accomplishment, hazard, encounter, or custom')
    if values.amount_xp is None:
        if reference is None:raise ValueError('Enter a GM-selected XP award for this reward')
        amount=reference
    else:amount=values.amount_xp
    if tracker['method']=='milestone' and amount>0:raise ValueError('Milestone leveling does not add XP; use Advance Level at a story milestone')
    return amount,reference


def page():
    body='''<link rel="stylesheet" href="/tools/treasure-xp/style.css">
    <nav><a class="back-link" href="/">← All tools</a> · <a href="/tools/encounter-builder">Encounter Builder</a> · <a href="/tools/combat-tracker">Combat Tracker</a></nav>
    <h1>Treasure &amp; XP Helper</h1><p>Track rewards and experience for the party.</p>
    <section class="reward-card"><h2>Party</h2><div class="reward-row"><label>Existing reward tracker<select id="tracker-list"></select></label><button id="load-tracker">Load</button><label>New tracker name<input id="new-name" value="Adventuring party"></label><label>Shared party<select id="party-list"></select></label><button id="create-tracker">Create tracker</button></div><div id="settings" hidden><div class="reward-row"><label>Party level<input id="level" type="number" min="1" max="20"></label><label>Players<input id="party-size" type="number" min="1" max="12"></label><label>Current XP per character<input id="current-xp" type="number" min="0"></label><label>Advancement<select id="method"><option value="standard">Standard · 1,000 XP</option><option value="fast">Fast · 800 XP</option><option value="slow">Slow · 1,200 XP</option><option value="milestone">Milestone</option></select></label><button id="save-settings">Save settings</button></div><p class="hint">The tracker stores one party-level XP total. Set current XP here when joining a campaign in progress.</p></div></section>
    <div id="workspace" hidden><div class="tabs" role="tablist"><button id="tab-treasure" class="selected" type="button">Treasure</button><button id="tab-xp" type="button">Experience</button></div>
    <div id="treasure-panel"><section class="reward-card"><h2>Treasure guideline</h2><div id="guideline"></div><p class="hint">Award these suggestions over an entire level. Approximate total value already includes currency; do not add currency again.</p></section>
    <section class="reward-card"><h2>Treasure overview</h2><div id="overview"></div><h3>Earlier awards / baseline</h3><div class="reward-row"><label>Previously awarded total, gp<input id="baseline-gp" type="number" min="0" step="0.01"></label><label>Of that, currency and valuables, gp<input id="baseline-currency" type="number" min="0" step="0.01"></label><label><input id="baseline-confirmed" type="checkbox"> Prior rewards reviewed</label><button id="save-baseline">Save baseline</button></div><p class="hint">Add earlier permanent or consumable items as awarded entries to track their item levels and quantities.</p></section>
    <section class="reward-card"><h2>Add treasure</h2><div class="reward-row"><label>Reward name<input id="reward-name" placeholder="Chest in Spider Cavern"></label><label>Category<select id="reward-category"><option value="permanent">Permanent item</option><option value="consumable">Consumable</option><option value="currency">Currency</option><option value="valuable">Gemstone or valuable</option><option value="other">Other</option></select></label><label>Item level<input id="item-level" type="number" min="0" max="25"></label><label>Quantity<input id="quantity" type="number" min="1" value="1"></label><label>Value each, gp<input id="value-gp" type="number" min="0" step="0.01" value="0"></label></div><div class="reward-row"><label>Source book<input id="source-book"></label><label>Page<input id="source-page" type="number" min="1"></label><label>Archives URL<input id="reward-url" type="url"></label><label>Associated encounter<select id="reward-encounter"></select></label><label>Status<select id="reward-status"><option value="planned">Planned</option><option value="awarded">Awarded</option><option value="missed">Missed</option></select></label></div><div class="reward-row"><label>Description<input id="reward-description"></label><label>Date / session<input id="reward-session" placeholder="Session 4"></label><label>GM note<input id="reward-notes"></label><button id="add-reward">Add reward</button></div><div id="reward-list"></div></section>
    <section class="reward-card"><h2>Treasure history</h2><div id="treasure-history"></div></section></div>
    <div id="xp-panel" hidden><section class="reward-card"><h2>Experience progress</h2><div id="progress"></div><button id="level-up">Confirm level up</button><p class="hint">XP is awarded in full to each eligible member; it is never divided among players. Leveling requires GM confirmation.</p></section>
    <section class="reward-card"><h2>Award XP</h2><div class="reward-row"><label>Type<select id="xp-kind"><option value="accomplishment">Accomplishment</option><option value="encounter">Saved encounter</option><option value="hazard">Hazard</option><option value="custom">Custom</option></select></label><label>Accomplishment<select id="accomplishment"><option value="minor">Minor · 10</option><option value="moderate">Moderate · 30</option><option value="major">Major · 80</option></select></label><label>Encounter<select id="xp-encounter"></select></label><label>Hazard type<select id="hazard-kind"><option value="simple">Simple</option><option value="complex">Complex</option></select></label><label>Hazard level<input id="hazard-level" type="number" value="1"></label><label>XP per character<input id="xp-amount" type="number" min="0" placeholder="Use guidance"></label></div><div id="xp-guidance" class="hint"></div><div class="reward-row"><label>Description<input id="xp-description" placeholder="Moderate accomplishment"></label><label>Date / session<input id="xp-session" placeholder="Session 4"></label><label>GM note<input id="xp-notes"></label><label><input id="allow-reaward" type="checkbox"> Correct a reversed encounter award</label><button id="award-xp">Confirm XP award</button></div><p class="hint">For a custom encounter, set the award after reading GM Core guidance. Correct mistakes by reversing a history entry, then creating a new award with a correction note.</p></section>
    <section class="reward-card"><h2>XP history</h2><div id="xp-history"></div></section></div></div>
    <p id="reward-message" role="status"></p><aside class="reward-card"><h2>Rules</h2><a href="/tools/rules-reference">Rules Quick Reference</a> · <a href="https://2e.aonprd.com/Rules.aspx?ID=2655" target="_blank" rel="noopener noreferrer">GM Core pp. 58–61: Treasure</a> · <a href="https://2e.aonprd.com/Rules.aspx?ID=2656" target="_blank" rel="noopener noreferrer">GM Core p. 59: Party Treasure by Level</a> · <a href="https://2e.aonprd.com/Rules.aspx?ID=2649" target="_blank" rel="noopener noreferrer">GM Core p. 56: XP Awards</a> · <a href="https://2e.aonprd.com/Rules.aspx?ID=2652" target="_blank" rel="noopener noreferrer">GM Core p. 56: Party Size</a> · <a href="https://2e.aonprd.com/Rules.aspx?ID=2654" target="_blank" rel="noopener noreferrer">GM Core p. 57: Advancement Speeds</a></aside>
    <script src="/tools/treasure-xp/app.js" defer></script>'''
    return layout('Treasure & XP',body)


def register(app:FastAPI,database_path:Path)->None:
    @app.get('/tools/treasure-xp',response_class=HTMLResponse)
    def reward_page():return page()
    @app.get('/tools/treasure-xp/style.css')
    def style():return FileResponse(FOLDER/'style.css',media_type='text/css')
    @app.get('/tools/treasure-xp/app.js')
    def script():return FileResponse(FOLDER/'app.js',media_type='text/javascript')
    @app.get('/api/treasure-xp/options')
    def options():
        with closing(connect(database_path)) as db:
            parties=[dict(id=i,name=n) for i,n in db.execute('SELECT id,name FROM parties ORDER BY name,id')]
            encounters=[dict(id=i,name=n,party_level=l,party_size=s,target=t) for i,n,l,s,t in db.execute('SELECT id,name,party_level,party_size,target FROM encounters ORDER BY name,id')]
            return dict(parties=parties,encounters=encounters)
    @app.get('/api/treasure-xp/trackers')
    def trackers():
        with closing(connect(database_path)) as db:
            return [dict(id=i,party_id=p,name=(db.execute('SELECT name FROM parties WHERE id=?',(p,)).fetchone() or (name,))[0] if p else name,level=l,party_size=s,current_xp=xp,method=m)
                    for i,p,name,l,s,xp,m in db.execute('SELECT id,party_id,name,level,party_size,current_xp,method FROM reward_trackers ORDER BY id DESC').fetchall()]
    @app.post('/api/treasure-xp/trackers',status_code=201)
    def create(values:TrackerInput):
        if values.method not in rules.ADVANCEMENT or not values.name.strip():raise HTTPException(422,'Enter a tracker name and advancement method')
        with closing(connect(database_path)) as db,db:
            if values.party_id:
                party=db.execute('SELECT name FROM parties WHERE id=?',(values.party_id,)).fetchone()
                if party is None:raise HTTPException(404,'Shared party not found')
                existing=db.execute('SELECT id FROM reward_trackers WHERE party_id=?',(values.party_id,)).fetchone()
                if existing:return _tracker(db,existing[0])
            ident=db.execute('INSERT INTO reward_trackers(party_id,name,level,party_size,current_xp,method) VALUES (?,?,?,?,?,?)',
                             (values.party_id,values.name.strip(),values.level,values.party_size,values.current_xp,values.method)).lastrowid
            return _tracker(db,ident)
    @app.get('/api/treasure-xp/trackers/{tracker_id}')
    def get(tracker_id:int):
        with closing(connect(database_path)) as db:return _tracker(db,tracker_id)
    @app.patch('/api/treasure-xp/trackers/{tracker_id}')
    def edit(tracker_id:int,values:TrackerEdit):
        data=values.model_dump(exclude_unset=True)
        if 'method' in data and data['method'] not in rules.ADVANCEMENT:raise HTTPException(422,'Choose a listed advancement method')
        if 'name' in data and not data['name'].strip():raise HTTPException(422,'Enter a name')
        try:
            for key in ('baseline_gp','baseline_currency_gp'):
                if key in data:data[key.replace('_gp','_cp')]=_cp(data.pop(key))
        except ValueError as error:raise HTTPException(422,str(error)) from error
        if 'baseline_confirmed' in data:data['baseline_confirmed']=int(data['baseline_confirmed'])
        if 'name' in data:data['name']=data['name'].strip()
        with closing(connect(database_path)) as db,db:
            before=_tracker(db,tracker_id)
            total_cp=data.get('baseline_cp',round(before['baseline_gp']*100))
            currency_cp=data.get('baseline_currency_cp',round(before['baseline_currency_gp']*100))
            if currency_cp>total_cp:raise HTTPException(422,'Currency baseline is part of the total baseline and cannot exceed it')
            if data:
                db.execute('UPDATE reward_trackers SET '+','.join(f'{key}=?' for key in data)+' WHERE id=?',(*data.values(),tracker_id))
                after=_tracker(db,tracker_id)
                _event(db,before,'tracker_correction','Party settings or treasure baseline corrected',before,after)
                return after
            return before
    @app.get('/api/treasure-xp/trackers/{tracker_id}/overview')
    def overview(tracker_id:int):
        with closing(connect(database_path)) as db:
            tracker=_tracker(db,tracker_id);return _overview(tracker,_rewards(db,tracker_id))
    @app.get('/api/treasure-xp/trackers/{tracker_id}/treasure')
    def treasure_list(tracker_id:int):
        with closing(connect(database_path)) as db:
            _tracker(db,tracker_id);return _rewards(db,tracker_id)
    @app.post('/api/treasure-xp/trackers/{tracker_id}/treasure',status_code=201)
    def add_treasure(tracker_id:int,values:TreasureInput):
        data=values.model_dump()
        with closing(connect(database_path)) as db,db:
            tracker=_tracker(db,tracker_id)
            try:_valid_reward(data,db)
            except ValueError as error:raise HTTPException(422,str(error)) from error
            cp=_cp(data.pop('value_gp'))
            data['value_cp_each']=cp;data['tracker_id']=tracker_id
            data['awarded_party_level']=tracker['level'] if data['status']=='awarded' else None
            keys=list(data)
            ident=db.execute('INSERT INTO treasure_rewards('+','.join(keys)+') VALUES ('+','.join('?' for _ in keys)+')',tuple(data.values())).lastrowid
            reward=next(x for x in _rewards(db,tracker_id) if x['id']==ident)
            _event(db,tracker,'treasure_created',reward['name'],after=reward,treasure_id=ident,encounter_id=reward['encounter_id'],session_label=reward['session_label'],notes=reward['notes'])
            return reward
    @app.patch('/api/treasure-xp/trackers/{tracker_id}/treasure/{reward_id}')
    def edit_treasure(tracker_id:int,reward_id:int,values:TreasureEdit):
        edits=values.model_dump(exclude_unset=True)
        with closing(connect(database_path)) as db,db:
            tracker=_tracker(db,tracker_id);before=next((x for x in _rewards(db,tracker_id) if x['id']==reward_id),None)
            if before is None:raise HTTPException(404,'Treasure reward not found')
            merged={**before,**edits}
            try:_valid_reward(merged,db)
            except ValueError as error:raise HTTPException(422,str(error)) from error
            if not edits or all(before.get(key)==value for key,value in edits.items()):
                return before
            if 'value_gp' in edits:edits['value_cp_each']=_cp(edits.pop('value_gp'))
            if 'name' in edits:edits['name']=edits['name'].strip()
            if 'status' in edits and edits['status']=='awarded' and before['status']!='awarded':edits['awarded_party_level']=tracker['level']
            if 'status' in edits and edits['status']!='awarded':edits['awarded_party_level']=None
            if edits:
                db.execute('UPDATE treasure_rewards SET '+','.join(f'{key}=?' for key in edits)+',updated_at=CURRENT_TIMESTAMP WHERE id=? AND tracker_id=?',(*edits.values(),reward_id,tracker_id))
            after=next(x for x in _rewards(db,tracker_id) if x['id']==reward_id)
            if before!=after:_event(db,tracker,'treasure_corrected',after['name'],before,after,reward_id,after['encounter_id'],after['session_label'],after['notes'])
            return after
    @app.get('/api/treasure-xp/encounters/{encounter_id}/preview')
    def encounter_preview(encounter_id:int):
        with closing(connect(database_path)) as db:return _encounter(db,encounter_id)
    @app.post('/api/treasure-xp/trackers/{tracker_id}/xp',status_code=201)
    def award_xp(tracker_id:int,values:XPAward):
        with closing(connect(database_path)) as db:
            db.execute('BEGIN IMMEDIATE');tracker=_tracker(db,tracker_id)
            try:amount,reference=_award_amount(db,tracker,values)
            except ValueError as error:raise HTTPException(422,str(error)) from error
            if values.kind=='encounter':
                previous=db.execute("SELECT id FROM xp_transactions WHERE tracker_id=? AND encounter_id=? AND kind='encounter' AND reverses_id IS NULL ORDER BY id DESC",(tracker_id,values.encounter_id)).fetchall()
                if previous:
                    if any(not db.execute('SELECT 1 FROM xp_transactions WHERE reverses_id=?',(row[0],)).fetchone() for row in previous):
                        raise HTTPException(409,'This encounter already has an active XP award. Reverse it before correcting the amount.')
                    if not values.allow_reaward or not values.notes.strip():raise HTTPException(409,'This encounter was awarded before. Confirm re-award and record a correction note.')
            description=values.description.strip() or (f'{values.accomplishment.title()} accomplishment' if values.kind=='accomplishment' else
                          f'{values.hazard_kind.title()} hazard level {values.hazard_level}' if values.kind=='hazard' else
                          f"Encounter: {_encounter(db,values.encounter_id)['name']}" if values.kind=='encounter' else 'Custom XP')
            ident=db.execute('INSERT INTO xp_transactions(tracker_id,kind,description,amount_xp,party_level,encounter_id,session_label,notes) VALUES (?,?,?,?,?,?,?,?)',
                             (tracker_id,values.kind,description,amount,tracker['level'],values.encounter_id,values.session_label,values.notes)).lastrowid
            db.execute('UPDATE reward_trackers SET current_xp=current_xp+? WHERE id=?',(amount,tracker_id))
            db.commit();return dict(id=ident,amount_xp=amount,reference_xp=reference,tracker=_tracker(db,tracker_id))
    @app.post('/api/treasure-xp/trackers/{tracker_id}/xp/{transaction_id}/reverse')
    def reverse_xp(tracker_id:int,transaction_id:int,values:Reversal):
        with closing(connect(database_path)) as db:
            db.execute('BEGIN IMMEDIATE');tracker=_tracker(db,tracker_id)
            row=db.execute('SELECT kind,description,amount_xp,encounter_id,session_label FROM xp_transactions WHERE id=? AND tracker_id=? AND reverses_id IS NULL',(transaction_id,tracker_id)).fetchone()
            if row is None:raise HTTPException(404,'XP award not found')
            kind,description,amount,encounter_id,session_label=row
            if db.execute('SELECT 1 FROM xp_transactions WHERE reverses_id=?',(transaction_id,)).fetchone():raise HTTPException(409,'XP award already reversed')
            if tracker['current_xp']<amount:raise HTTPException(422,'Not enough current XP to reverse after level-up; correct the party XP manually with a ledger note')
            ident=db.execute('INSERT INTO xp_transactions(tracker_id,kind,description,amount_xp,party_level,encounter_id,reverses_id,session_label,notes) VALUES (?,?,?,?,?,?,?,?,?)',
                             (tracker_id,'reversal','Reversed: '+description,-amount,tracker['level'],encounter_id,transaction_id,session_label,values.reason.strip())).lastrowid
            db.execute('UPDATE reward_trackers SET current_xp=current_xp-? WHERE id=?',(amount,tracker_id))
            db.commit();return dict(id=ident,reversed_id=transaction_id,tracker=_tracker(db,tracker_id))
    @app.post('/api/treasure-xp/trackers/{tracker_id}/level-up')
    def level_up(tracker_id:int):
        with closing(connect(database_path)) as db:
            db.execute('BEGIN IMMEDIATE');tracker=_tracker(db,tracker_id)
            try:level,xp=rules.level_up(tracker['level'],tracker['current_xp'],tracker['method'])
            except ValueError as error:raise HTTPException(422,str(error)) from error
            db.execute('UPDATE reward_trackers SET level=?,current_xp=? WHERE id=?',(level,xp,tracker_id))
            after=_tracker(db,tracker_id);_event(db,tracker,'level_up',f'Advanced to level {level}',tracker,after)
            db.commit();return after
    @app.get('/api/treasure-xp/trackers/{tracker_id}/history')
    def history(tracker_id:int):
        with closing(connect(database_path)) as db:
            _tracker(db,tracker_id)
            xp=[dict(zip(('id','kind','description','amount_xp','party_level','encounter_id','reverses_id','session_label','notes','created_at'),row))
                for row in db.execute('SELECT id,kind,description,amount_xp,party_level,encounter_id,reverses_id,session_label,notes,created_at FROM xp_transactions WHERE tracker_id=? ORDER BY id DESC',(tracker_id,))]
            treasure=[dict(zip(('id','event_type','description','party_level','treasure_id','encounter_id','session_label','notes','before_json','after_json','created_at'),row))
                for row in db.execute('SELECT id,event_type,description,party_level,treasure_id,encounter_id,session_label,notes,before_json,after_json,created_at FROM reward_events WHERE tracker_id=? ORDER BY id DESC',(tracker_id,))]
            return dict(xp=xp,treasure=treasure)
