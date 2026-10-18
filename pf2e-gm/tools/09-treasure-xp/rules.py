"""Verified GM Core reward tables and pure treasure/XP calculations."""

# GM Core p. 59, Table 10-9. (Total value gp, currency gp, currency/additional PC gp,
# permanent item levels, consumable item levels.) Currency is INCLUDED in total value.
TREASURE = {
 1:(175,40,10,{2:2,1:2},{2:2,1:3}),
 2:(300,70,18,{3:2,2:2},{3:2,2:2,1:2}),
 3:(500,120,30,{4:2,3:2},{4:2,3:2,2:2}),
 4:(850,200,50,{5:2,4:2},{5:2,4:2,3:2}),
 5:(1350,320,80,{6:2,5:2},{6:2,5:2,4:2}),
 6:(2000,500,125,{7:2,6:2},{7:2,6:2,5:2}),
 7:(2900,720,180,{8:2,7:2},{8:2,7:2,6:2}),
 8:(4000,1000,250,{9:2,8:2},{9:2,8:2,7:2}),
 9:(5700,1400,350,{10:2,9:2},{10:2,9:2,8:2}),
 10:(8000,2000,500,{11:2,10:2},{11:2,10:2,9:2}),
 11:(11500,2800,700,{12:2,11:2},{12:2,11:2,10:2}),
 12:(16500,4000,1000,{13:2,12:2},{13:2,12:2,11:2}),
 13:(25000,6000,1500,{14:2,13:2},{14:2,13:2,12:2}),
 14:(36500,9000,2250,{15:2,14:2},{15:2,14:2,13:2}),
 15:(54500,13000,3250,{16:2,15:2},{16:2,15:2,14:2}),
 16:(82500,20000,5000,{17:2,16:2},{17:2,16:2,15:2}),
 17:(128000,30000,7500,{18:2,17:2},{18:2,17:2,16:2}),
 18:(208000,48000,12000,{19:2,18:2},{19:2,18:2,17:2}),
 19:(355000,80000,20000,{20:2,19:2},{20:2,19:2,18:2}),
 20:(490000,140000,35000,{20:4},{20:4,19:2}),
}
HAZARD = {-4:(2,10),-3:(3,15),-2:(4,20),-1:(6,30),0:(8,40),1:(12,60),2:(16,80),3:(24,120),4:(32,160)}
ACCOMPLISHMENT={'minor':10,'moderate':30,'major':80}
ADVANCEMENT={'standard':1000,'fast':800,'slow':1200,'milestone':None}


def treasure_guideline(level:int,party_size:int)->dict:
    if not isinstance(level,int) or isinstance(level,bool) or level not in TREASURE:
        raise ValueError('Party level must be 1–20')
    if not isinstance(party_size,int) or isinstance(party_size,bool) or not 1<=party_size<=12:
        raise ValueError('Party size must be 1–12')
    total,currency,extra,permanent,consumable=TREASURE[level]
    delta=party_size-4
    return dict(level=level,party_size=party_size,total_value_gp=total,base_currency_gp=currency,
                currency_per_additional_pc_gp=extra,suggested_currency_gp=max(0,currency+delta*extra),
                permanent=permanent.copy(),consumable=consumable.copy(),
                extra_permanent_count=max(delta,0),extra_permanent_level_options=[level,min(level+1,20)] if delta>0 else [],
                extra_consumable={level:max(delta,0),min(level+1,20):max(delta,0)} if delta>0 and level<20 else ({20:2*delta} if delta>0 else {}),
                smaller_party_reduction=max(-delta,0),
                note=('For each additional PC, add one permanent item at party level or one higher, two consumables (normally one at each level), and listed currency.' if delta>0 else
                      'For each missing PC, you may subtract the corresponding items and currency, or keep more treasure to help the smaller party.' if delta<0 else
                      'Four-character guideline. Total value already includes currency and items.'),
                total_note='Approximate value for four PCs over the entire level; adjusted total is not exact because extra item prices vary.')


def hazard_xp(party_level:int,hazard_level:int,kind:str)->int:
    if not isinstance(party_level,int) or isinstance(party_level,bool) or not 1<=party_level<=20:
        raise ValueError('Party level must be 1–20')
    if not isinstance(hazard_level,int) or isinstance(hazard_level,bool) or kind not in {'simple','complex'}:
        raise ValueError('Choose a simple or complex hazard and its level')
    pair=HAZARD.get(hazard_level-party_level)
    if pair is None:raise ValueError('Hazard level must be within party level −4 to +4')
    return pair[0 if kind=='simple' else 1]


def progress(level:int,xp:int,method:str)->dict:
    if method not in ADVANCEMENT or not isinstance(level,int) or isinstance(level,bool) or not 1<=level<=20 or not isinstance(xp,int) or isinstance(xp,bool) or xp<0:
        raise ValueError('Enter level 1–20, nonnegative XP, and a listed advancement method')
    threshold=ADVANCEMENT[method]
    return dict(level=level,current_xp=xp,method=method,threshold=threshold,
                remaining=None if threshold is None or level==20 else max(0,threshold-xp),
                percentage=None if threshold is None else min(100,round(100*xp/threshold,1)),
                ready=threshold is not None and level<20 and xp>=threshold,
                milestone=method=='milestone',at_max_level=level==20)


def level_up(level:int,xp:int,method:str)->tuple[int,int]:
    state=progress(level,xp,method)
    if level==20:raise ValueError('Level 20 is the maximum supported level')
    if method=='milestone':return level+1,xp
    if not state['ready']:raise ValueError('XP threshold has not been reached')
    return level+1,xp-state['threshold']
