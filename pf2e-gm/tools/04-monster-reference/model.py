"""Phase 11 monster schema and derived, application-only completeness labels."""

from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Entry(BaseModel):
    """Spellcasting entry; its existing optional shape remains supported."""
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    modifier: int | None = None
    damage: str = Field(default="", max_length=200)
    usable_in_combat: bool = False
    offensive: bool = False

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Entry name cannot be blank")
        return value.strip()


class Speed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str = Field(default="land", min_length=1, max_length=50)
    feet: int = Field(gt=0)


class Attack(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    type: str | None = Field(default=None, min_length=1, max_length=40)
    actions: int | str | None = None
    bonus: int | None = None
    traits: list[str] = Field(default_factory=list)
    damage: str = Field(default="", max_length=200)
    effect: str = Field(default="", max_length=2000)

    @model_validator(mode="before")
    @classmethod
    def old_entry_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        for old, new in (("modifier", "bonus"), ("description", "effect")):
            if old in data:
                previous = data.pop(old)
                if new in data and data[new] != previous:
                    raise ValueError(f"Conflicting {new} values")
                data[new] = previous
        data.pop("usable_in_combat", None)
        data.pop("offensive", None)
        return data

    @field_validator("name")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Attack name cannot be blank")
        return value.strip()

    @field_validator("type")
    @classmethod
    def clean_type(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Attack type cannot be blank")
        return value.strip() if value is not None else None

    @field_validator("actions")
    @classmethod
    def check_actions(cls, value: int | str | None) -> int | str | None:
        if value is None:
            return None
        if isinstance(value, bool) or (isinstance(value, int) and value < 1):
            raise ValueError("Attack actions must be positive or a nonblank description")
        if isinstance(value, str) and not value.strip():
            raise ValueError("Attack actions cannot be blank")
        return value


class Ability(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    actions: int | str | None = None
    traits: list[str] = Field(default_factory=list)
    trigger: str | None = None
    requirements: str | None = None
    description: str = Field(default="", max_length=2000)
    dc: int | None = None

    @model_validator(mode="before")
    @classmethod
    def old_entry_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if data.pop("usable_in_combat", False) and "actions" not in data:
            data["actions"] = "combat use; action cost not entered"
        data.pop("offensive", None)
        modifier = data.pop("modifier", None)
        damage = data.pop("damage", "")
        legacy_details = [part for part in (f"Modifier {modifier:+d}" if modifier is not None else "", f"Damage {damage}" if damage else "") if part]
        if legacy_details:
            data["description"] = "; ".join(part for part in (data.get("description", ""), *legacy_details) if part)
        return data

    @field_validator("name")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Ability name cannot be blank")
        return value.strip()

    @field_validator("actions")
    @classmethod
    def check_actions(cls, value: int | str | None) -> int | str | None:
        if value is None:
            return None
        if isinstance(value, bool) or (isinstance(value, int) and value < 1):
            raise ValueError("Ability actions must be positive or a nonblank description")
        if isinstance(value, str) and not value.strip():
            raise ValueError("Ability actions cannot be blank")
        return value


class Monster(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=120)
    level: int = Field(strict=True, ge=-1, le=25)
    max_hp: int = Field(strict=True, gt=0)
    ac: int | None = None
    fortitude: int | None = None
    reflex: int | None = None
    will: int | None = None
    perception: int | None = None
    traits: list[str] = Field(default_factory=list)
    senses: list[str] = Field(default_factory=list)
    skills: dict[str, int] = Field(default_factory=dict)
    speeds: list[Speed] = Field(default_factory=list)
    attacks: list[Attack] = Field(default_factory=list)
    abilities: list[Ability] = Field(default_factory=list)
    spellcasting: list[Entry] = Field(default_factory=list)
    source_book: str = Field(default="", max_length=120)
    source_page: int | None = Field(default=None, gt=0)
    source_url: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="before")
    @classmethod
    def import_compatibility(cls, value: Any) -> Any:
        return normalize_import(value)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Monster name cannot be blank")
        return value.strip()

    @field_validator("source_url")
    @classmethod
    def check_url(cls, value: str) -> str:
        if value and (urlparse(value).scheme not in {"http", "https"} or not urlparse(value).netloc):
            raise ValueError("Source URL must use http or https")
        return value

    @field_validator("traits", "senses")
    @classmethod
    def clean_terms(cls, value: list[str]) -> list[str]:
        return [term.strip() for term in value if term.strip()]


def normalize_import(raw: Any) -> dict:
    """Accept canonical v1 JSON and a narrow legacy defenses.hp shape."""
    if not isinstance(raw, dict):
        raise ValueError("Monster must be a JSON object")
    data = dict(raw)
    if data.get("schema_version", 1) != 1:
        raise ValueError("Unsupported monster schema version")
    data.pop("id", None)
    data.pop("completeness", None)  # Derived view metadata is never imported.
    data.pop("missing_for_next", None)
    defenses = data.pop("defenses", None)
    if defenses is not None:
        if not isinstance(defenses, dict):
            raise ValueError("defenses must be an object")
        old = dict(defenses)
        for legacy, canonical in (("hp", "max_hp"), ("ac", "ac"), ("fortitude", "fortitude"), ("reflex", "reflex"), ("will", "will")):
            if legacy in old:
                value = old.pop(legacy)
                if canonical in data and data[canonical] != value:
                    raise ValueError(f"Conflicting {canonical} values")
                data[canonical] = value
        if old:
            raise ValueError(f"Unsupported defenses fields: {', '.join(old)}")
    if "speed" in data and "speeds" not in data:
        speed = data.pop("speed")
        data["speeds"] = [{"type": "land", "feet": speed}] if speed is not None else []
    return data


def completeness(monster: Monster | dict) -> dict:
    value = monster.model_dump() if isinstance(monster, Monster) else monster
    missing = [label for key, label in (("ac", "AC"), ("fortitude", "Fortitude"), ("reflex", "Reflex"), ("will", "Will")) if value.get(key) is None]
    if not value.get("speeds"):
        missing.append("a movement Speed")
    if not (value.get("attacks") or any(row.get("offensive") for row in value.get("spellcasting", [])) or any(
        row.get("actions") not in (None, "passive") or row.get("dc") is not None or row.get("trigger")
        for row in value.get("abilities", []))):
        missing.append("an attack, offensive spell, or usable combat ability")
    if missing:
        return {"level": "Basic", "missing_for_next": missing, "next_level": "Combat Ready"}
    detail = bool(value.get("skills") or value.get("senses") or value.get("traits") or value.get("abilities") or value.get("spellcasting") or value.get("source_book") or value.get("source_page") or value.get("source_url"))
    return {"level": "Detailed" if detail else "Combat Ready", "missing_for_next": [] if detail else ["skills, senses, traits, special abilities, spellcasting, or a source reference"], "next_level": None if detail else "Detailed"}
