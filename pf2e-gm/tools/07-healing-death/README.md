# Healing & Death Helper (Phase 7)

Open **Healing & Death** from the dashboard. Choose a combatant from a saved combat or add a standalone character. Combatant HP comes from the Combat Tracker; Dying, Wounded, Doomed, and Unconscious come from the Conditions Tracker. Hero Points and treatment history are stored in the same local SQLite database. No internet connection is needed for play.

## During play

- **Character status** shows HP, the four relevant conditions, Hero Points, game time, and recent treatments. Use the manual fields for special abilities or GM rulings. Set HP and conditions separately if making a manual override.
- **Knocked Out** sets HP to 0 and previews Dying based on a normal hit, an attacker's critical hit, or the character's own critical failure. Existing Wounded adds to initial Dying. Nonlethal damage leaves the character Unconscious without Dying. Ordinary monsters need explicit confirmation as significant creatures before using PC dying rules. For a combatant, the optional initiative move places them directly before the active turn.
- **Recovery check** uses a natural d20 flat check against DC 10 + current Dying. **Damage while Dying** previews a 1 or 2 point increase. Both show the Doomed-adjusted death threshold. Select the Hero Point option before confirming an increase, or use the separate turn-start Hero Point button. It spends all points, stabilizes at 0 HP, and keeps Wounded unchanged.
- **Administer First Aid: Stabilize** uses Medicine DC 15 + Dying. Enter a natural roll and modifier, or select a degree. A successful check removes Dying and increases Wounded. Persistent bleeding remains in the Conditions Tracker.
- **Manual Healing** raises HP up to maximum and ends Dying if HP rises above 0, increasing Wounded normally. It does not immediately remove Wounded. At full HP, advance game time at least 10 minutes, then confirm the character rested to clear Wounded.

For emergency actions and treatments, **Preview** calculates the projected result without changing records. **Confirm change** applies it. Fatal outcomes remain GM decisions; the helper warns when Dying reaches the death threshold.

## Treat Wounds and Battle Medicine

Choose a healer, Medicine rank, DC option, and either a d20 check and modifier or a manually determined degree. Enter the **rolled dice total**; the helper adds the listed bonus. It validates dice totals for 2d8, 4d8, or 1d8, and allows a higher-ranked healer to choose a lower DC. A successful Treat Wounds that restores HP removes Wounded. Battle Medicine requires its feat, takes one action, and does not remove Wounded.

Treat Wounds advances the recorded game clock by 10 minutes, or by one hour if successful treatment is continued for double healing. Its usual one-hour immunity starts **when treatment begins**, so ordinary 10-minute care leaves 50 minutes afterward. Battle Medicine uses a separate one-day immunity for each healer and patient. Enter an override reason when a feat or GM ruling changes immunity. The **Advance game time** control tracks game minutes explicitly; wall-clock time is never used.

The clock is shared by patients in one saved combat, and each standalone patient has a separate clock. Treatments are recorded in sequence; use the game-time and immunity override controls for overlapping care or feats. The tool does not roll dice, apply initiative automatically, calculate persistent bleed, or interpret unusual abilities.

## Storage and integration

`rules.py` contains deterministic calculations. `storage.py` is the narrow adapter to Combat Tracker's saved `state_json` and Conditions Tracker's `active_conditions` rows. It creates `healing_profiles`, `healing_clocks`, and `healing_treatments` for Hero Points, explicit game time, and treatment records. The helper does not copy combatants or create a second condition list. `tool.py` applies HP, condition, and treatment changes in one SQLite transaction. Combat Tracker calls the read-only `/api/healing-death/combat/{id}/reminders` endpoint at turn start and links to the helper.

Run `.venv/bin/python -m pytest` from the project root for all tests. Start the application with `.venv/bin/python -m uvicorn master.app:app --host 127.0.0.1 --port 18765`.

## Official sources

- [Player Core p. 410: Getting Knocked Out](https://2e.aonprd.com/Rules.aspx?ID=2324)
- [Player Core p. 411: Dying and recovery](https://2e.aonprd.com/Rules.aspx?ID=2325)
- [Player Core p. 447: Wounded](https://2e.aonprd.com/Conditions.aspx?ID=99)
- [Player Core pp. 241–242: Medicine, Treat Wounds, and Administer First Aid](https://2e.aonprd.com/Skills.aspx?ID=42)
- [Player Core p. 253: Battle Medicine](https://2e.aonprd.com/Feats.aspx?ID=5125)
- [Player Core p. 413: Hero Points](https://2e.aonprd.com/Rules.aspx?ID=2333)
