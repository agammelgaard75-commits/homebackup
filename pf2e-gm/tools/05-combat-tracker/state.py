"""Pure combat bookkeeping. No rules decisions or database access live here."""

from copy import deepcopy
import re


KINDS = {"PC", "NPC", "monster"}


def new_combat(name: str, source_encounter_id: int | None = None, party_id: int | None = None) -> dict:
    if not name.strip() or len(name.strip()) > 120:
        raise ValueError("Enter a combat name of at most 120 characters")
    return {
        "name": name.strip(), "status": "active", "source_encounter_id": source_encounter_id, "party_id": party_id,
        "round": 1, "turns_started": False, "active_id": None,
        "order": [], "pending": [], "delayed": [], "delayed_since_round": {},
        "next_combatant_id": 1, "combatants": [],
    }


def combatant(state: dict, combatant_id: int) -> dict:
    for actor in state["combatants"]:
        if actor["id"] == combatant_id:
            return actor
    raise ValueError("Combatant not found")


def _sort_key(state: dict, combatant_id: int) -> tuple:
    actor = combatant(state, combatant_id)
    initiative = actor["initiative"]
    return (initiative is None, -(initiative or 0), actor["type"] == "PC")


def _start_turn(state: dict, combatant_id: int) -> None:
    if combatant_id in state["delayed"]:
        if state["round"] <= state["delayed_since_round"][str(combatant_id)]:
            raise ValueError("A delayed combatant cannot act before reentering")
        state["delayed"].remove(combatant_id)
        state["delayed_since_round"].pop(str(combatant_id), None)
    actor = combatant(state, combatant_id)
    actor["actions_remaining"] = 3
    actor["reaction_remaining"] = 1
    actor["attack_count"] = 0
    state["active_id"] = combatant_id


def _resort(state: dict) -> None:
    state["order"].sort(key=lambda ident: _sort_key(state, ident))
    if not state["turns_started"]:
        state["pending"] = [ident for ident in state["order"] if ident not in state["delayed"]]
        if state["pending"]:
            _start_turn(state, state["pending"][0])
        else:
            state["active_id"] = None
    else:
        active = state["active_id"]
        rest = sorted((ident for ident in state["pending"] if ident != active), key=lambda ident: _sort_key(state, ident))
        state["pending"] = ([active] if active is not None else []) + rest
        if active is None and rest:
            _start_turn(state, rest[0])


def _number_duplicates(state: dict, base_name: str) -> str:
    matching = [actor for actor in state["combatants"] if actor["name"] == base_name or re.fullmatch(re.escape(base_name) + r" \d+", actor["name"])]
    if not matching:
        return base_name
    if len(matching) == 1 and matching[0]["name"] == base_name:
        matching[0]["name"] = f"{base_name} 1"
    used = {int(actor["name"][len(base_name) + 1:]) for actor in matching if re.fullmatch(re.escape(base_name) + r" \d+", actor["name"])}
    number = 1
    while number in used:
        number += 1
    return f"{base_name} {number}"


def add_combatant(state: dict, name: str, kind: str, initiative: int | None = None,
                  max_hp: int | None = None, current_hp: int | None = None,
                  notes: str = "", party_member_id: int | None = None,
                  class_name: str = "") -> dict:
    if not name.strip() or len(name.strip()) > 120 or kind not in KINDS:
        raise ValueError("Enter a name and choose PC, NPC, or monster")
    if initiative is not None and (not isinstance(initiative, int) or isinstance(initiative, bool)):
        raise ValueError("Initiative must be an integer")
    if max_hp is not None and (not isinstance(max_hp, int) or isinstance(max_hp, bool) or max_hp < 1):
        raise ValueError("Maximum HP must be positive")
    if current_hp is not None and (not isinstance(current_hp, int) or isinstance(current_hp, bool) or max_hp is None or not 0 <= current_hp <= max_hp):
        raise ValueError("Current HP must be between 0 and maximum HP")
    if len(notes) > 1000:
        raise ValueError("Notes are too long")
    actual_name = _number_duplicates(state, name.strip())
    ident = state["next_combatant_id"]
    state["next_combatant_id"] += 1
    actor = {
        "id": ident, "name": actual_name, "type": kind, "initiative": initiative,
        "party_member_id": party_member_id, "class_name": class_name,
        "max_hp": max_hp, "current_hp": current_hp, "temp_hp": 0,
        "actions_remaining": 0, "reaction_remaining": 0, "attack_count": 0,
        "notes": notes, "effects": [],
    }
    state["combatants"].append(actor)
    state["order"].append(ident)
    if state["turns_started"]:
        state["pending"].append(ident)
    _resort(state)
    return actor


def import_party_members(state: dict, party_id: int, members: list[dict]) -> int:
    """Copy missing roster PCs into one running combat; repeated imports are safe."""
    if state.get("party_id") not in (None, party_id):
        raise ValueError("This combat is already linked to another party")
    if state["status"] == "ended":
        raise ValueError("Resume this combat before adding PCs")
    existing = {actor.get("party_member_id") for actor in state["combatants"] if actor.get("party_member_id") is not None}
    added = 0
    for member in members:
        if member["id"] in existing:
            continue
        add_combatant(state, member["name"], "PC", max_hp=member["max_hp"],
                      current_hp=member["current_hp"], notes=member["notes"],
                      party_member_id=member["id"], class_name=member["class_name"])
        added += 1
    state["party_id"] = party_id
    return added


def import_monster(state: dict, monster_id: int, monster: dict, quantity: int = 1, notes: str = "") -> None:
    """Copy a library monster as independent combat instances."""
    if state["status"] == "ended":
        raise ValueError("Resume this combat before adding monsters")
    if not 1 <= quantity <= 100:
        raise ValueError("Quantity must be from 1 to 100")
    optional = {key: value for key, value in monster.items()
                if key not in {"name", "level", "max_hp"} and value not in (None, "", [], {})}
    for _ in range(quantity):
        actor = add_combatant(state, monster["name"], "monster", max_hp=monster["max_hp"],
                              current_hp=monster["max_hp"], notes=notes or monster.get("notes", ""))
        actor["monster_id"] = monster_id
        actor["monster_level"] = monster["level"]
        actor["monster_stats"] = optional


def next_turn(state: dict) -> None:
    if state["active_id"] is None:
        return
    outgoing = combatant(state, state["active_id"])
    outgoing["actions_remaining"] = 0
    outgoing["attack_count"] = 0
    state["turns_started"] = True
    state["pending"].pop(0)
    if not state["pending"]:
        state["round"] += 1
        state["pending"] = state["order"].copy()
    if state["pending"]:
        _start_turn(state, state["pending"][0])
    else:
        state["active_id"] = None


def delay(state: dict) -> None:
    ident = state["active_id"]
    if ident is None:
        raise ValueError("No active combatant to delay")
    actor = combatant(state, ident)
    actor["reaction_remaining"] = 0
    actor["actions_remaining"] = 0
    actor["attack_count"] = 0
    state["delayed"].append(ident)
    state["delayed_since_round"][str(ident)] = state["round"]
    next_turn(state)


def reenter_after(state: dict, combatant_id: int, after_id: int) -> None:
    if combatant_id not in state["delayed"]:
        raise ValueError("Combatant is not delayed")
    if after_id not in state["pending"] or after_id == combatant_id:
        raise ValueError("Choose a current or upcoming combatant to follow")
    if combatant_id in state["pending"]:
        if state["pending"].index(after_id) >= state["pending"].index(combatant_id):
            raise ValueError("Reenter before the delayed combatant's original next turn")
        state["pending"].remove(combatant_id)
    state["delayed"].remove(combatant_id)
    state["delayed_since_round"].pop(str(combatant_id), None)
    state["pending"].insert(state["pending"].index(after_id) + 1, combatant_id)
    state["order"].remove(combatant_id)
    state["order"].insert(state["order"].index(after_id) + 1, combatant_id)


def move(state: dict, combatant_id: int, direction: str) -> None:
    if direction not in {"up", "down"} or combatant_id not in state["order"]:
        raise ValueError("Choose a combatant and Up or Down")
    index = state["order"].index(combatant_id)
    other = index + (-1 if direction == "up" else 1)
    if not 0 <= other < len(state["order"]):
        return
    state["order"][index], state["order"][other] = state["order"][other], state["order"][index]
    if not state["turns_started"]:
        state["pending"] = [ident for ident in state["order"] if ident not in state["delayed"]]
        if state["pending"]:
            _start_turn(state, state["pending"][0])
        return
    active = state["active_id"]
    future = [ident for ident in state["order"] if ident in state["pending"] and ident != active]
    state["pending"] = ([active] if active is not None else []) + future


def map_penalty(attack_count: int, agile: bool = False) -> int:
    if attack_count < 0:
        raise ValueError("Attack counter cannot be negative")
    return 0 if attack_count == 0 else (-4 if agile else -5) if attack_count == 1 else (-8 if agile else -10)


def apply_damage(actor: dict, amount: int) -> None:
    if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0 or actor["current_hp"] is None:
        raise ValueError("Enter a nonnegative amount and set HP first")
    absorbed = min(actor["temp_hp"], amount)
    actor["temp_hp"] -= absorbed
    actor["current_hp"] = max(0, actor["current_hp"] - (amount - absorbed))


def apply_healing(actor: dict, amount: int) -> None:
    if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0 or actor["current_hp"] is None or actor["max_hp"] is None:
        raise ValueError("Enter a nonnegative amount and set HP first")
    actor["current_hp"] = min(actor["max_hp"], actor["current_hp"] + amount)


def apply(state: dict, command: dict) -> dict:
    """Apply one validated user command to a copy; callers persist only on success."""
    result = deepcopy(state)
    op = command.get("op")
    if op == "rename_combat":
        name = (command.get("name") or "").strip()
        if not name or len(name) > 120:
            raise ValueError("Enter a combat name of at most 120 characters")
        result["name"] = name
    elif op == "end":
        result["status"] = "ended"
    elif op == "resume":
        result["status"] = "active"
    elif op == "save":
        pass
    elif result["status"] == "ended":
        raise ValueError("Resume this combat before changing it")
    elif op == "add":
        quantity = command.get("quantity", 1)
        if not isinstance(quantity, int) or isinstance(quantity, bool) or not 1 <= quantity <= 100:
            raise ValueError("Quantity must be from 1 to 100")
        for _ in range(quantity):
            add_combatant(result, command.get("name") or "", command.get("type") or "", command.get("initiative"), command.get("max_hp"), command.get("current_hp"), command.get("notes") or "")
    elif op == "next_turn":
        next_turn(result)
    elif op == "delay":
        delay(result)
    elif op == "reenter":
        reenter_after(result, command.get("combatant_id"), command.get("after_id"))
    elif op == "move":
        move(result, command.get("combatant_id"), command.get("direction"))
    else:
        actor = combatant(result, command.get("combatant_id"))
        if op == "remove":
            ident = actor["id"]
            was_active = ident == result["active_id"]
            result["combatants"].remove(actor)
            result["order"].remove(ident)
            if ident in result["delayed"]:
                result["delayed"].remove(ident)
                result["delayed_since_round"].pop(str(ident), None)
            if ident in result["pending"]:
                result["pending"].remove(ident)
            if was_active:
                if not result["pending"] and result["order"]:
                    result["round"] += 1
                    result["pending"] = result["order"].copy()
                if result["pending"]:
                    _start_turn(result, result["pending"][0])
                else:
                    result["active_id"] = None
        elif op == "set_name":
            name = (command.get("name") or "").strip()
            if not name or len(name) > 120:
                raise ValueError("Enter a combatant name of at most 120 characters")
            actor["name"] = name
        elif op == "set_type":
            if command.get("type") not in KINDS:
                raise ValueError("Choose PC, NPC, or monster")
            actor["type"] = command["type"]
            _resort(result)
        elif op == "set_initiative":
            value = command.get("initiative")
            if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
                raise ValueError("Initiative must be an integer")
            actor["initiative"] = value
            _resort(result)
        elif op == "set_hp":
            maximum = command.get("max_hp", actor["max_hp"])
            current = command.get("current_hp", actor["current_hp"])
            temporary = command.get("temp_hp", actor["temp_hp"])
            if maximum is not None and (not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1):
                raise ValueError("Maximum HP must be positive")
            if current is not None and (not isinstance(current, int) or isinstance(current, bool) or maximum is None or not 0 <= current <= maximum):
                raise ValueError("Current HP must be between 0 and maximum HP")
            if temporary is None or not isinstance(temporary, int) or isinstance(temporary, bool) or temporary < 0:
                raise ValueError("Temporary HP cannot be negative")
            actor.update(max_hp=maximum, current_hp=current, temp_hp=temporary)
        elif op == "damage":
            apply_damage(actor, command.get("amount"))
        elif op == "heal":
            apply_healing(actor, command.get("amount"))
        elif op == "actions":
            if actor["id"] != result["active_id"]:
                raise ValueError("Actions can be tracked only on the active turn")
            amount = command.get("amount")
            if not isinstance(amount, int) or isinstance(amount, bool):
                raise ValueError("Enter an integer action adjustment")
            value = actor["actions_remaining"] + amount
            if not 0 <= value <= 20:
                raise ValueError("Actions must be between 0 and 20")
            actor["actions_remaining"] = value
            result["turns_started"] = True
        elif op == "reaction":
            if actor["id"] in result["delayed"]:
                raise ValueError("Delayed combatants cannot use reactions until they reenter")
            amount = command.get("amount")
            if not isinstance(amount, int) or isinstance(amount, bool):
                raise ValueError("Enter an integer reaction adjustment")
            value = actor["reaction_remaining"] + amount
            if not 0 <= value <= 20:
                raise ValueError("Reactions must be between 0 and 20")
            actor["reaction_remaining"] = value
            result["turns_started"] = True
        elif op == "attack":
            if actor["id"] != result["active_id"]:
                raise ValueError("MAP counts attacks only on the active turn")
            amount = command.get("amount")
            if not isinstance(amount, int) or isinstance(amount, bool):
                raise ValueError("Enter an integer attack adjustment")
            value = actor["attack_count"] + amount
            if not 0 <= value <= 20:
                raise ValueError("Attack counter must be between 0 and 20")
            actor["attack_count"] = value
            result["turns_started"] = True
        elif op == "ready":
            if actor["id"] != result["active_id"] or actor["actions_remaining"] < 2:
                raise ValueError("Ready needs the active combatant and two actions")
            actor["actions_remaining"] -= 2
            next_turn(result)
        elif op == "notes":
            notes = command.get("notes") or ""
            if len(notes) > 1000:
                raise ValueError("Notes are too long")
            actor["notes"] = notes
        elif op == "add_effect":
            label = (command.get("label") or "").strip()
            duration = (command.get("duration") or "").strip()
            if not label or len(label) > 80 or len(duration) > 100:
                raise ValueError("Enter a short effect label and optional duration")
            actor["effects"].append({"label": label, "duration": duration})
        elif op == "remove_effect":
            index = command.get("effect_index")
            if index is None or not 0 <= index < len(actor["effects"]):
                raise ValueError("Effect not found")
            actor["effects"].pop(index)
        else:
            raise ValueError("Unknown combat command")
    return result
