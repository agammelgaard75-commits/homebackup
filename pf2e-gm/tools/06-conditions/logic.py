"""Pure condition effects and turn reminders; no database or browser dependencies."""

from collections import defaultdict
import re

IMPLIES = {
    "grabbed": ("off-guard", "immobilized"),
    "restrained": ("off-guard", "immobilized"),
    "prone": ("off-guard",),
    "paralyzed": ("off-guard",),
    "confused": ("off-guard",),
    "encumbered": ("clumsy",),
    "unconscious": ("blinded", "off-guard"),
    "dying": ("unconscious",),
}


def visible(instances: list[dict]) -> list[dict]:
    """Highest valued source applies; implied labels are derived, never stored."""
    groups = defaultdict(list)
    for item in instances:
        groups[item["slug"]].append(item)
    result = {}
    for slug, sources in groups.items():
        chosen = max(sources, key=lambda row: row.get("value") or 0)
        round_sources = [row for row in sources if row.get("duration_kind") == "rounds" and row.get("rounds_remaining") is not None]
        result[slug] = {"slug": slug, "value": chosen.get("value"),
                        "source_ids": [row["id"] for row in sources],
                        "round_counts": [row["rounds_remaining"] for row in round_sources],
                        "other_duration_sources": len(sources) - len(round_sources),
                        "implied_by": [], "overridden": False}
    if "restrained" in result and "grabbed" in result:
        result["grabbed"]["overridden"] = True
    if "blinded" in result and "dazzled" in result:
        result["dazzled"]["overridden"] = True
    queue = [slug for slug, row in result.items() if not row["overridden"]]
    visited = set()
    while queue:
        parent = queue.pop(0)
        if parent in visited:
            continue
        visited.add(parent)
        for child in IMPLIES.get(parent, ()):
            row = result.setdefault(child, {"slug": child, "value": 1 if child == "clumsy" else None,
                                            "source_ids": [], "round_counts": [], "other_duration_sources": 0,
                                            "implied_by": [], "overridden": False})
            if parent not in row["implied_by"]:
                row["implied_by"].append(parent)
            if child == "clumsy":
                row["value"] = max(row.get("value") or 0, 1)
            queue.append(child)
    return sorted(result.values(), key=lambda row: row["slug"])


def penalty_summary(instances: list[dict]) -> dict:
    """Only known penalties; never infer a complete character statistic."""
    current = {row["slug"]: row for row in visible(instances) if not row["overridden"]}
    def value(slug):
        row = current.get(slug)
        return (row.get("value") or 1) if row else 0
    general = max(value("frightened"), value("sickened"))
    return {
        "all_checks_and_dcs_status": -general,
        "ac_status": -max(general, value("clumsy"), 1 if "fatigued" in current else 0, 4 if "unconscious" in current else 0),
        "ac_circumstance": -2 if "off-guard" in current else 0,
        "attack_circumstance": -2 if "prone" in current else 0,
        "dexterity_status": -max(general, value("clumsy")),
        "strength_status": -max(general, value("enfeebled")),
        "constitution_status": -max(general, value("drained")),
        "mental_status": -max(general, value("stupefied")),
        "fortitude_status": -max(general, value("drained"), 1 if "fatigued" in current else 0),
        "reflex_status": -max(general, value("clumsy"), 1 if "fatigued" in current else 0, 4 if "unconscious" in current else 0),
        "will_status": -max(general, value("stupefied"), 1 if "fatigued" in current else 0),
        "perception_status": -max(general, 4 if "unconscious" in current else 0),
        "notes": "Use only the largest applicable penalty of each type. Check whether Off-Guard applies to the attacker. Other rules can change these values.",
    }


def upcoming(instances: list[dict]) -> list[dict]:
    """List tracked triggers without guessing when a turn will occur."""
    result = []
    for row in instances:
        kind = row.get("duration_kind")
        if kind in {"start_turn", "end_turn", "rounds"}:
            event = row.get("duration_event") if kind == "rounds" else kind.split("_")[0]
            result.append({"instance_id": row["id"], "slug": row["slug"],
                           "controller_id": row.get("controller_id"), "event": event,
                           "rounds_remaining": row.get("rounds_remaining")})
    return result


def zero_round_reminders(instances: list[dict]) -> list[dict]:
    """Keep finished round counters visible until their source is removed."""
    return [{"instance_id": row["id"], "kind": "round_expired", "slug": row["slug"],
             "source": row.get("source") or "", "controller_id": row.get("controller_id"),
             "duration_event": row.get("duration_event"),
             "text": f"{row['slug'].replace('-', ' ').title()} (0 rounds): counter finished. Review the effect; remove it manually when it ends."}
            for row in instances if row.get("duration_kind") == "rounds" and row.get("rounds_remaining") == 0]


def action_guidance(instances: list[dict]) -> dict:
    current = {row["slug"]: row for row in visible(instances) if not row["overridden"]}
    slowed = current.get("slowed", {}).get("value") or 0
    stunned = current.get("stunned", {}).get("value") or 0
    duration_stunned = any(row["slug"] == "stunned" and row.get("value") is None for row in instances)
    quickened_sources = [row for row in instances if row["slug"] == "quickened"]
    extra = int(bool(quickened_sources))
    loss = 3 + extra if duration_stunned else min(3 + extra, max(slowed, stunned))
    restrictions = sorted({row.get("quickened_restriction", "").strip() for row in quickened_sources if row.get("quickened_restriction", "").strip()})
    if duration_stunned:
        extra = 0
    return {"normal_actions": max(0, 3 - loss), "quickened_extra": extra,
            "total_guidance": max(0, 3 + extra - loss),
            "actions_lost": loss, "slowed": slowed, "stunned": stunned, "quickened_restrictions": restrictions,
            "note": "At turn start, Stunned actions count toward Slowed's lost actions; do not add the two values. Quickened grants at most one restricted extra action. When actions differ, the GM chooses which are lost, including the quickened action. Adjust the Combat Tracker manually."}


def persistent_groups(instances: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for item in instances:
        if item["slug"] == "persistent-damage":
            groups[item["damage_type"].lower()].append(item)
    result = []
    for damage_type, sources in groups.items():
        amounts = [row["damage_expression"] for row in sources]
        fixed = all(re.fullmatch(r"\d+", amount or "") for amount in amounts)
        chosen = max(sources, key=lambda row: int(row["damage_expression"])) if fixed else sources[0] if len(set(amounts)) == 1 else None
        result.append({"damage_type": damage_type, "sources": [row["id"] for row in sources],
                       "active_expression": chosen["damage_expression"] if chosen else None,
                       "gm_choice_needed": chosen is None,
                       "note": "Apply only the higher same-type amount. If fixed and dice cannot be compared clearly, the GM chooses the source."})
    return sorted(result, key=lambda row: row["damage_type"])


def reminders(instances: list[dict], event: str, actor_id: int | None, target_id: int | None) -> list[dict]:
    """Return prompts only. No change occurs before GM confirmation."""
    if event not in {"start", "end"}:
        raise ValueError("Event must be start or end")
    prompts = []
    for row in instances:
        own_turn = actor_id == target_id
        slug = row["slug"]
        kind = row.get("duration_kind")
        if kind == f"{event}_turn" and row.get("controller_id") == actor_id:
            prompts.append({"instance_id": row["id"], "kind": "expiration", "text": f"Review {slug.replace('-', ' ').title()}: duration reaches {event} of controller's turn."})
        if kind == "rounds" and row.get("rounds_remaining", 0) > 0 and row.get("controller_id") == actor_id and row.get("duration_event") == event:
            prompts.append({"instance_id": row["id"], "kind": "round", "text": f"Review {slug.replace('-', ' ').title()}: {row['rounds_remaining']} round(s) remaining; tick at this turn event."})
    if actor_id == target_id and event == "start":
        for slug in {row["slug"] for row in instances} & {"slowed", "quickened"}:
            row = next(item for item in instances if item["slug"] == slug)
            prompts.append({"instance_id": row["id"], "kind": "actions", "text": f"Review {slug.title()} when this combatant regains actions; adjust actions manually."})
        stunned = [row for row in instances if row["slug"] == "stunned"]
        if stunned:
            strongest = max(stunned, key=lambda row: row.get("value") or 0)
            if strongest.get("value") is None:
                prompts.append({"instance_id": strongest["id"], "kind": "actions", "text": "Duration-based Stunned prevents acting until its duration ends; review the source."})
            else:
                available = 3 + int(any(row["slug"] == "quickened" for row in instances))
                consumed = min(strongest["value"], available)
                prompts.append({"instance_id": strongest["id"], "kind": "stunned_reduce", "amount": consumed,
                                "text": f"Stunned {strongest['value']} uses {consumed} action(s) at turn start. Confirm reducing Stunned by {consumed}; count those lost actions toward Slowed."})
    if event == "end" and actor_id == target_id:
        frightened = [row for row in instances if row["slug"] == "frightened"]
        if frightened:
            strongest = max(frightened, key=lambda row: row["value"])
            prompts.append({"instance_id": strongest["id"], "kind": "reduce", "text": f"Reduce Frightened {strongest['value']} by 1? Check exceptions from its source."})
        for group in persistent_groups(instances):
            if group["gm_choice_needed"]:
                prompts.append({"instance_id": group["sources"][0], "kind": "persistent_choice",
                                "text": f"Persistent {group['damage_type']}: compare the same-type sources and apply only the stronger one; then make its recovery check. Choose the source in Conditions Tracker."})
            else:
                chosen = next(row for row in instances if row["id"] in group["sources"] and row["damage_expression"] == group["active_expression"])
                prompts.append({"instance_id": chosen["id"], "kind": "persistent",
                                "text": f"Apply {chosen['damage_expression']} persistent {group['damage_type']} damage manually, then attempt DC {chosen['recovery_dc']} recovery flat check. Do not add same-type sources."})
    return prompts


def reduce_all_sources(instances: list[dict], slug: str, amount: int = 1) -> list[dict]:
    """A reduction to a valued condition reduces every source of that condition."""
    if amount < 1:
        raise ValueError("Reduction must be positive")
    return [{**row, "value": max(0, (row.get("value") or 0) - amount)} if row["slug"] == slug else row for row in instances]
