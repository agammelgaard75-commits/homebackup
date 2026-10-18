# PF2e GM Toolkit

A local, modular workspace for Pathfinder Second Edition Remaster Game Masters. The dashboard lists ten tools. Rules Quick Reference, Skill & DC Helper, Encounter Builder, Combat Tracker, Conditions Tracker, Healing & Death Helper, Exploration Helper, and Treasure & XP Helper are available; the other tools remain placeholders.

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

See [docs/architecture.md](docs/architecture.md) for the module layout and tool registration interface. Each implemented tool has its own README under `tools/`; the [Treasure & XP Helper README](tools/09-treasure-xp/README.md) explains reward planning, XP progression, and corrections.
