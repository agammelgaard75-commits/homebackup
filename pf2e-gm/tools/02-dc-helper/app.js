const form = document.querySelector('#dc-form');
const modeInputs = [...form.querySelectorAll('input[name="mode"]')];
const proficiency = document.querySelector('#proficiency');
const level = document.querySelector('#level');
const manual = document.querySelector('#manual-dc');
const difficulty = document.querySelector('#difficulty');
const skill = document.querySelector('#skill');
const roll = document.querySelector('#roll');
const modifier = document.querySelector('#modifier');
const dcError = document.querySelector('#dc-error');
const checkMessage = document.querySelector('#check-message');
const checkResult = document.querySelector('#check-result');
let requestNumber = 0;

function selectedMode() {
  return modeInputs.find(input => input.checked).value;
}

function showMode(mode) {
  document.querySelector('#simple-fields').hidden = mode !== 'simple';
  document.querySelector('#level-fields').hidden = mode !== 'level';
  document.querySelector('#manual-fields').hidden = mode !== 'manual';
}

function showError(message) {
  dcError.textContent = message;
  dcError.hidden = !message;
  document.querySelector('#final-dc').textContent = '—';
  document.querySelector('#base-dc').textContent = '—';
  document.querySelector('#adjustment').textContent = '—';
  checkResult.hidden = true;
}

async function update() {
  const currentRequest = ++requestNumber;
  const mode = selectedMode();
  showMode(mode);
  document.querySelector('#secret-reminder').hidden = !document.querySelector('#secret-check').checked;

  const manualText = manual.value.trim();
  if (mode === 'manual' && (!/^[0-9]+$/.test(manualText) || /^0+$/.test(manualText))) {
    showError('Enter a positive whole-number manual DC.');
    return;
  }
  const rollText = roll.value.trim();
  const modifierText = modifier.value.trim();
  const hasRoll = rollText !== '';
  const hasModifier = modifierText !== '';
  const validRoll = !hasRoll || (Number.isInteger(Number(rollText)) && Number(rollText) >= 1 && Number(rollText) <= 20);
  const validModifier = !hasModifier || /^[+-]?\d+$/.test(modifierText);
  if (!validRoll || !validModifier) {
    checkMessage.textContent = 'Enter a natural roll from 1 to 20 and a whole-number modifier.';
  } else if (hasRoll !== hasModifier) {
    checkMessage.textContent = 'Enter both the roll and total modifier to calculate a result.';
  } else if (!hasRoll) {
    checkMessage.textContent = 'Enter both values to calculate the degree of success.';
  } else {
    checkMessage.textContent = '';
  }

  const payload = {
    mode, proficiency: proficiency.value, level: Number(level.value),
    manual_dc: mode === 'manual' ? manualText : null,
    difficulty: difficulty.value, skill: skill.value,
    roll: hasRoll && hasModifier && validRoll && validModifier ? Number(rollText) : null,
    modifier: hasRoll && hasModifier && validRoll && validModifier ? modifierText : null,
  };
  try {
    const response = await fetch('/api/dc-helper/calculate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error('Check the DC inputs.');
    const data = await response.json();
    if (currentRequest !== requestNumber) return;
    dcError.hidden = true;
    document.querySelector('#base-dc').textContent = data.base_dc_text;
    document.querySelector('#adjustment').textContent = `${data.adjustment >= 0 ? '+' : ''}${data.adjustment}`;
    document.querySelector('#final-dc').textContent = data.final_dc_text;
    checkResult.hidden = !data.check;
    if (data.check) {
      document.querySelector('#check-total').textContent = data.check.total_text;
      document.querySelector('#check-difference').textContent = `${data.check.difference >= 0 ? '+' : ''}${data.check.difference_text}`;
      document.querySelector('#degree').textContent = data.check.degree;
    }
  } catch (error) {
    if (currentRequest === requestNumber) showError(error.message);
  }
}

form.addEventListener('input', update);
form.addEventListener('change', update);
form.addEventListener('submit', event => event.preventDefault());
document.querySelector('#reset-helper').addEventListener('click', () => {
  form.reset();
  document.querySelector('#check-panel').open = false;
  update();
});
update();
