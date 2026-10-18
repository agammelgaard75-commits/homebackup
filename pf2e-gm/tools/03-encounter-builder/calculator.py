"""Deterministic GM Core encounter budgets and creature XP."""

BASE_BUDGETS = {"Trivial": 40, "Low": 60, "Moderate": 80, "Severe": 120, "Extreme": 160}
CHARACTER_ADJUSTMENTS = {"Trivial": 10, "Low": 20, "Moderate": 20, "Severe": 30, "Extreme": 40}
CREATURE_XP = {-4: 10, -3: 15, -2: 20, -1: 30, 0: 40, 1: 60, 2: 80, 3: 120, 4: 160}
TEMPLATES = (
    ("two_equal", "Two equal-level creatures", (("Equal-level creature", 0, 2),)),
    ("equal_and_four_weak", "One equal-level and four four levels lower", (("Equal-level creature", 0, 1), ("Lower-level creature", -4, 4))),
    ("strong_and_equal", "One two levels higher and one equal-level", (("Higher-level creature", 2, 1), ("Equal-level creature", 0, 1))),
)


def budget(difficulty: str, party_size: int) -> int:
    if difficulty not in BASE_BUDGETS or not 2 <= party_size <= 8:
        raise ValueError("Choose a listed difficulty and a party size from 2 to 8")
    return BASE_BUDGETS[difficulty] + (party_size - 4) * CHARACTER_ADJUSTMENTS[difficulty]


def creature_xp(party_level: int, creature_level: int) -> int | None:
    if not 1 <= party_level <= 20 or not -1 <= creature_level <= 25:
        raise ValueError("Party or creature level is out of range")
    return CREATURE_XP.get(creature_level - party_level)


def available_templates(party_level: int) -> list[dict]:
    if not 1 <= party_level <= 20:
        raise ValueError("Party level must be from 1 to 20")
    return [
        {
            "id": key,
            "name": name,
            "creatures": [
                {"name": label, "level": party_level + offset, "quantity": quantity, "notes": "", "url": ""}
                for label, offset, quantity in groups
            ],
        }
        for key, name, groups in TEMPLATES
        if all(-1 <= party_level + offset <= 25 for _, offset, _ in groups)
    ]


def comparison(total: int, budgets: dict[str, int]) -> str:
    matches = [name for name, value in budgets.items() if value == total]
    if matches:
        return "Matches " + " and ".join(matches) + " target" + ("s" if len(matches) > 1 else "") + "."
    if total < min(budgets.values()):
        return "Below the Trivial target."
    if total > max(budgets.values()):
        return "Above the Extreme target."
    lower = max(value for value in budgets.values() if value < total)
    upper = min(value for value in budgets.values() if value > total)
    lower_names = "/".join(name for name, value in budgets.items() if value == lower)
    upper_names = "/".join(name for name, value in budgets.items() if value == upper)
    return f"Between {lower_names} ({lower} XP) and {upper_names} ({upper} XP) targets."


def calculate(party_level: int, party_size: int, target: str, creatures: list[dict]) -> dict:
    if not 1 <= party_level <= 20:
        raise ValueError("Party level must be from 1 to 20")
    budgets = {name: budget(name, party_size) for name in BASE_BUDGETS}
    if target not in budgets:
        raise ValueError("Choose a listed difficulty")
    groups = []
    unsupported = False
    high_levels = False
    weak_count = 0
    for creature in creatures:
        level = creature["level"]
        quantity = creature["quantity"]
        if not -1 <= level <= 25 or quantity < 1:
            raise ValueError("Creature level must be -1 to 25 and quantity must be positive")
        each = creature_xp(party_level, level)
        if each is None:
            unsupported = True
        if level - party_level >= 3:
            high_levels = True
        if level - party_level <= -3:
            weak_count += quantity
        groups.append({**creature, "relative_level": level - party_level, "xp_each": each, "xp_total": each * quantity if each is not None else None})
    total = None if unsupported else sum(group["xp_total"] for group in groups)
    selected = budgets[target]
    warnings = []
    if unsupported:
        warnings.append("A creature is outside the supported party level −4 to +4 XP table. Change its level before using the total.")
    if target == "Severe":
        warnings.append("Severe encounters can be deadly, especially for an unprepared party.")
    if target == "Extreme":
        warnings.append("Extreme encounters risk defeating the entire party.")
    if high_levels:
        warnings.append("A creature three or more levels above the party can be particularly dangerous.")
    if weak_count >= 4:
        warnings.append("Many weaker enemies may be less threatening individually; review how their abilities work together.")
    if total is not None and total > selected:
        warnings.append("This encounter exceeds the selected XP target. Review its difficulty before play.")
    if total is not None and total == 0:
        warnings.append("Add creatures to build an encounter.")
    warnings.append("XP targets are planning guides; terrain, tactics, and creature abilities also affect difficulty.")
    if target == "Trivial":
        award = "Trivial encounters normally award no XP. Use GM Core guidance if you award XP for one."
        standard_award = None
    else:
        standard_award = BASE_BUDGETS[target]
        award = f"A standard {target.lower()} encounter awards {standard_award} XP to each character, regardless of party size. XP is not divided among characters."
        if total is not None and total > 0 and total != selected:
            award += " This encounter differs from the selected target. For a custom award, start with its creature XP total, award each character rather than dividing by party size, and consult GM Core XP Awards for any adjustment."
    return {
        "target": target,
        "party_level": party_level,
        "party_size": party_size,
        "base_budget": BASE_BUDGETS[target],
        "party_adjustment": selected - BASE_BUDGETS[target],
        "adjusted_target": selected,
        "budgets": budgets,
        "creatures": groups,
        "total_xp": total,
        "remaining_xp": selected - total if total is not None else None,
        "difference_from_target": total - selected if total is not None else None,
        "comparison": comparison(total, budgets) if total is not None else "Unavailable until unsupported creatures are corrected.",
        "standard_award_xp": standard_award,
        "award_guidance": award,
        "warnings": warnings,
    }
