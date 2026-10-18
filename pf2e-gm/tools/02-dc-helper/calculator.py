"""Deterministic PF2e Remaster DC and degree-of-success calculations.

DCs by level are transcribed from GM Core, page 52, Table 10-5:
https://2e.aonprd.com/Rules.aspx?ID=2629
"""

SIMPLE_DCS = {
    "Untrained": 10,
    "Trained": 15,
    "Expert": 20,
    "Master": 30,
    "Legendary": 40,
}

# Index is the level of the task or subject, 0 through 25.
LEVEL_DCS = (
    14, 15, 16, 18, 19, 20, 22, 23, 24, 26, 27, 28, 30,
    31, 32, 34, 35, 36, 38, 39, 40, 42, 44, 46, 48, 50,
)

ADJUSTMENTS = {
    "Incredibly easy": -10,
    "Very easy": -5,
    "Easy": -2,
    "Standard": 0,
    "Hard": 2,
    "Very hard": 5,
    "Incredibly hard": 10,
}

DEGREES = ("Critical failure", "Failure", "Success", "Critical success")


def _integer(value: int, name: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")
    return value


def base_dc(mode: str, *, proficiency: str | None = None,
            level: int | None = None, manual_dc: int | None = None) -> int:
    """Choose the base DC without considering a character's level or skill."""
    if mode == "simple":
        if proficiency not in SIMPLE_DCS:
            raise ValueError("Choose a valid proficiency difficulty")
        return SIMPLE_DCS[proficiency]
    if mode == "level":
        _integer(level, "Level")
        if not 0 <= level <= 25:
            raise ValueError("Level must be from 0 to 25")
        return LEVEL_DCS[level]
    if mode == "manual":
        _integer(manual_dc, "Manual DC")
        if manual_dc <= 0:
            raise ValueError("Manual DC must be positive")
        return manual_dc
    raise ValueError("Choose a valid DC method")


def adjusted_dc(base: int, difficulty: str) -> tuple[int, int]:
    _integer(base, "Base DC")
    if difficulty not in ADJUSTMENTS:
        raise ValueError("Choose a valid difficulty adjustment")
    adjustment = ADJUSTMENTS[difficulty]
    return adjustment, base + adjustment


def check_result(roll: int, modifier: int, dc: int) -> tuple[int, int, str]:
    """Return check total, difference from DC, and final degree of success."""
    _integer(roll, "Natural roll")
    _integer(modifier, "Total modifier")
    _integer(dc, "DC")
    if not 1 <= roll <= 20:
        raise ValueError("Natural roll must be from 1 to 20")
    total = roll + modifier
    difference = total - dc
    if difference >= 10:
        degree = 3
    elif difference >= 0:
        degree = 2
    elif difference <= -10:
        degree = 0
    else:
        degree = 1
    if roll == 20:
        degree = min(3, degree + 1)
    elif roll == 1:
        degree = max(0, degree - 1)
    return total, difference, DEGREES[degree]
