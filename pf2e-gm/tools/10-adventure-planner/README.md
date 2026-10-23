# Adventure & Session Planner

The planner is a private, offline GM workspace. It keeps short prompts for improvisation rather than prepared scripts. Scene order and connections are suggestions. Open or complete any scene in any order.

## Use

Start the toolkit from the repository root with:

```bash
.venv/bin/python -m uvicorn master.app:app --host 127.0.0.1 --port 18765
```

Open <http://127.0.0.1:18765/tools/adventure-planner>. Choose **New adventure**, enter a title, and save. Campaign and party links are optional and use the shared records when present. In **Preparation** mode, add scenes, then add NPCs, clues, items, objectives, and sessions. Check several scenes for one clue or NPC to make it available in more than one place. Use the arrows to change suggested scene order. Connections are optional labels between scenes.

Use **Party PCs** to create a campaign and party and add each PC's name, class, maximum and current HP, Speed, and brief notes. Edit or remove PCs there. Select that party in **Edit adventure** to link it to the adventure. The roster is shared across adventures; adventure JSON export does not include the shared roster. **Open Combat Tracker with this party** preselects it. Linked scene encounters also preselect their encounter and the adventure's party. The GM creates the combat explicitly, and can later copy missing PCs into it. Combat HP changes affect the roster only through Combat Tracker's confirmed **Update party HP from combat** action.

Create a session with planned minutes and scene selections. The planner sums those scene estimates and warns when they exceed the session's planned time. In **Play** mode, switch directly to any scene, edit its short notes, mark it completed or skipped, and record short session notes. Mark clues discovered and items obtained as play unfolds. A selected session lets the recap associate those changes with that session. Add GM notes for the next session in the session editor. **Generate recap** opens an editable summary; save the session to keep edits, then use **Export recap** for Markdown.

Link a saved Encounter Builder encounter to any scene. The planner displays its current creature summary, XP, and comparison from Encounter Builder. **Open combat** opens Combat Tracker; the GM chooses whether to create or resume a combat. Scene changes never start combat or change the encounter. When an encounter is deleted, the planner keeps a visible unavailable link. Use the contextual tool links for DCs, rules, conditions, healing, exploration, and rewards.

**Export JSON** backs up this adventure only, including scenes, associations, linked encounter IDs, sessions, and notes. **Export Markdown** gives readable GM notes. **Import JSON backup** is available at the top of the planner even when no adventure is open. Import creates a separate adventure and validates its records. Existing encounter IDs are retained; unavailable encounters are marked missing. Campaign and party references are restored only if those IDs exist locally. Review those links after moving a backup to another installation.

For generated JSON, each scene `type` must be one of `roleplaying`, `exploration`, `combat`, `puzzle`, `investigation`, `travel`, or `other`. Scene `status` must be `not_started`, `active`, `completed`, or `skipped`. The importer also accepts display labels such as `Investigation` and `Not Started`, then stores the canonical values. `current_scene_id: null` is valid for a new adventure.

The adventure can be archived and restored. Deletion asks for confirmation and removes only planner records; it leaves linked encounters and combat history alone. Play mode quick scene notes save shortly after typing; other changes save to the local SQLite database as soon as a form or action is submitted.

## Scope and rules

This tool does not calculate encounters, treasure, or adventure outcomes. It does not force scene progression or generate fictional events. The recap includes recorded completed scenes, clues, items, decisions, completed linked encounters, unresolved objective entries, and session notes. For precise session attribution, choose the active session while marking progress in Play mode.

References: [GM Core, Adventure Design, page 68](https://2e.aonprd.com/Rules.aspx?ID=2688) and [GM Core, Encounter Design](https://2e.aonprd.com/Rules.aspx?ID=2716).

## Tests

```bash
.venv/bin/python -m pytest
```

The planner tests cover nonlinear scenes, associations, session budgets, recaps, encounter deletion, backups, and restart persistence.
