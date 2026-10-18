# Rules Quick Reference

A searchable local reference for Pathfinder 2e Remaster. The ten short official examples were checked against the linked Archives of Nethys pages. They are read-only, and include Player Core, GM Core, and Monster Core sources. The local app does not contact Archives of Nethys; links open only when you choose them.

## Add your own reference

1. Open the dashboard and choose **Rules Quick Reference**.
2. Select **Add my entry**.
3. Choose a category and either **Personal note** or **House rule**. Enter a name and short explanation. Add reminders, a book and page, or an Archives of Nethys URL if useful.
4. Select **Save entry**. Your entry appears in search and survives restarts. Use **Edit** or **Delete** on your entry later.

User-supplied book, page, and link fields are labeled unverified. Check them against the source before relying on them. The official examples are short pointers, not a substitute for the rulebooks.

## Data and tests

Entries live in the same local SQLite database as the rest of the app (`data/pf2e.sqlite3`). The tool's `tool.py` registers its page and JSON API with the master; `seed.json` contains the ten verified examples. No rule calculation is performed. From the project root, run `.venv/bin/python -m pytest`.
