"""SQLite adapter for Phase 7. Combat HP and Phase 6 conditions stay authoritative."""

import json

RELEVANT = {"dying", "wounded", "doomed", "unconscious"}
SOURCE = "Healing & Death Helper"


def initialize(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS healing_profiles (
            id INTEGER PRIMARY KEY,
            combat_id INTEGER REFERENCES combat_sessions(id) ON DELETE CASCADE,
            combatant_id INTEGER,
            subject_id INTEGER REFERENCES condition_subjects(id) ON DELETE CASCADE,
            hero_points INTEGER NOT NULL DEFAULT 0 CHECK(hero_points BETWEEN 0 AND 3),
            standalone_max_hp INTEGER,
            standalone_hp INTEGER,
            standalone_temp_hp INTEGER NOT NULL DEFAULT 0,
            full_hp_since_minute INTEGER,
            last_seen_hp INTEGER,
            last_seen_max_hp INTEGER,
            CHECK ((combat_id IS NOT NULL AND combatant_id IS NOT NULL AND subject_id IS NULL)
                OR (combat_id IS NULL AND combatant_id IS NULL AND subject_id IS NOT NULL))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS healing_profile_combat
            ON healing_profiles(combat_id,combatant_id) WHERE combat_id IS NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS healing_profile_subject
            ON healing_profiles(subject_id) WHERE subject_id IS NOT NULL;
        CREATE TABLE IF NOT EXISTS healing_clocks (
            scope_kind TEXT NOT NULL CHECK(scope_kind IN ('combat','standalone')),
            scope_id INTEGER NOT NULL,
            minutes INTEGER NOT NULL DEFAULT 0 CHECK(minutes>=0),
            PRIMARY KEY(scope_kind,scope_id)
        );
        CREATE TABLE IF NOT EXISTS healing_treatments (
            id INTEGER PRIMARY KEY,
            combat_id INTEGER REFERENCES combat_sessions(id) ON DELETE CASCADE,
            combatant_id INTEGER,
            subject_id INTEGER REFERENCES condition_subjects(id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK(kind IN ('treat','battle')),
            healer TEXT NOT NULL,
            started_minute INTEGER NOT NULL,
            duration_minutes INTEGER NOT NULL,
            immunity_until_minute INTEGER NOT NULL,
            proficiency TEXT NOT NULL,
            dc INTEGER NOT NULL,
            degree TEXT NOT NULL,
            dice_total INTEGER,
            hp_change INTEGER NOT NULL,
            actual_hp_change INTEGER NOT NULL,
            override_note TEXT NOT NULL DEFAULT '',
            CHECK ((combat_id IS NOT NULL AND combatant_id IS NOT NULL AND subject_id IS NULL)
                OR (combat_id IS NULL AND combatant_id IS NULL AND subject_id IS NOT NULL))
        );
        CREATE INDEX IF NOT EXISTS healing_treatment_patient_combat ON healing_treatments(combat_id,combatant_id);
        CREATE INDEX IF NOT EXISTS healing_treatment_patient_subject ON healing_treatments(subject_id);
    """)


def target_key(target):
    combat_id, combatant_id, subject_id = target.get("combat_id"), target.get("combatant_id"), target.get("subject_id")
    if subject_id is not None and combat_id is None and combatant_id is None:
        return "subject_id=?", (subject_id,), "standalone", subject_id
    if combat_id is not None and combatant_id is not None and subject_id is None:
        return "combat_id=? AND combatant_id=?", (combat_id, combatant_id), "combat", combat_id
    raise ValueError("Choose one standalone character or one combatant")


def load(db, target):
    clause, params, scope_kind, scope_id = target_key(target)
    db.execute("INSERT OR IGNORE INTO healing_clocks(scope_kind,scope_id) VALUES (?,?)", (scope_kind, scope_id))
    clock = db.execute("SELECT minutes FROM healing_clocks WHERE scope_kind=? AND scope_id=?", (scope_kind, scope_id)).fetchone()[0]
    state = actor = None
    if scope_kind == "combat":
        row = db.execute("SELECT state_json FROM combat_sessions WHERE id=?", (target["combat_id"],)).fetchone()
        if row is None:
            raise ValueError("Combat not found")
        state = json.loads(row[0])
        actor = next((a for a in state["combatants"] if a["id"] == target["combatant_id"]), None)
        if actor is None:
            raise ValueError("Combatant not found")
        name, kind = actor["name"], actor["type"]
    else:
        row = db.execute("SELECT name FROM condition_subjects WHERE id=?", (target["subject_id"],)).fetchone()
        if row is None:
            raise ValueError("Standalone character not found")
        name, kind = row[0], "standalone"
    db.execute(f"INSERT OR IGNORE INTO healing_profiles({','.join(target)}) VALUES ({','.join('?' for _ in target)})", tuple(target.values()))
    profile = db.execute(f"SELECT id,hero_points,standalone_max_hp,standalone_hp,standalone_temp_hp,full_hp_since_minute,last_seen_hp,last_seen_max_hp FROM healing_profiles WHERE {clause}", params).fetchone()
    ident, hero, maximum, hp, temp, full_since, seen_hp, seen_max = profile
    if actor is not None:
        maximum, hp, temp = actor["max_hp"], actor["current_hp"], actor["temp_hp"]
        if hp != seen_hp or maximum != seen_max:
            full_since = clock if hp is not None and hp == maximum else None
            db.execute("UPDATE healing_profiles SET last_seen_hp=?,last_seen_max_hp=?,full_hp_since_minute=? WHERE id=?",
                       (hp, maximum, full_since, ident))
    records = db.execute(f"SELECT id,slug,value,source FROM active_conditions WHERE active=1 AND ({clause}) AND slug IN ('dying','wounded','doomed','unconscious') ORDER BY id", params).fetchall()
    conditions = [dict(id=i, slug=slug, value=value, source=source) for i, slug, value, source in records]
    values = {slug: max((r["value"] or 1 for r in conditions if r["slug"] == slug), default=0) for slug in RELEVANT}
    values["unconscious"] = max(values["unconscious"], int(values["dying"] > 0))
    return {"target": target, "name": name, "type": kind, "state": state, "actor": actor, "profile_id": ident,
            "hero_points": hero, "max_hp": maximum, "current_hp": hp, "temp_hp": temp,
            "full_hp_since_minute": full_since, "game_minutes": clock, "conditions": conditions,
            **values}


def save_hp(db, current, hp, maximum=None, temp=None):
    maximum = current["max_hp"] if maximum is None else maximum
    temp = current["temp_hp"] if temp is None else temp
    if maximum is None or hp is None or maximum < 1 or hp < 0 or hp > maximum or temp < 0:
        raise ValueError("Set valid maximum, current, and temporary HP")
    if current["actor"] is not None:
        actor = current["actor"]
        actor.update(max_hp=maximum, current_hp=hp, temp_hp=temp)
        db.execute("UPDATE combat_sessions SET state_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                   (json.dumps(current["state"]), current["target"]["combat_id"]))
    else:
        db.execute("UPDATE healing_profiles SET standalone_max_hp=?,standalone_hp=?,standalone_temp_hp=? WHERE id=?",
                   (maximum, hp, temp, current["profile_id"]))
    full_since = (current["full_hp_since_minute"] if current["current_hp"] == current["max_hp"]
                  else current["game_minutes"]) if hp == maximum else None
    db.execute("UPDATE healing_profiles SET full_hp_since_minute=?,last_seen_hp=?,last_seen_max_hp=? WHERE id=?",
               (full_since, hp, maximum, current["profile_id"]))
    current.update(max_hp=maximum, current_hp=hp, temp_hp=temp, full_hp_since_minute=full_since)


def set_hero(db, current, value):
    if not 0 <= value <= 3:
        raise ValueError("Hero Points must be from 0 to 3")
    db.execute("UPDATE healing_profiles SET hero_points=? WHERE id=?", (value, current["profile_id"]))
    current["hero_points"] = value


def set_condition(db, current, slug, value):
    """Update the one Phase 6 state, preserving unrelated condition sources and notes."""
    if slug not in RELEVANT or value < 0:
        raise ValueError("Invalid healing condition")
    clause, params, _, _ = target_key(current["target"])
    if value == 0:
        db.execute(f"DELETE FROM active_conditions WHERE active=1 AND ({clause}) AND slug=?", (*params, slug))
    else:
        rows = db.execute(f"SELECT id FROM active_conditions WHERE active=1 AND ({clause}) AND slug=?", (*params, slug)).fetchall()
        if rows:
            for (ident,) in rows:
                db.execute("UPDATE active_conditions SET value=? WHERE id=?", (value if slug != "unconscious" else None, ident))
        else:
            keys = list(current["target"]) + ["slug", "value", "source"]
            vals = list(current["target"].values()) + [slug, value if slug != "unconscious" else None, SOURCE]
            db.execute(f"INSERT INTO active_conditions({','.join(keys)}) VALUES ({','.join('?' for _ in vals)})", vals)
    current[slug] = value


def remove_own_unconscious(db, current):
    clause, params, _, _ = target_key(current["target"])
    db.execute(f"DELETE FROM active_conditions WHERE active=1 AND ({clause}) AND slug='unconscious' AND source=?", (*params, SOURCE))


def treatments(db, current):
    clause, params, _, _ = target_key(current["target"])
    records = db.execute(f"SELECT id,kind,healer,started_minute,duration_minutes,immunity_until_minute,proficiency,dc,degree,dice_total,hp_change,actual_hp_change,override_note FROM healing_treatments WHERE {clause} ORDER BY id DESC", params).fetchall()
    fields = ("id","kind","healer","started_minute","duration_minutes","immunity_until_minute","proficiency","dc","degree","dice_total","hp_change","actual_hp_change","override_note")
    return [dict(zip(fields, record)) for record in records]


def immunity_until(records, kind, healer=None):
    relevant = [row["immunity_until_minute"] for row in records if row["kind"] == kind and (kind == "treat" or row["healer"].casefold() == healer.casefold())]
    return max(relevant, default=0)
