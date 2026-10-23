# PF2e GM Toolkit

A local, modular workspace for Pathfinder Second Edition Remaster Game Masters. The dashboard lists ten working tools, including the Adventure & Session Planner. The toolkit runs entirely on your computer.

Monster Reference is a local Monster Library. Add a monster with only name, level, and maximum HP, then fill in optional details when useful. The library starts empty. Its Basic, Combat Ready, and Detailed labels are informational and never limit encounter or combat use. See the [Monster Library README](tools/04-monster-reference/README.md) and [JSON schema guide](tools/04-monster-reference/MONSTER_SCHEMA.md).

## Install and start

Python 3.10 or newer is required. From the project directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn master.app:app --host 127.0.0.1 --port 18765
```

The final line is the single command to start the application after installation. Open <http://127.0.0.1:18765/>. The app uses a local SQLite file at `data/pf2e.sqlite3` and needs no external service.

## Test

```bash
.venv/bin/python -m pytest
```

See [docs/architecture.md](docs/architecture.md) for the module layout and tool registration interface. Each tool has its own README under `tools/`; the [Adventure Planner README](tools/10-adventure-planner/README.md) explains preparation, play mode, notes, and backups.

## Reusable party PCs

Open Adventure Planner and use **Party PCs** to create a campaign and party, then add PCs with name, class, HP, Speed, and a short note. Link that party in **Edit adventure**. From the adventure, open Combat Tracker and create an empty combat or one based on a saved encounter; the selected party PCs are copied in with initiative blank. You can also use **Add missing party PCs** in an existing combat. Combat HP stays in that combat until you explicitly choose **Update party HP from combat** and confirm the values.
