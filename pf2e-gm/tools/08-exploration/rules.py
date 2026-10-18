"""Concise Player Core exploration references and deterministic travel calculations."""

BASE = 'https://2e.aonprd.com/Rules.aspx?ID=2440'
ACTIVITIES = {
 'normal': ('Normal Travel','Make steady progress toward the destination.','Full travel speed.','None.','Full travel pace.','No special encounter effect.',438,1),
 'avoid': ('Avoid Notice','Use Stealth to avoid being noticed.','Half travel speed.','Stealth.','Attempt to avoid notice.','Usually use Stealth for initiative; resolve detection separately.',438,.5),
 'defend': ('Defend','Keep a shield raised while traveling.','Half travel speed.','A usable shield.','Shield remains raised.','Gain Raise a Shield benefits before the first turn, if applicable.',438,.5),
 'detect': ('Detect Magic','Cast detect magic at regular intervals.','Half speed or slower; 300 ft/min to avoid overlooking auras, 150 ft/min to detect before entering.','Ability to cast detect magic.','Notice magic auras at the relevant pace.','Resolve any ongoing spell effect with the GM.',438,.5),
 'follow': ('Follow the Expert','Follow an expert ally doing recurring skill checks.','Match the expert’s travel tactic and pace.','Willing ally at least expert in the relevant skill.','Add your level as proficiency if untrained; circumstance bonus +2/+3/+4 for expert/master/legendary ally.','Use the relevant activity and check guidance.',438,1),
 'hustle': ('Hustle','Push to travel faster for a limited time.','Double travel speed; Constitution modifier × 10 minutes, minimum 10.','Constitution modifier.','Cover ground quickly.','No automatic combat bonus.',438,2),
 'investigate': ('Investigate','Look for clues and recall relevant knowledge.','Half travel speed.','Relevant Recall Knowledge skill.','GM makes secret Recall Knowledge checks when relevant.','Resolve discovered clues separately.',439,.5),
 'repeat': ('Repeat a Spell','Cast the same suitable spell repeatedly.','Half travel speed.','Spell castable in 2 actions or fewer.','Keep a suitable spell ready.','Resolve the spell’s applicable effect; no automatic bonus.',439,.5),
 'scout': ('Scout','Watch ahead and behind for danger.','Half travel speed.','No specific skill.','Watch for danger.','Every party member gains +1 circumstance bonus to initiative at the next encounter.',439,.5),
 'search': ('Search','Seek hidden doors, hazards, and objects.','Usually half speed; thorough search at most 300 ft/min, or 150 ft/min before entering.','Perception; GM rolls secret Seek checks.','Search relevant locations.','Resolve secret checks and discoveries separately.',439,.5),
 'track': ('Track','Follow tracks using Survival.','Pace is set by the Track rule and GM.','Survival.','Follow tracks.','No automatic combat bonus.',439,None),
 'custom': ('Custom Activity','Record a GM-defined exploration tactic.','GM sets the travel pace.','GM decides.','GM decides.','Review the activity when combat begins.',None,None),
}

def library():
    result=[]
    for slug,(name,summary,movement,skill,benefit,encounter,page,multiplier) in ACTIVITIES.items():
        result.append(dict(slug=slug,name=name,summary=summary,movement=movement,skill=skill,benefit=benefit,
                           encounter=encounter,book='Player Core' if page else None,page=page,
                           url=BASE if page else None,multiplier=multiplier))
    return result


def hustle_limit(con_modifier):
    if not isinstance(con_modifier,int) or isinstance(con_modifier,bool) or not -20<=con_modifier<=30:
        raise ValueError('Enter an integer Constitution modifier')
    return max(10,con_modifier*10)


def travel(members,terrain='normal',minutes=10,search_mode='usual',detect_mode='usual',override_fpm=None):
    if terrain not in {'normal','difficult','greater'} or search_mode not in {'usual','thorough','before'} or detect_mode not in {'usual','auras','before'}:
        raise ValueError('Choose valid terrain and search modes')
    if not isinstance(minutes,int) or isinstance(minutes,bool) or not 1<=minutes<=10080:
        raise ValueError('Travel duration must be 1–10080 minutes')
    if override_fpm is not None and (not isinstance(override_fpm,int) or isinstance(override_fpm,bool) or override_fpm<1):
        raise ValueError('Manual party pace must be positive feet per minute')
    by_id={m['id']:m for m in members}
    rows=[]
    for member in members:
        speed=member['speed']
        if not isinstance(speed,int) or isinstance(speed,bool) or speed<1 or speed>500:
            raise ValueError('Speed must be 1–500 feet')
        slug=member['activity']
        if slug not in ACTIVITIES:
            raise ValueError('Unknown activity')
        effective=slug
        if slug=='follow':
            expert=by_id.get(member.get('expert_id'))
            if expert is None or expert['id']==member['id'] or expert.get('expert_rank') not in {'expert','master','legendary'} or not member.get('skill'):
                raise ValueError('Following the Expert needs another party member with an expert, master, or legendary rank and a relevant skill')
            effective=expert['activity']
            if effective=='follow':
                raise ValueError('Expert must have a direct activity')
        multiplier=ACTIVITIES[effective][-1]
        base=speed*10
        adjusted=None if multiplier is None else base*multiplier
        cap=None
        if effective=='search' and search_mode!='usual': cap=300 if search_mode=='thorough' else 150
        if effective=='detect' and detect_mode!='usual': cap=300 if detect_mode=='auras' else 150
        if cap is not None: adjusted=min(adjusted,cap)
        terrain_rate=None if adjusted is None else adjusted/({'normal':1,'difficult':2,'greater':3}[terrain])
        rows.append(dict(id=member['id'],name=member['name'],activity=slug,normal_fpm=base,activity_fpm=adjusted,
                         terrain_fpm=terrain_rate,hustle_limit_minutes=hustle_limit(member.get('con_modifier',0)) if effective=='hustle' else None,
                         hustle_used_minutes=member.get('hustle_used_minutes',0)))
    known=[row['terrain_fpm'] for row in rows if row['terrain_fpm'] is not None]
    unknown=any(row['terrain_fpm'] is None for row in rows)
    party_rate=override_fpm if override_fpm is not None else min(known) if known and not unknown else None
    group_limit=min((row['hustle_limit_minutes'] for row in rows if row['hustle_limit_minutes'] is not None),default=None)
    warnings=[]
    if unknown and override_fpm is None: warnings.append('Track or Custom Activity needs a GM-selected party pace.')
    if group_limit is not None and minutes>group_limit: warnings.append(f'Hustle exceeds the shortest single-segment limit ({group_limit} minutes); review the route.')
    for row in rows:
        if row['hustle_limit_minutes'] is not None and row['hustle_used_minutes']+minutes>row['hustle_limit_minutes']:
            warnings.append(f"{row['name']}: recorded Hustle time would exceed {row['hustle_limit_minutes']} minutes. Review before recording travel.")
    if override_fpm is not None: warnings.append('Manual pace overrides the slowest-member estimate; review split parties and unusual movement.')
    feet=None if party_rate is None else party_rate*minutes
    return dict(members=rows,party_fpm=party_rate,distance_feet=feet,distance_miles=None if feet is None else feet/5280,
                terrain=terrain,minutes=minutes,group_hustle_limit_minutes=group_limit,warnings=warnings,
                note='Foot-based distance is an estimate; Player Core also gives rounded miles-per-hour travel rates.')


def encounter_reminders(members):
    reminders=[]
    if any(m['activity']=='scout' for m in members):
        reminders.append('Scout: each party member gains +1 circumstance bonus to initiative at the next encounter. Apply once.')
    for m in members:
        name=m['name'];slug=m['activity']
        if slug=='avoid': reminders.append(f'{name}: usually use Stealth for initiative; resolve detection against Perception DCs separately.')
        elif slug=='defend': reminders.append(f'{name}: shield is raised if applicable; benefits apply before the first turn.')
        elif slug=='repeat': reminders.append(f'{name}: review the repeated spell and resolve its applicable effect.')
        elif slug=='follow': reminders.append(f'{name}: review the expert’s tactic and relevant skill check.')
    if not reminders: reminders.append('Review current activities and ask everyone to roll initiative as appropriate.')
    return reminders
