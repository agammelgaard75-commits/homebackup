# Skill & DC Helper

An offline Pathfinder 2e Remaster DC and check helper. Open it from the master dashboard.

## During play

1. Choose **Simple** for a task without a level, **Level-based** for a challenge or subject with a level, or **Manual** when a rule already gives a DC. The level is the challenge's level, not automatically the character's level. A Simple rank describes task difficulty and usually is not a minimum rank to attempt it.
2. Choose an adjustment if the task differs from the base difficulty. Standard adds 0. The page shows base DC, adjustment, and final DC immediately.
3. Optionally select a skill or Perception and describe the action. These fields do not change the DC.
4. Open **Optional check result calculator** and enter the natural d20 result and total modifier to see the check total, difference, and degree of success. Consult the specific action for what that degree does.
5. Select **Secret check** for a reminder to roll privately. **Reset** returns to Trained Simple DC 15 with Standard adjustment.

No input is saved, and the tool makes only local requests to the running FastAPI app. The source links are optional to open; they are not needed for normal use.

## Rule sources

- [GM Core p. 52: Simple DCs](https://2e.aonprd.com/Rules.aspx?ID=2628)
- [GM Core p. 52: Level-Based DCs](https://2e.aonprd.com/Rules.aspx?ID=2629)
- [GM Core p. 52: Adjusting Difficulty](https://2e.aonprd.com/Rules.aspx?ID=2630)
- [Player Core p. 401: Checks and Degrees of Success](https://2e.aonprd.com/Rules.aspx?ID=2263)

The fixed values and degree calculation live in `calculator.py`, separate from the UI in `tool.py` and `app.js`. From the project root, run `.venv/bin/python -m pytest` to run all tool and dashboard tests.
