const queryInput = document.querySelector('#rule-query');
const categoryInput = document.querySelector('#rule-category');
const list = document.querySelector('#rules-list');
const count = document.querySelector('#rule-count');
const panel = document.querySelector('#entry-panel');
const form = document.querySelector('#entry-form');
const formTitle = document.querySelector('#form-title');
const formError = document.querySelector('#form-error');
let editingId = null;
let requestNumber = 0;
let searchTimer;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function sourceLine(entry) {
  const source = element('p', undefined, 'rule-source');
  if (entry.kind === 'official') {
    source.append(`${entry.source_book}, p. ${entry.source_page} · Verified source · `);
  } else if (entry.source_book || entry.source_page || entry.source_url) {
    source.append(`${entry.source_book || 'Source'}${entry.source_page ? `, p. ${entry.source_page}` : ''} · User supplied, unverified · `);
  } else {
    return null;
  }
  if (entry.source_url) {
    const link = element('a', 'Archives of Nethys');
    link.href = entry.source_url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    source.append(link);
  }
  return source;
}

function showForm(entry = null) {
  form.reset();
  formError.hidden = true;
  editingId = entry ? entry.id : null;
  formTitle.textContent = entry ? 'Edit my entry' : 'Add my entry';
  if (entry) {
    for (const field of ['name', 'category', 'summary', 'reminders', 'kind', 'source_book', 'source_page', 'source_url']) {
      form.elements[field].value = entry[field] ?? '';
    }
  }
  panel.hidden = false;
  panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  form.elements.name.focus();
}

function render(entries) {
  list.replaceChildren();
  for (const entry of entries) {
    const card = element('article', undefined, 'rule-entry');
    const heading = element('h2', entry.name);
    card.append(heading);
    const meta = element('div', undefined, 'rule-meta');
    meta.append(element('span', entry.category));
    const kind = entry.kind === 'official' ? 'Official rule' : entry.kind === 'house_rule' ? 'House rule' : 'Personal note';
    meta.append(element('span', kind, entry.kind === 'house_rule' ? 'house-rule' : ''));
    card.append(meta, element('p', entry.summary));
    if (entry.reminders) card.append(element('p', `Reminder: ${entry.reminders}`, 'rule-reminder'));
    const source = sourceLine(entry);
    if (source) card.append(source);
    if (entry.kind !== 'official') {
      const actions = element('div', undefined, 'rule-actions');
      const edit = element('button', 'Edit', 'secondary');
      edit.type = 'button';
      edit.addEventListener('click', () => showForm(entry));
      const remove = element('button', 'Delete', 'secondary');
      remove.type = 'button';
      remove.addEventListener('click', () => deleteEntry(entry));
      actions.append(edit, remove);
      card.append(actions);
    }
    list.append(card);
  }
  if (!entries.length) list.append(element('p', 'No matching references.'));
}

async function loadEntries() {
  const currentRequest = ++requestNumber;
  const params = new URLSearchParams({ q: queryInput.value.trim(), category: categoryInput.value });
  try {
    const response = await fetch(`/api/rules-reference?${params}`);
    if (!response.ok) throw new Error('Could not load references.');
    const data = await response.json();
    if (currentRequest !== requestNumber) return;
    render(data.items);
    count.textContent = `${data.count} ${data.count === 1 ? 'reference' : 'references'}`;
  } catch (error) {
    if (currentRequest === requestNumber) count.textContent = error.message;
  }
}

async function deleteEntry(entry) {
  if (!window.confirm(`Delete “${entry.name}”?`)) return;
  try {
    const response = await fetch(`/api/rules-reference/${entry.id}`, { method: 'DELETE' });
    if (!response.ok) throw new Error('Could not delete this entry.');
    await loadEntries();
  } catch (error) {
    count.textContent = error.message;
  }
}

queryInput.addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadEntries, 120);
});
categoryInput.addEventListener('change', loadEntries);
document.querySelector('#new-entry').addEventListener('click', () => showForm());
document.querySelector('#cancel-entry').addEventListener('click', () => { panel.hidden = true; });
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(form));
  values.source_page = values.source_page ? Number(values.source_page) : null;
  try {
    const response = await fetch(editingId ? `/api/rules-reference/${editingId}` : '/api/rules-reference', {
      method: editingId ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(values),
    });
    if (!response.ok) throw new Error('Could not save. Check the fields and use an Archives of Nethys link.');
    panel.hidden = true;
    await loadEntries();
  } catch (error) {
    formError.textContent = error.message;
    formError.hidden = false;
  }
});
loadEntries();
