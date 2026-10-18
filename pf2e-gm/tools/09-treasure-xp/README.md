# Treasure & XP Helper (Phase 9)

Open **Treasure & XP** from the dashboard. Create an independent tracker or select an existing shared party. Each shared party can have one reward tracker, so creating one for the same party opens its existing XP and reward history. Set party level, size, current XP per character, and advancement method in **Party**. These fields can also initialize a campaign already in progress.
The master dashboard shows the last opened reward tracker's level and XP when one exists.

## Treasure tab

The guideline uses the published GM Core Party Treasure by Level table for levels 1–20. Its **approximate total value already includes** item value and currency. Currency and valuables are shown separately as one part of that total. The table applies across an entire level, not each encounter. For extra PCs, the page shows the additional item suggestions and currency; it does not invent prices for those extra items or an exact adjusted total. For fewer PCs, reducing treasure is optional.

Add a reward with a name, category, item level for permanent items or consumables, quantity, **value per item** in gp, optional source and Archives URL, description, session label, GM note, and optional saved encounter. Choose Planned, Awarded, or Missed. Planned entries can be marked Awarded later. Open an entry to correct its fields; every actual change is kept in the treasure history with before and after snapshots. Awarded value counts only Awarded entries. Item counts are grouped by level independently of gp value.

For a campaign that began before using the app, enter previously awarded total gp and its currency/valuable portion under **Earlier awards / baseline**, then confirm review. Add earlier permanent and consumable rewards as Awarded entries if their item levels should appear in the count. Without a confirmed baseline, the remaining-treasure figure is incomplete.

## Experience tab

Use the published accomplishment awards (10/30/80 XP), the simple or complex hazard table, a saved Encounter Builder encounter, or a custom nonnegative award. XP is the **amount each eligible character receives**; it is never divided by party size. An encounter preview uses Encounter Builder's existing calculation. It offers the standard target award only when creature XP matches that encounter's adjusted target. For a different total, enter a GM-selected award after reviewing the guidance. Creating or ending an encounter never awards XP automatically.

Click **Confirm XP award** to record it. The same saved encounter cannot have two active XP awards in one tracker. To correct it, reverse the old transaction with a reason, then select **Correct a reversed encounter award** and enter a correction note before awarding it again. Reversal is stored as a new signed transaction; the original remains in history. If a party has leveled since the mistake and lacks enough current XP to reverse the full award, correct current XP manually in Party settings, which writes an auditable settings event.

Standard, fast, and slow advancement thresholds are 1,000, 800, and 1,200 XP. Reaching the threshold shows **Ready to Level Up**; the level changes only on GM confirmation, with excess XP carried forward. Milestone mode disables XP awards and permits a manual level advance. Level 20 is the supported maximum.

A completed Combat Tracker combat has an **Open reward screen** link. If it came from a saved Encounter Builder definition, that encounter is preselected in the XP tab. The Combat Tracker does not grant XP or treasure itself.

## Storage and tests

`rules.py` holds the verified treasure, hazard XP, accomplishment, and advancement tables and pure calculations. `tool.py` stores tracker state, treasure entries, immutable XP transactions and reversals, and treasure change events in the shared SQLite database. It reads saved encounters through a narrow call to Encounter Builder's calculator. The `parties` table remains the shared party identity; Phase 9 holds its sole XP total in `reward_trackers`. The page uses plain `app.js` and `style.css`.

From the project root, run `.venv/bin/python -m pytest`. Start the app with `.venv/bin/python -m uvicorn master.app:app --host 127.0.0.1 --port 18765`. Normal use requires no internet connection; source links are optional reading.

## Official references

- [GM Core pp. 58–61: Treasure and party size](https://2e.aonprd.com/Rules.aspx?ID=2655)
- [GM Core p. 59: Party Treasure by Level](https://2e.aonprd.com/Rules.aspx?ID=2656)
- [GM Core p. 56: XP Awards and hazards](https://2e.aonprd.com/Rules.aspx?ID=2649)
- [GM Core p. 56: Party Size and XP](https://2e.aonprd.com/Rules.aspx?ID=2652)
- [GM Core p. 57: Advancement Speeds](https://2e.aonprd.com/Rules.aspx?ID=2654)
