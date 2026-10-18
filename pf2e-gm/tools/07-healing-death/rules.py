"""Verified PF2e Remaster healing and dying calculations, independent of storage/UI."""

RANKS = {"trained": 1, "expert": 2, "master": 3, "legendary": 4}
TREAT_OPTIONS = {15: ("trained", 0), 20: ("expert", 10), 30: ("master", 30), 40: ("legendary", 50)}
DEGREES = ("critical_failure", "failure", "success", "critical_success")


def death_threshold(doomed: int) -> int:
    if not isinstance(doomed, int) or isinstance(doomed, bool) or doomed < 0:
        raise ValueError("Doomed must be a nonnegative integer")
    return max(0, 4 - doomed)


def check_degree(roll: int, modifier: int, dc: int) -> str:
    if not isinstance(roll, int) or isinstance(roll, bool) or not 1 <= roll <= 20:
        raise ValueError("Natural d20 roll must be 1–20")
    if not isinstance(modifier, int) or isinstance(modifier, bool) or not isinstance(dc, int) or isinstance(dc, bool) or dc < 1:
        raise ValueError("Enter an integer modifier and positive DC")
    result = roll + modifier
    degree = 3 if result >= dc + 10 else 2 if result >= dc else 0 if result <= dc - 10 else 1
    if roll == 20:
        degree = min(3, degree + 1)
    elif roll == 1:
        degree = max(0, degree - 1)
    return DEGREES[degree]


def knockout(wounded: int, doomed: int, critical: bool = False, own_critical_failure: bool = False,
             nonlethal: bool = False) -> dict:
    if wounded < 0:
        raise ValueError("Wounded cannot be negative")
    value = 0 if nonlethal else (2 if critical or own_critical_failure else 1) + wounded
    threshold = death_threshold(doomed)
    return {"dying": value, "unconscious": True, "death_threshold": threshold,
            "fatal": not nonlethal and value >= threshold,
            "initiative_offer": True}


def recovery(dying: int, doomed: int, roll: int) -> dict:
    if not 1 <= dying <= 99:
        raise ValueError("Recovery requires a Dying value")
    dc = 10 + dying
    degree = check_degree(roll, 0, dc)
    change = {"critical_success": -2, "success": -1, "failure": 1, "critical_failure": 2}[degree]
    resulting = max(0, dying + change)
    return {"dc": dc, "roll": roll, "degree": degree, "change": change,
            "dying": resulting, "loses_dying": resulting == 0,
            "death_threshold": death_threshold(doomed), "fatal": resulting >= death_threshold(doomed)}


def damage_while_dying(dying: int, doomed: int, critical: bool = False,
                       own_critical_failure: bool = False) -> dict:
    if not 1 <= dying <= 99:
        raise ValueError("Damage while dying requires a Dying value")
    resulting = dying + (2 if critical or own_critical_failure else 1)
    return {"dying": resulting, "change": resulting - dying,
            "death_threshold": death_threshold(doomed), "fatal": resulting >= death_threshold(doomed)}


def first_aid(dying: int, doomed: int, degree: str) -> dict:
    if not 1 <= dying <= 99 or degree not in DEGREES:
        raise ValueError("Choose a Dying value and degree of success")
    resulting = dying + 1 if degree == "critical_failure" else 0 if degree in {"success", "critical_success"} else dying
    return {"dc": 15 + dying, "degree": degree, "dying": resulting,
            "loses_dying": resulting == 0, "death_threshold": death_threshold(doomed),
            "fatal": resulting >= death_threshold(doomed)}


def treatment_option(proficiency: str, dc: int) -> dict:
    if proficiency not in RANKS or dc not in TREAT_OPTIONS:
        raise ValueError("Choose a trained Medicine rank and listed DC")
    minimum, bonus = TREAT_OPTIONS[dc]
    if RANKS[proficiency] < RANKS[minimum]:
        raise ValueError(f"DC {dc} requires {minimum} Medicine")
    return {"minimum_rank": minimum, "dc": dc, "bonus": bonus,
            "success_dice": "2d8", "critical_success_dice": "4d8"}


def treatment(proficiency: str, dc: int, degree: str, dice_total: int | None,
              kind: str, continue_hour: bool = False) -> dict:
    option = treatment_option(proficiency, dc)
    if kind not in {"treat", "battle"} or degree not in DEGREES:
        raise ValueError("Choose Treat Wounds or Battle Medicine and a valid degree")
    if continue_hour and (kind != "treat" or degree not in {"success", "critical_success"}):
        raise ValueError("Only successful Treat Wounds can continue to one hour")
    if degree == "failure":
        if dice_total is not None:
            raise ValueError("A failure has no healing or damage dice")
        amount, dice, bonus = 0, "", 0
    else:
        dice, minimum, maximum = ("1d8", 1, 8) if degree == "critical_failure" else ("4d8", 4, 32) if degree == "critical_success" else ("2d8", 2, 16)
        if not isinstance(dice_total, int) or isinstance(dice_total, bool) or not minimum <= dice_total <= maximum:
            raise ValueError(f"Enter the rolled {dice} total ({minimum}–{maximum})")
        bonus = 0 if degree == "critical_failure" else option["bonus"]
        amount = dice_total + bonus
        if continue_hour:
            amount *= 2
    return {"kind": kind, "degree": degree, "dc": dc, "dice": dice,
            "dice_total": dice_total, "bonus": bonus, "amount": amount,
            "hp_change": -amount if degree == "critical_failure" else amount,
            "duration_minutes": 0 if kind == "battle" else 60 if continue_hour else 10,
            "immunity_minutes": 1440 if kind == "battle" else 60,
            "removes_wounded_if_hp_restored": kind == "treat" and degree in {"success", "critical_success"}}
