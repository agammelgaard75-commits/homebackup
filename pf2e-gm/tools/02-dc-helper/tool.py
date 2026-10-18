"""Skill & DC Helper page and local calculation API."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field, field_validator

from master.pages import layout


FOLDER = Path(__file__).resolve().parent
spec = spec_from_file_location("pf2e_dc_calculator", FOLDER / "calculator.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load the DC calculator")
calculator = module_from_spec(spec)
spec.loader.exec_module(calculator)

SKILLS = (
    "Acrobatics", "Arcana", "Athletics", "Crafting", "Deception",
    "Diplomacy", "Intimidation", "Lore", "Medicine", "Nature",
    "Occultism", "Performance", "Religion", "Society", "Stealth",
    "Survival", "Thievery", "Perception", "Other/Custom",
)


class CalculationInput(BaseModel):
    mode: str = "simple"
    proficiency: str = "Trained"
    level: int = Field(default=1, strict=True, ge=0, le=25)
    manual_dc: int | None = Field(default=None, gt=0)
    difficulty: str = "Standard"
    skill: str = "Other/Custom"
    roll: int | None = Field(default=None, strict=True, ge=1, le=20)
    modifier: int | None = None

    @field_validator("skill")
    @classmethod
    def valid_skill(cls, value: str) -> str:
        if value not in SKILLS:
            raise ValueError("Choose a listed skill or Other/Custom")
        return value


def calculate(values: CalculationInput) -> dict:
    base = calculator.base_dc(
        values.mode, proficiency=values.proficiency,
        level=values.level, manual_dc=values.manual_dc,
    )
    adjustment, final = calculator.adjusted_dc(base, values.difficulty)
    result = {
        "base_dc": base,
        "base_dc_text": str(base),
        "adjustment": adjustment,
        "final_dc": final,
        "final_dc_text": str(final),
        "check": None,
        "check_pending": (values.roll is None) != (values.modifier is None),
    }
    if values.roll is not None and values.modifier is not None:
        total, difference, degree = calculator.check_result(values.roll, values.modifier, final)
        result["check"] = {
            "total": total, "total_text": str(total),
            "difference": difference, "difference_text": str(difference),
            "degree": degree,
        }
    return result


def page() -> str:
    proficiency_options = "".join(
        f'<option value="{name}"{" selected" if name == "Trained" else ""}>{name} — DC {dc}</option>'
        for name, dc in calculator.SIMPLE_DCS.items()
    )
    level_options = "".join(
        f'<option value="{level}"{" selected" if level == 1 else ""}>Level {level}</option>'
        for level in range(26)
    )
    adjustment_options = "".join(
        f'<option value="{name}"{" selected" if name == "Standard" else ""}>{name} ({value:+d})</option>'
        for name, value in calculator.ADJUSTMENTS.items()
    )
    skill_options = "".join(
        f'<option value="{name}"{" selected" if name == "Other/Custom" else ""}>{name}</option>'
        for name in SKILLS
    )
    body = f"""
    <link rel="stylesheet" href="/tools/dc-helper/style.css">
    <nav aria-label="Breadcrumb"><a class="back-link" href="/">← All tools</a></nav>
    <header class="helper-heading">
      <div><h1>Skill &amp; DC Helper</h1><p>Look up skill guidance and determine appropriate difficulty classes.</p></div>
      <button id="reset-helper" type="button">Reset</button>
    </header>
    <form id="dc-form" novalidate>
      <div class="helper-grid">
        <section class="helper-card" aria-labelledby="method-title">
          <h2 id="method-title">Choose a DC</h2>
          <fieldset class="method-picker"><legend>DC method</legend>
            <label><input type="radio" name="mode" value="simple" checked> Simple</label>
            <label><input type="radio" name="mode" value="level"> Level-based</label>
            <label><input type="radio" name="mode" value="manual"> Manual</label>
          </fieldset>
          <label id="simple-fields">Task difficulty by proficiency
            <select id="proficiency">{proficiency_options}</select>
          </label>
          <label id="level-fields" hidden>Level of challenge or subject
            <select id="level">{level_options}</select>
          </label>
          <label id="manual-fields" hidden>DC from a specific rule
            <input id="manual-dc" type="text" inputmode="numeric" pattern="[0-9]+" placeholder="Positive integer">
          </label>
          <label>Difficulty adjustment
            <select id="difficulty">{adjustment_options}</select>
          </label>
          <p class="helper-hint">Choose the challenge's difficulty; a character's level does not set the DC automatically.</p>
        </section>
        <section class="helper-card result-card" aria-labelledby="dc-title">
          <h2 id="dc-title">Final DC</h2>
          <output id="final-dc" class="final-dc" aria-live="polite">15</output>
          <dl class="dc-breakdown">
            <div><dt>Base DC</dt><dd id="base-dc">15</dd></div>
            <div><dt>Adjustment</dt><dd id="adjustment">+0</dd></div>
          </dl>
          <p id="dc-error" class="error" role="alert" hidden></p>
        </section>
      </div>
      <section class="helper-card context-card" aria-labelledby="context-title">
        <h2 id="context-title">Check context</h2>
        <div class="context-grid">
          <label>Skill or statistic<select id="skill">{skill_options}</select></label>
          <label>Attempted action<input id="description" type="text" maxlength="160" placeholder="Climb a slippery cave wall"></label>
        </div>
        <p class="helper-hint">Skill selection and this description do not change the DC.</p>
        <label class="secret-label"><input id="secret-check" type="checkbox"> Secret check</label>
        <p id="secret-reminder" class="secret-reminder" hidden>The GM normally rolls privately and describes the outcome without revealing the numerical result.</p>
      </section>
      <details id="check-panel" class="helper-card check-panel">
        <summary>Optional check result calculator</summary>
        <div class="check-inputs">
          <label>Natural d20 roll<input id="roll" type="number" min="1" max="20" step="1" inputmode="numeric" placeholder="1–20"></label>
          <label>Total character modifier<input id="modifier" type="text" inputmode="numeric" placeholder="Including bonuses and penalties"></label>
        </div>
        <p id="check-message" class="helper-hint">Enter both values to calculate the degree of success.</p>
        <div id="check-result" hidden>
          <dl class="check-breakdown"><div><dt>Check result</dt><dd id="check-total"></dd></div><div><dt>Difference from DC</dt><dd id="check-difference"></dd></div></dl>
          <p id="degree" class="degree"></p>
          <p>See the specific action's rules for the effect of this degree of success.</p>
        </div>
      </details>
    </form>
    <aside class="helper-card help-card">
      <h2>Which DC should I use?</h2>
      <p><strong>Simple:</strong> For a task without a level, choose the proficiency difficulty that fits the task. That rank usually is not required to attempt it.</p>
      <p><strong>Level-based:</strong> For a creature, item, obstacle, or other subject with a level, use that subject's level. Use Manual when an action or ability specifies a DC.</p>
      <p><a href="/tools/rules-reference">Open Rules Quick Reference</a> for short rule reminders.</p>
      <h3>Sources</h3>
      <ul>
        <li><a href="https://2e.aonprd.com/Rules.aspx?ID=2628" target="_blank" rel="noopener noreferrer">GM Core p. 52 — Simple DCs</a></li>
        <li><a href="https://2e.aonprd.com/Rules.aspx?ID=2629" target="_blank" rel="noopener noreferrer">GM Core p. 52 — Level-Based DCs</a></li>
        <li><a href="https://2e.aonprd.com/Rules.aspx?ID=2630" target="_blank" rel="noopener noreferrer">GM Core p. 52 — Adjusting Difficulty</a></li>
        <li><a href="https://2e.aonprd.com/Rules.aspx?ID=2263" target="_blank" rel="noopener noreferrer">Player Core p. 401 — Checks and Degrees of Success</a></li>
      </ul>
    </aside>
    <script src="/tools/dc-helper/app.js" defer></script>
    """
    return layout("Skill & DC Helper", body)


def initialize(database_path: Path) -> None:
    """This calculator has no persistent data to initialize."""


def register(app: FastAPI, database_path: Path) -> None:
    @app.get("/tools/dc-helper", response_class=HTMLResponse)
    def helper_page() -> str:
        return page()

    @app.get("/tools/dc-helper/style.css")
    def style() -> FileResponse:
        return FileResponse(FOLDER / "style.css", media_type="text/css")

    @app.get("/tools/dc-helper/app.js")
    def script() -> FileResponse:
        return FileResponse(FOLDER / "app.js", media_type="text/javascript")

    @app.post("/api/dc-helper/calculate")
    def calculate_route(values: CalculationInput) -> dict:
        try:
            return calculate(values)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
