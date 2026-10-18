# Encounter Builder

An offline Pathfinder 2e Remaster encounter planning page. Open **Encounter Builder** from the master dashboard.

## During play

1. Set the party level (1–20), number of characters (2–8), and desired difficulty. The page starts at level 1, four characters, Moderate. All characters are assumed to be the same level.
2. Add creature groups manually. Enter a name, level (−1 to 25), and quantity; notes and an external reference URL are optional. Change any value or remove a group to update XP immediately. A valid URL appears as a link; the app never fetches it.
3. Optionally choose a quick template and click **Use template**. This replaces the current creature list with generic groups you can rename. Templates appear only when their creature levels are valid.
4. Read total creature XP, the party-size-adjusted target, remaining XP, each group's contribution, and the comparison with all five targets. A negative remaining amount means the selected target is exceeded. Encounters between targets are described as between targets; the app does not invent a cutoff.
5. Enter an encounter name and optional notes, then click **Save new**. Use **Saved encounters** and **Load selected** to reopen one. **Save changes** updates the loaded record. **Duplicate** creates a separate copy; **Delete** removes the selected saved record.

The tool warns if a creature is outside the published party level −4 to +4 XP table. In that case, it leaves the total and comparison unavailable until you correct the creature level. Severe and Extreme targets, high-level creatures, many weak creatures, and totals over the selected target also produce reminders. Warnings never block editing or saving.

The adjusted encounter budget is a building target. The displayed standard XP award is the four-character target amount **for each character**, independent of party size; it is not divided among players. Trivial encounters normally give no XP. For a custom encounter that differs from its selected target, consult the GM Core XP Awards guidance for its creature XP total and any adjustment. The tool does not assign a custom official award.

The shared Phase 1 tables store campaign and party names but have no active campaign, party level, or party size. This tool therefore uses its own party settings and does not associate saved encounters with a campaign yet. Saved encounters persist in the same local SQLite database as the rest of the app. No external service is needed to build or save encounters. Mixed-level parties, monster statistics, hazards, combat tracking, and treasure are outside this phase.

## Rules sources

- [GM Core p. 75: Encounter Design and XP Budgets](https://2e.aonprd.com/Rules.aspx?ID=2716)
- [GM Core p. 56: XP Awards](https://2e.aonprd.com/Rules.aspx?ID=2649)
- [GM Core p. 56: Party Size](https://2e.aonprd.com/Rules.aspx?ID=2652)

The fixed XP tables, templates, and comparison logic are in `calculator.py`, separate from the FastAPI routes and SQLite code in `tool.py` and the page in `app.js`. Run `.venv/bin/python -m pytest` from the project root to test this tool and the existing application.
