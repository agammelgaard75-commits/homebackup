# Combat Tracker

A local Pathfinder 2e Remaster combat bookkeeping tool. Open **Combat Tracker** from the dashboard.

## Start and resume

- **Create empty combat** starts a named combat with no combatants. Add PCs, NPCs, and monsters manually. Name, type, initiative, maximum HP, and current HP can be entered when adding; initiative and HP may be left blank until known. Quantity adds multiple combatants and numbers duplicate names, such as Spider 1 and Spider 2.
- **Create from encounter** copies the name, creature names, quantities, and notes from a saved Phase 4 encounter into a separate combat. Imported creatures have no initiative or HP. Editing combat never changes the saved encounter definition.
- **Saved combats** loads any combat history. The browser also reopens its most recently used combat when available. Every edit is saved to SQLite automatically. **Save now** explicitly writes the current state, **End encounter** keeps its history, **Resume** makes an ended combat editable again, and **Delete saved combat** removes that history.

## During a round

The order starts with highest initiative first. Monsters and NPCs normally precede PCs on a tie. Enter or edit initiative directly on each row; use the arrow buttons to override the order. The highlighted combatant is taking the current turn. **Next Turn** ends that turn, moves to the next pending combatant, and advances the round after the last turn. Actions and reaction refresh only when that combatant starts a turn. A reaction spent on someone else's turn stays spent until its owner's next turn; changing the round alone does not refill it. Before a combatant's first turn, the GM decides whether it can react and can restore the counter manually when appropriate.

For the active combatant, use **Spend/Restore action** and **Spend/Restore reaction** as counters. The three action dots and one reaction dot show ordinary availability; manual restores can exceed those values for special cases. Free actions cost none of these normal actions. **Ready** records its two-action cost, ends the turn, and keeps initiative unchanged. Add the chosen action and trigger to a manual note if needed. Use **Delay** at the start of a turn, before acting. It moves the combatant to the separate delayed list; use **Reenter at chosen point** to place it after a current or upcoming combatant. A delayed combatant cannot use reactions until returning. The combatant can return early in the next round, before its original initiative position; if it never returns, its next turn begins at that original position. Review start/end-of-turn effects manually when delaying.

The optional attack counter shows the next standard and agile multiple attack penalties. Increase it for any attack-trait action, including one that is not a Strike. Use the penalty for the weapon or attack used **now**. Decrease the counter to correct a mistake. It resets at the end of that combatant's turn. Some abilities and readied attacks need additional GM judgment; the tracker does not roll attacks.

Select any combatant to apply damage or healing, spend an off-turn reaction, edit notes, and add or remove short effect labels with optional duration text. Damage consumes temporary HP before regular HP. Healing stops at maximum HP and damage stops at 0 HP. At 0 HP the page highlights the combatant and reminds the GM to consult the knockout and dying rules. Effects and duration text never expire automatically. Maximum, current, and temporary HP can also be edited directly in the initiative row.

The selected combatant panel also has a quick **Add condition** picker. Structured rules conditions appear as labels beside combatants and link to the [Conditions Tracker](../06-conditions/README.md), where you can edit sources, values, and durations. The Combat Tracker can remove a selected condition source. Turn transitions show advisory condition reminders, including Frightened reduction and persistent damage recovery; confirm those changes explicitly. Other manual effect labels and notes remain separate from structured conditions.

The selected panel also links to the [Healing & Death Helper](../07-healing-death/README.md). At the start of a Dying combatant's turn, the tracker displays its recovery DC and a link to preview and confirm the check. HP and death-related conditions changed in that helper appear here when the combat is refreshed. A knocked-out character's initiative move is an optional confirmed action in the helper.

Opening Combat Tracker from the [Exploration Helper](../08-exploration/README.md) displays its read-only encounter checklist and loads the linked combat if one exists. Enter initiative and apply any Scout, Defend, Avoid Notice, or spell effects manually so a bonus is not counted twice.

An ended combat displays **Open reward screen**, which links to the [Treasure & XP Helper](../09-treasure-xp/README.md). A saved encounter definition is preselected there when available. Ending combat never grants XP or treasure automatically.

The tracker makes no attack, damage, saving throw, death, dying, wounded, quickened, slowed, or stunned decisions. Initiative is entered by the GM; it is never rolled automatically. The tool works offline after installation. Rule links are optional reading.

## Rules sources

- [Player Core: Encounter Mode and Turns](https://2e.aonprd.com/Rules.aspx?ID=2263)
- [Player Core p. 402: Multiple Attack Penalty](https://2e.aonprd.com/Rules.aspx?ID=2289)
- [GM Core p. 26: Running the Encounter](https://2e.aonprd.com/Rules.aspx?ID=2545)
- [Player Core p. 410: Getting Knocked Out](https://2e.aonprd.com/Rules.aspx?ID=2324)

Combat bookkeeping lives in pure `state.py` functions. `tool.py` reads only Phase 4's saved encounter tables when importing, then writes an independent `combat_sessions` record to the shared SQLite database. The page is in `app.js` and `style.css`. Run `.venv/bin/python -m pytest` from the project root for all tool and dashboard tests.
