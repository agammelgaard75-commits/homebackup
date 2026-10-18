"""Exploration sessions, using the Phase 7 game clock and a read-only Combat handoff."""
from contextlib import closing
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from master.pages import layout
from shared.database.storage import connect

FOLDER=Path(__file__).resolve().parent
spec=spec_from_file_location('pf2e_exploration_rules',FOLDER/'rules.py')
rules=module_from_spec(spec);spec.loader.exec_module(rules)

class NewSession(BaseModel):
    name:str=Field(min_length=1,max_length=120)
    party_id:int|None=Field(default=None,strict=True,gt=0)
    linked_combat_id:int|None=Field(default=None,strict=True,gt=0)

class Member(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=1,max_length=120)
    speed:int=Field(default=25,strict=True,ge=1,le=500)
    con_modifier:int=Field(default=0,strict=True,ge=-20,le=30)
    activity:str='normal'
    skill:str=Field(default='',max_length=100)
    expert_rank:str=Field(default='',max_length=20)
    expert_id:int|None=Field(default=None,strict=True,gt=0)
    notes:str=Field(default='',max_length=500)

class MemberEdit(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str|None=Field(default=None,min_length=1,max_length=120)
    speed:int|None=Field(default=None,strict=True,ge=1,le=500)
    con_modifier:int|None=Field(default=None,strict=True,ge=-20,le=30)
    activity:str|None=None
    skill:str|None=Field(default=None,max_length=100)
    expert_rank:str|None=Field(default=None,max_length=20)
    expert_id:int|None=Field(default=None,strict=True,gt=0)
    notes:str|None=Field(default=None,max_length=500)
    hustle_used_minutes:int|None=Field(default=None,strict=True,ge=0,le=10000000)

class ClockChange(BaseModel):
    minutes:int=Field(strict=True,ge=0,le=10000000)
    correction:bool=False

class LogEntry(BaseModel):
    event:str=Field(min_length=1,max_length=120)
    note:str=Field(default='',max_length=1000)

class TravelInput(BaseModel):
    terrain:str='normal'
    minutes:int=Field(default=10,strict=True,ge=1,le=10080)
    search_mode:str='usual'
    detect_mode:str='usual'
    override_fpm:int|None=Field(default=None,strict=True,gt=0)


def initialize(database_path:Path)->None:
    with closing(connect(database_path)) as db:
        schema=db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='healing_clocks'").fetchone()
        if schema and "'exploration'" not in schema[0]:
            db.executescript("""
                CREATE TABLE healing_clocks_new(scope_kind TEXT NOT NULL CHECK(scope_kind IN ('combat','standalone','exploration')),
                    scope_id INTEGER NOT NULL,minutes INTEGER NOT NULL DEFAULT 0 CHECK(minutes>=0),PRIMARY KEY(scope_kind,scope_id));
                INSERT INTO healing_clocks_new SELECT * FROM healing_clocks;
                DROP TABLE healing_clocks;
                ALTER TABLE healing_clocks_new RENAME TO healing_clocks;
            """)
        db.executescript("""
            CREATE TABLE IF NOT EXISTS exploration_sessions(
                id INTEGER PRIMARY KEY,name TEXT NOT NULL,
                party_id INTEGER REFERENCES parties(id) ON DELETE SET NULL,
                linked_combat_id INTEGER REFERENCES combat_sessions(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS exploration_members(
                id INTEGER PRIMARY KEY,session_id INTEGER NOT NULL REFERENCES exploration_sessions(id) ON DELETE CASCADE,
                combatant_id INTEGER,name TEXT NOT NULL,speed INTEGER NOT NULL,con_modifier INTEGER NOT NULL DEFAULT 0,
                activity TEXT NOT NULL DEFAULT 'normal',skill TEXT NOT NULL DEFAULT '',expert_rank TEXT NOT NULL DEFAULT '',
                hustle_used_minutes INTEGER NOT NULL DEFAULT 0,
                expert_id INTEGER,notes TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS exploration_log(
                id INTEGER PRIMARY KEY,session_id INTEGER NOT NULL REFERENCES exploration_sessions(id) ON DELETE CASCADE,
                game_minutes INTEGER NOT NULL,event TEXT NOT NULL,note TEXT NOT NULL DEFAULT '');
            CREATE TRIGGER IF NOT EXISTS exploration_combat_deleted BEFORE DELETE ON combat_sessions
            BEGIN
                INSERT OR IGNORE INTO healing_clocks(scope_kind,scope_id,minutes)
                    SELECT 'exploration',s.id,COALESCE((SELECT minutes FROM healing_clocks WHERE scope_kind='combat' AND scope_id=OLD.id),0)
                    FROM exploration_sessions s WHERE s.linked_combat_id=OLD.id;
                UPDATE exploration_sessions SET linked_combat_id=NULL WHERE linked_combat_id=OLD.id;
            END;
        """)


def _session(db,session_id):
    row=db.execute('SELECT id,name,party_id,linked_combat_id FROM exploration_sessions WHERE id=?',(session_id,)).fetchone()
    if row is None: raise HTTPException(404,'Exploration session not found')
    ident,name,party_id,combat_id=row
    kind,scope_id=('combat',combat_id) if combat_id else ('exploration',ident)
    db.execute('INSERT OR IGNORE INTO healing_clocks(scope_kind,scope_id) VALUES (?,?)',(kind,scope_id))
    minutes=db.execute('SELECT minutes FROM healing_clocks WHERE scope_kind=? AND scope_id=?',(kind,scope_id)).fetchone()[0]
    state=None
    if combat_id:
        raw=db.execute('SELECT state_json FROM combat_sessions WHERE id=?',(combat_id,)).fetchone()
        state=json.loads(raw[0]) if raw else None
    names={a['id']:a['name'] for a in state['combatants']} if state else {}
    fields=('id','session_id','combatant_id','name','speed','con_modifier','activity','skill','expert_rank','expert_id','notes','hustle_used_minutes')
    members=[dict(zip(fields,row)) for row in db.execute('SELECT '+','.join(fields)+' FROM exploration_members WHERE session_id=? ORDER BY id',(ident,))]
    for m in members:
        if m['combatant_id'] in names:m['name']=names[m['combatant_id']]
    logs=[dict(zip(('id','game_minutes','event','note'),row)) for row in db.execute('SELECT id,game_minutes,event,note FROM exploration_log WHERE session_id=? ORDER BY id DESC',(ident,))]
    party=db.execute('SELECT name FROM parties WHERE id=?',(party_id,)).fetchone() if party_id else None
    return dict(id=ident,name=name,party_id=party_id,party_name=party[0] if party else None,linked_combat_id=combat_id,
                game_minutes=minutes,members=members,log=logs,clock_scope={'kind':kind,'id':scope_id})


def _checked_activity(slug):
    if slug not in rules.ACTIVITIES: raise HTTPException(422,'Choose a listed exploration activity')
    return slug


def _write_log(db,session,event,note=''):
    db.execute('INSERT INTO exploration_log(session_id,game_minutes,event,note) VALUES (?,?,?,?)',
               (session['id'],session['game_minutes'],event,note))


def page():
    body='''<link rel="stylesheet" href="/tools/exploration/style.css">
    <nav><a class="back-link" href="/">← All tools</a> · <a href="/tools/combat-tracker">Combat Tracker</a> · <a href="/tools/healing-death">Healing &amp; Death</a></nav>
    <h1>Exploration Helper</h1><p>Organize exploration activities and notes.</p><p>Set activities, estimate party travel, and track in-game time.</p>
    <section class="explore-card"><h2>Session and party</h2><div class="explore-row"><label>Saved session<select id="session-list"></select></label><button id="load-session">Load</button><label>New session name<input id="new-name" value="Exploration"></label><label>Shared party<select id="party-list"></select></label><label>Link saved combat and clock<select id="combat-list"></select></label><button id="create-session">Create session</button></div><div id="overview"></div></section>
    <div id="workspace" hidden>
      <section class="explore-card"><h2>Party activities</h2><p class="hint">Changes save immediately. Importing PCs links names by stable combatant ID; exploration fields stay in this session.</p><button id="import-pcs">Import PCs from linked combat</button><div id="members"></div><div class="explore-row"><label>New character<input id="member-name" placeholder="Name"></label><label>Speed, feet<input id="member-speed" type="number" min="1" value="25"></label><label>Con modifier<input id="member-con" type="number" value="0"></label><button id="add-member">Add character</button></div></section>
      <section class="explore-card"><h2>Activity reference</h2><div id="activity-reference"></div><a href="/tools/rules-reference">Rules Quick Reference</a></section>
    <section class="explore-card"><h2>Travel calculator</h2><div class="explore-row"><label>Terrain<select id="terrain"><option value="normal">Normal</option><option value="difficult">Difficult</option><option value="greater">Greater difficult</option></select></label><label>Minutes<input id="travel-minutes" type="number" min="1" value="10"></label><label>Search pace<select id="search-mode"><option value="usual">Usual half speed</option><option value="thorough">Thorough: max 300 ft/min</option><option value="before">Before entering: max 150 ft/min</option></select></label><label>Detect Magic pace<select id="detect-mode"><option value="usual">Usual half speed</option><option value="auras">Avoid overlooking: max 300 ft/min</option><option value="before">Before entering: max 150 ft/min</option></select></label><label>Manual party pace, ft/min<input id="pace-override" type="number" min="1" placeholder="Optional"></label><button id="calculate">Calculate</button><button id="record-travel">Record travel and advance time</button></div><div id="travel-result"></div></section>
      <div class="explore-grid"><section class="explore-card"><h2>Game time</h2><p id="clock"></p><div class="explore-row"><button class="advance" data-minutes="1">+1 min</button><button class="advance" data-minutes="10">+10 min</button><button class="advance" data-minutes="30">+30 min</button><button class="advance" data-minutes="60">+1 hour</button><label>Custom minutes<input id="custom-minutes" type="number" min="1" value="10"></label><button id="advance-custom">Advance</button></div><div class="explore-row"><label>Correct total minutes<input id="correct-minutes" type="number" min="0"></label><button id="correct-time">Set game time</button></div><p class="hint">Time does not automatically heal, rest, or expire conditions. A linked combat shares the Healing &amp; Death clock.</p></section>
      <section class="explore-card"><h2>Quick tasks</h2><div id="tasks"></div></section></div>
      <section class="explore-card"><h2>Exploration notes</h2><div class="explore-row"><label>Event<input id="log-event" maxlength="120" placeholder="Door found"></label><label>GM note<input id="log-note" maxlength="1000" placeholder="Optional"></label><button id="add-log">Add to log</button></div><div id="log"></div></section>
      <section class="explore-card"><h2>Start Encounter</h2><button id="start-encounter">Start Encounter checklist</button><div id="encounter" hidden><div id="encounter-list"></div><label><input id="confirm-reminders" type="checkbox"> I reviewed these reminders</label><p><a id="combat-link" href="/tools/combat-tracker">Open Combat Tracker</a></p></div></section>
    </div><p id="explore-message" role="status"></p>
    <aside class="explore-card"><h2>Sources</h2><a href="https://2e.aonprd.com/Rules.aspx?ID=2440" target="_blank" rel="noopener noreferrer">Player Core pp. 438–439: Exploration Mode and Travel Speed</a> · <a href="https://2e.aonprd.com/Rules.aspx?ID=2442" target="_blank" rel="noopener noreferrer">Player Core pp. 438–439: Exploration Activities</a> · <a href="https://2e.aonprd.com/Rules.aspx?ID=2573" target="_blank" rel="noopener noreferrer">GM Core: Running Exploration</a></aside>
    <script src="/tools/exploration/app.js" defer></script>'''
    return layout('Exploration',body)


def register(app:FastAPI,database_path:Path)->None:
    @app.get('/tools/exploration',response_class=HTMLResponse)
    def exploration_page():return page()
    @app.get('/tools/exploration/style.css')
    def style():return FileResponse(FOLDER/'style.css',media_type='text/css')
    @app.get('/tools/exploration/app.js')
    def script():return FileResponse(FOLDER/'app.js',media_type='text/javascript')
    @app.get('/api/exploration/activities')
    def activities():return rules.library()
    @app.get('/api/exploration/options')
    def options():
        with closing(connect(database_path)) as db:
            return {'parties':[dict(id=i,name=n) for i,n in db.execute('SELECT id,name FROM parties ORDER BY name,id')],
                    'combats':[dict(id=i,name=n) for i,n in db.execute('SELECT id,name FROM combat_sessions ORDER BY id DESC')]}
    @app.get('/api/exploration/sessions')
    def sessions():
        with closing(connect(database_path)) as db:
            return [dict(id=i,name=n,party_id=p,linked_combat_id=c) for i,n,p,c in db.execute('SELECT id,name,party_id,linked_combat_id FROM exploration_sessions ORDER BY id DESC')]
    @app.post('/api/exploration/sessions',status_code=201)
    def create(values:NewSession):
        with closing(connect(database_path)) as db,db:
            if values.party_id and not db.execute('SELECT 1 FROM parties WHERE id=?',(values.party_id,)).fetchone():raise HTTPException(404,'Party not found')
            if values.linked_combat_id and not db.execute('SELECT 1 FROM combat_sessions WHERE id=?',(values.linked_combat_id,)).fetchone():raise HTTPException(404,'Combat not found')
            ident=db.execute('INSERT INTO exploration_sessions(name,party_id,linked_combat_id) VALUES (?,?,?)',(values.name.strip(),values.party_id,values.linked_combat_id)).lastrowid
            return _session(db,ident)
    @app.get('/api/exploration/sessions/{session_id}')
    def get(session_id:int):
        with closing(connect(database_path)) as db,db:return _session(db,session_id)
    @app.post('/api/exploration/sessions/{session_id}/members',status_code=201)
    def add_member(session_id:int,values:Member):
        _checked_activity(values.activity)
        with closing(connect(database_path)) as db,db:
            _session(db,session_id)
            ident=db.execute('INSERT INTO exploration_members(session_id,name,speed,con_modifier,activity,skill,expert_rank,expert_id,notes) VALUES (?,?,?,?,?,?,?,?,?)',
                             (session_id,values.name.strip(),values.speed,values.con_modifier,values.activity,values.skill,values.expert_rank,values.expert_id,values.notes)).lastrowid
            return {'id':ident,'session':_session(db,session_id)}
    @app.post('/api/exploration/sessions/{session_id}/import-pcs')
    def import_pcs(session_id:int):
        with closing(connect(database_path)) as db,db:
            session=_session(db,session_id)
            if not session['linked_combat_id']:raise HTTPException(422,'Link a saved combat first')
            state=json.loads(db.execute('SELECT state_json FROM combat_sessions WHERE id=?',(session['linked_combat_id'],)).fetchone()[0]);added=0
            for actor in state['combatants']:
                if actor['type']=='PC' and not db.execute('SELECT 1 FROM exploration_members WHERE session_id=? AND combatant_id=?',(session_id,actor['id'])).fetchone():
                    db.execute('INSERT INTO exploration_members(session_id,combatant_id,name,speed) VALUES (?,?,?,25)',(session_id,actor['id'],actor['name']));added+=1
            return {'added':added,'session':_session(db,session_id)}
    @app.patch('/api/exploration/sessions/{session_id}/members/{member_id}')
    def edit_member(session_id:int,member_id:int,values:MemberEdit):
        data=values.model_dump(exclude_unset=True)
        if 'activity' in data:_checked_activity(data['activity'])
        if 'expert_rank' in data and data['expert_rank'] not in {'','expert','master','legendary'}:raise HTTPException(422,'Choose a valid expert rank')
        if 'name' in data:data['name']=data['name'].strip()
        with closing(connect(database_path)) as db,db:
            session=_session(db,session_id)
            previous=next((m for m in session['members'] if m['id']==member_id),None)
            if previous is None:raise HTTPException(404,'Member not found')
            if data:db.execute('UPDATE exploration_members SET '+','.join(f'{key}=?' for key in data)+' WHERE id=?',(*data.values(),member_id))
            if 'activity' in data and data['activity']!=previous['activity']:
                _write_log(db,session,f"{previous['name']}: {rules.ACTIVITIES[data['activity']][0]}")
            return _session(db,session_id)
    @app.delete('/api/exploration/sessions/{session_id}/members/{member_id}',status_code=204)
    def remove_member(session_id:int,member_id:int):
        with closing(connect(database_path)) as db,db:
            if not db.execute('DELETE FROM exploration_members WHERE id=? AND session_id=?',(member_id,session_id)).rowcount:raise HTTPException(404,'Member not found')
    @app.post('/api/exploration/sessions/{session_id}/travel')
    def calculate(session_id:int,values:TravelInput):
        with closing(connect(database_path)) as db,db:
            session=_session(db,session_id)
            try:return rules.travel(session['members'],**values.model_dump())
            except ValueError as error:raise HTTPException(422,str(error)) from error
    @app.post('/api/exploration/sessions/{session_id}/travel/record')
    def record_travel(session_id:int,values:TravelInput):
        with closing(connect(database_path)) as db:
            db.execute('BEGIN IMMEDIATE');session=_session(db,session_id)
            try:calculation=rules.travel(session['members'],**values.model_dump())
            except ValueError as error:raise HTTPException(422,str(error)) from error
            if calculation['party_fpm'] is None:raise HTTPException(422,'Choose a manual pace before recording travel with Track or Custom Activity')
            for row in calculation['members']:
                if row['hustle_limit_minutes'] is not None:
                    db.execute('UPDATE exploration_members SET hustle_used_minutes=hustle_used_minutes+? WHERE id=?',(values.minutes,row['id']))
            kind,ident=session['clock_scope']['kind'],session['clock_scope']['id']
            db.execute('UPDATE healing_clocks SET minutes=minutes+? WHERE scope_kind=? AND scope_id=?',(values.minutes,kind,ident))
            session['game_minutes']+=values.minutes
            note=f"{values.terrain} terrain; {calculation['distance_feet']:.1f} feet estimated" 
            if calculation['warnings']:note+='; '+ ' '.join(calculation['warnings'])
            _write_log(db,session,'Travel',note)
            result={'travel':calculation,'session':_session(db,session_id)};db.commit();return result
    @app.post('/api/exploration/sessions/{session_id}/clock')
    def clock(session_id:int,values:ClockChange):
        with closing(connect(database_path)) as db:
            db.execute('BEGIN IMMEDIATE');session=_session(db,session_id)
            if not values.correction and values.minutes<1:raise HTTPException(422,'Advance at least one minute')
            kind,ident=session['clock_scope']['kind'],session['clock_scope']['id']
            total=values.minutes if values.correction else session['game_minutes']+values.minutes
            db.execute('UPDATE healing_clocks SET minutes=? WHERE scope_kind=? AND scope_id=?',(total,kind,ident))
            session['game_minutes']=total
            _write_log(db,session,'Game time corrected' if values.correction else f'Advanced {values.minutes} minute(s)')
            result=_session(db,session_id);db.commit();return result
    @app.post('/api/exploration/sessions/{session_id}/log',status_code=201)
    def log(session_id:int,values:LogEntry):
        with closing(connect(database_path)) as db,db:
            session=_session(db,session_id);_write_log(db,session,values.event.strip(),values.note.strip());return _session(db,session_id)
    @app.get('/api/exploration/sessions/{session_id}/encounter')
    def encounter(session_id:int):
        with closing(connect(database_path)) as db,db:
            session=_session(db,session_id)
            return {'session_id':session_id,'linked_combat_id':session['linked_combat_id'],
                    'reminders':rules.encounter_reminders(session['members']),
                    'members':[{'id':m['id'],'combatant_id':m['combatant_id'],'name':m['name'],'activity':m['activity']} for m in session['members']],
                    'note':'Checklist only. Enter initiative manually in Combat Tracker; do not add Scout twice.'}
