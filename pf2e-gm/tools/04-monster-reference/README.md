# Monster Library

Open **Monster Reference** from the dashboard. The library starts empty and works offline. It never downloads monsters or fills in missing statistics.

## Add and edit

Use **Quick Add** for name, level (−1 through 25), and maximum HP. These are the only required fields. After creation, open **Detailed Editor** to add optional defenses, saves, perception, senses, skills, movement, attacks, abilities, spellcasting, sources, and notes. Expand only the sections you need. Attacks, abilities, spells, skills, and Speeds have repeatable rows that can be added or removed. **Save and continue editing** retains other saved fields. **Quick Edit** changes the three core fields; **Duplicate Monster** makes an independent copy.

The Basic, Combat Ready, and Detailed labels are application-specific completeness hints. They never block saving, import, encounter use, or combat use. The details panel lists the fields needed for the next label. The library filter can show one completeness level at a time. Session Monster Collections let you group saved monsters under a session label; the same monster can appear in several collections.

## JSON

Use **JSON import** for one monster object or a version 1 backup containing a `monsters` array. A minimal example is [`minimal.example.json`](minimal.example.json). The detailed attack and ability format, including `type`, `actions`, `bonus`, `effect`, `trigger`, `requirements`, and `dc`, is described in [`MONSTER_SCHEMA.md`](MONSTER_SCHEMA.md) and [`monster.schema.json`](monster.schema.json). Single-monster export omits local IDs and derived completeness. Import creates new records. The GUI and import share the same validation model. Existing saved monsters using the earlier entry format are read in the new format.

## Encounter and combat handoff

Encounter Builder's Monster Library selector copies a saved monster's name and level into a creature group and retains a stable library ID. Completeness is shown in the selector and beside the group; it is informational. Manually changing the copied name or level detaches that group from the library. The encounter record remains usable if the library monster is later deleted.

Combat Tracker can copy a library monster directly or through a linked encounter group. It copies name, maximum HP, available optional statistics, and starts current HP at maximum HP. A combatant is a separate snapshot; damage never edits the library monster. Initiative remains for the GM to enter. A deleted library monster in an older encounter falls back to that encounter's saved name and level, with HP unknown.

Each library monster has a read-only details page at `/tools/monster-reference/monsters/{id}`. It displays every entered field without edit controls. Combat Tracker links to a separate read-only page for each monster combatant; that page shows the copy saved with the combat, including its attacks, abilities, spellcasting, source, and notes. Later library edits or deletion do not change the combat copy. A manually entered monster shows the information available in its combat record.

Run all tests with `.venv/bin/python -m pytest` from the repository root.
