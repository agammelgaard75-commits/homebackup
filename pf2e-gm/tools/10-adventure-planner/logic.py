"""Small, deterministic planning helpers. Scene order never controls availability."""


def time_budget(planned_minutes: int, scene_minutes: list[int]) -> dict:
    if planned_minutes < 0 or any(value < 0 for value in scene_minutes):
        raise ValueError("Durations must be nonnegative")
    used = sum(scene_minutes)
    return {"planned_minutes": planned_minutes, "scene_minutes": used,
            "buffer_minutes": planned_minutes - used, "over_budget": used > planned_minutes}


def recap(session: dict, scenes: list[dict], clues: list[dict], items: list[dict],
          events: list[dict], encounters: list[dict]) -> str:
    """Summarize recorded state only; leave an editable section for future prep."""
    lines = [f"# {session['title']} recap"]
    groups = (
        ("Completed scenes", [s["title"] for s in scenes if s["status"] == "completed"]),
        ("Discovered clues", [c["name"] for c in clues if c["discovered"]]),
        ("Obtained items", [i["name"] for i in items if i["obtained"]]),
        ("Player decisions", [e["text"] for e in events if e["kind"] == "decision"]),
        ("Completed encounters", [e["name"] for e in encounters if e["completed"] and not e["missing"]]),
        ("Unresolved objectives", [i["name"] for i in items if i["kind"] == "objective" and not i["obtained"]]),
    )
    for heading, values in groups:
        if values:
            lines += ["", f"## {heading}", *[f"- {value}" for value in values]]
    if session.get("actual_notes"):
        lines += ["", "## Session notes", session["actual_notes"]]
    if session.get("next_session_notes"):
        lines += ["", "## GM notes for next session", session["next_session_notes"]]
    return "\n".join(lines) + "\n"


def markdown(adventure: dict) -> str:
    """Readable local export of the adventure snapshot."""
    root = adventure["adventure"]
    lines = [f"# {root['title']}"]
    for label, key in (("Description", "description"), ("Starting situation", "starting_situation"),
                       ("Main objective", "main_objective"), ("Secrets", "secrets"),
                       ("Possible outcomes", "outcomes"), ("GM notes", "gm_notes")):
        if root.get(key):
            lines += ["", f"**{label}:** {root[key]}"]
    lines += ["", "## Scenes"]
    for scene in adventure["scenes"]:
        lines += ["", f"### {scene['title']} ({scene['type']}; {scene['status']})"]
        for key in ("location", "purpose", "description", "complications", "notes"):
            if scene.get(key):
                lines.append(f"- {key.title()}: {scene[key]}")
        if scene.get("duration_minutes"):
            lines.append(f"- Estimated duration: {scene['duration_minutes']} minutes")
        for link in adventure["encounters"]:
            if link["scene_id"] == scene["id"]:
                label = f"Missing encounter #{link['encounter_id']}" if link["missing"] else f"{link['name']} ({link['xp']} XP; {link['difficulty']})"
                lines.append(f"- Encounter: {label}")
    if adventure["connections"]:
        lines += ["", "## Scene connections"]
        names = {scene["id"]: scene["title"] for scene in adventure["scenes"]}
        for link in adventure["connections"]:
            lines.append(f"- {names[link['from_scene_id']]} → {names[link['to_scene_id']]} ({link['kind'].replace('_', ' ')})")
    for heading, key, fields in (("NPCs", "npcs", ("role", "personality", "motivation", "knows", "wants", "secret", "status", "notes")),
                                 ("Clues", "clues", ("description", "reveals", "location", "alternatives", "notes")),
                                 ("Items and objectives", "items", ("description", "starting_location", "current_location", "notes"))):
        lines += ["", f"## {heading}"]
        for row in adventure[key]:
            state = ("discovered" if row["discovered"] else "undiscovered") if key == "clues" else (("obtained" if row["obtained"] else "open") if key == "items" else "")
            lines += ["", f"### {row['name']}" + (f" ({state})" if state else "")]
            for field in fields:
                if row.get(field):
                    lines.append(f"- {field.title()}: {row[field]}")
            related = [scene["title"] for scene in adventure["scenes"] if scene["id"] in row.get("scene_ids", [])]
            if related:
                lines.append(f"- Scenes: {', '.join(related)}")
            if row.get("external_url"):
                lines.append(f"- External reference: {row['external_url']}")
    lines += ["", "## Sessions"]
    for session in adventure["sessions"]:
        lines += ["", f"### {session['title']}"]
        lines.append(f"- Planned duration: {session['planned_minutes']} minutes")
        planned = [scene["title"] for scene in adventure["scenes"] if scene["id"] in session["scene_ids"]]
        if planned:
            lines.append(f"- Planned scenes: {', '.join(planned)}")
        for field in ("objectives", "prep_notes", "actual_notes", "next_session_notes", "summary_markdown"):
            if session.get(field):
                lines += ["", session[field]]
        for event in session.get("events", []):
            lines.append(f"- {event.get('game_time') or 'During session'}: {event['text']}")
    return "\n".join(lines) + "\n"
