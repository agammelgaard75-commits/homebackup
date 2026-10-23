# Monster JSON schema (version 1)

The smallest valid monster is:

```json
{"schema_version": 1, "name": "My Monster", "level": 1, "max_hp": 20}
```

`name` must contain non-whitespace text, `level` must be an integer from −1 through 25, and `max_hp` must be a positive integer. Quick Add and JSON import use the same validation model. Every other field is optional. Missing numeric values remain `null`; missing lists and objects remain empty. No missing statistic is filled in automatically.

Optional top-level fields:

| Field | Shape |
| --- | --- |
| `ac`, `fortitude`, `reflex`, `will`, `perception` | Integer or `null`; zero and negative modifiers are valid |
| `traits`, `senses` | Arrays of strings |
| `skills` | Object mapping skill names to integer modifiers |
| `speeds` | Array of `{ "type": "land", "feet": 25 }` objects; `feet` is positive |
| `attacks` | Array of entries with `name`, `type`, `actions`, `bonus`, `traits`, `damage`, and `effect` |
| `abilities` | Array of entries with `name`, `actions`, `traits`, `trigger`, `requirements`, `description`, and `dc` |
| `spellcasting` | Array of entries with `name`, optional `description`, and `offensive` boolean |
| `source_book`, `source_page`, `source_url`, `notes` | Optional source and GM text |

Only `name` is required within each attack or ability; the other entry fields may be omitted. `actions` accepts a positive integer or text such as `"passive"` or `"reaction"`. A missing attack type, action cost, bonus, or ability DC remains `null`, not a guessed value. The complete canonical format is in [`monster.schema.json`](monster.schema.json). Unknown fields are rejected so typos do not silently lose data. `source_url` must use HTTP or HTTPS.

Example attack and ability:

```json
{
  "attacks": [{"name": "Fangs", "type": "melee", "actions": 1, "bonus": 9,
    "traits": ["finesse"], "damage": "1d4+2 piercing", "effect": "See venom ability."}],
  "abilities": [{"name": "Venom", "actions": "passive", "traits": ["poison"],
    "trigger": null, "requirements": null, "description": "GM-entered effect.", "dc": 17}]
}
```

Import accepts one monster object or `{ "schema_version": 1, "monsters": [ ... ] }`. Export of a single monster returns a version 1 object with `schema_version: 1`. The saved monster ID and derived completeness label are not part of portable monster data. Import creates new local records; it never replaces existing monsters.

For older JSON, the importer also accepts `defenses.hp` as `max_hp`, along with `defenses.ac`, `defenses.fortitude`, `defenses.reflex`, and `defenses.will`. A top-level `speed` number maps to one land Speed. Earlier attack entries with `modifier` and `description` map to `bonus` and `effect`; earlier abilities remain importable. If both `max_hp` and `defenses.hp` are present and differ, import fails. These legacy shapes are import-only; exports always use canonical fields.

Completeness is toolkit guidance, not a PF2e rule. Basic needs only the three required fields. Combat Ready additionally needs AC, all three saves, a Speed, and an attack, offensive spell, or combat ability. An ability qualifies when it has a non-passive action, a trigger, or a DC. Detailed needs Combat Ready plus one of skills, senses, traits, abilities, spellcasting, or a source reference. The label is calculated from current data; it is never stored or required for saving or use.
