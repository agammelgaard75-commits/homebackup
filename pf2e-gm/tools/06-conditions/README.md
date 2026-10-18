# Conditions Tracker (Phase 6)

Open **Conditions** from the dashboard. Choose a saved combat and combatant, or add a standalone temporary character. Search for a condition, set its value and source, choose a duration, then select **Apply condition**. The current condition list lets you edit, increase, reduce, or remove each source. **Reduce all sources** follows the Player Core rule for reductions to a valued condition. Reapplying the same condition from the same source edits that instance; different sources remain independent.

The rule pane gives concise summaries and verified Player Core page and Archives of Nethys links. The tracker derives consequences such as Off-Guard from Grabbed, Restrained, and Prone without writing duplicate records. It shows the strongest applicable same-type penalties as guidance. Check which creature or attack a rule applies to before using a number. Dying, Wounded, Doomed, and Unconscious are reference and manual labels; detailed death calculations belong to Phase 7.
The rule pane gives concise summaries and verified Player Core page and Archives of Nethys links. The tracker derives consequences such as Off-Guard from Grabbed, Restrained, and Prone without writing duplicate records. It shows the strongest applicable same-type penalties as guidance. Check which creature or attack a rule applies to before using a number. Dying, Wounded, Doomed, and Unconscious are the authoritative condition rows also used by the [Healing & Death Helper](../07-healing-death/README.md). Open that helper from the page or an active condition for knockout, recovery, and treatment calculations.

For turn durations, choose the controlling creature. The **Start-turn reminders** and **End-turn reminders** buttons show prompts; confirmation is required to reduce Frightened, tick a round count, or end a condition. End-of-turn persistent damage prompts show its amount and recovery DC. Record a failed or successful recovery check with the buttons. Successful recovery hides the condition while retaining the check history. Damage is never rolled or applied to HP automatically. For overlapping persistent damage of the same type, the tracker uses the higher fixed amount; if amounts cannot be directly compared, the GM chooses the applicable source.

In Combat Tracker, condition labels appear beside combatants and link to this page. The selected combatant panel can add or remove a common condition. Turn transitions display condition reminders. The earlier **manual effect notes** remain separate and are not converted into rules conditions. The Combat Tracker action counters remain manual; Conditions Tracker's quickened, slowed, and stunned guidance does not modify them.

## Storage and integration

`library.py` contains short fixed rule definitions. `logic.py` contains pure calculations and turn reminders. `tool.py` owns `condition_subjects` and `active_conditions` in the shared SQLite file. Each active row points to either a standalone subject or the pair `(combat_id, combatant_id)` used by Phase 5. The pair is validated against Combat Tracker state; no combatant is copied. `/api/conditions/combat/{id}/summary` is the narrow read interface used by Combat Tracker. The write and reminder endpoints are local and work offline.

## Run and test

From the project root, after installing `requirements.txt`:

```bash
.venv/bin/python -m uvicorn master.app:app --host 127.0.0.1 --port 18765
.venv/bin/python -m pytest
```

Normal play needs no internet. The official source links open only if you choose to follow them.
