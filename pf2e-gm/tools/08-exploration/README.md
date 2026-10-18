# Exploration Helper (Phase 8)

Open **Exploration** from the dashboard. Create a named session, optionally choose an existing shared party name, and optionally link a saved Combat Tracker combat. The shared `parties` table currently stores party names only, so add members manually or import PC names from a linked combat. Imported names continue to come from the combatant's stable ID; exploration Speed, activities, and notes belong to the exploration session.

## Activities and travel

Change each member's activity from the dropdown; it saves immediately and appears in the chronological log. Select an activity to see its short description, movement restriction, relevant skill, encounter effect, Player Core page, and official link. Avoid Notice, Defend, Detect Magic, Investigate, Repeat a Spell, Scout, and Search use half travel speed. Normal Travel uses full speed; Hustle uses double speed. Follow the Expert uses the selected expert's tactic and requires an expert, master, or legendary ally plus a relevant skill. Track and Custom Activity require a manual travel pace because the helper does not infer one.

The calculator starts with **Speed × 10 feet per minute**, then applies the activity and terrain. Difficult terrain halves travel; greater difficult terrain reduces it to one-third. Search and Detect Magic have optional 300 or 150 feet-per-minute caps for the specific thoroughness described in Player Core. The party pace is the slowest effective member; enter a manual pace for a split party or special movement. Estimated feet and miles are shown together. Player Core's separate miles-per-hour table uses rounded values, so long-distance estimates may differ slightly.

Enter a duration and select **Record travel and advance time** to save a Travel log entry and add that duration to the shared game clock. Hustle minutes used accumulate for each Hustling member, and the calculator warns when a segment would exceed the recorded Constitution-based limit. The GM can correct Hustle minutes manually; the tool does not decide when a character's ability to Hustle resets.

## Time, notes, and combat

Use the time buttons or a custom duration to advance in-game minutes; **Set game time** corrects the total. The clock is stored in Phase 7's `healing_clocks` table. A session linked to a saved combat uses that combat's clock, so Healing & Death sees the same minute count. An independent exploration session uses its own scope in the same clock table. No healing, rest benefit, or condition expiry is applied when time changes.

**Quick tasks** log Refocus, Treat Wounds, Repair, Identify Magic, Search an area, Rest, and Daily preparations, with optional GM-entered minutes. Treat Wounds links to Healing & Death; tasks do not run their mechanics. The notes form adds short events with their game time.

**Start Encounter checklist** shows Scout's one +1 circumstance initiative bonus for the party, Stealth initiative guidance for Avoid Notice, raised-shield guidance for Defend, and relevant spell or expert reminders. Confirm review before opening Combat Tracker. The Combat Tracker displays this read-only handoff and opens the linked saved combat when present. Initiative rolls, detection, shields, spell effects, and bonuses remain GM decisions; the helper never writes them into combat state.

## Storage and testing

`rules.py` holds the fixed activity summaries, travel calculations, Hustle limit, and encounter reminders. `tool.py` owns `exploration_sessions`, `exploration_members`, and `exploration_log` in SQLite. It extends the existing Phase 7 clock table with an exploration scope while preserving its existing combat and standalone clock rows. `app.js` and `style.css` provide the single-page UI. Run `.venv/bin/python -m pytest` from the project root. Start the app with `.venv/bin/python -m uvicorn master.app:app --host 127.0.0.1 --port 18765`.

## Official references

- [Player Core pp. 438–439: Exploration Mode, Travel Speed, and activities](https://2e.aonprd.com/Rules.aspx?ID=2440)
- [Player Core pp. 438–439: Exploration Activities](https://2e.aonprd.com/Rules.aspx?ID=2442)
- [GM Core: Running Exploration](https://2e.aonprd.com/Rules.aspx?ID=2573)
