const search = document.querySelector('#tool-search');
if (search) {
  const cards = [...document.querySelectorAll('.tool-card')];
  const noResults = document.querySelector('#no-results');
  search.addEventListener('input', () => {
    const query = search.value.trim().toLowerCase();
    let visible = 0;
    for (const card of cards) {
      const matches = card.dataset.toolSearch.includes(query);
      card.hidden = !matches;
      if (matches) visible += 1;
    }
    noResults.hidden = visible > 0;
  });
}
const partyProgress = document.querySelector('#dashboard-xp');
if (partyProgress) {
  fetch('/api/treasure-xp/trackers').then(response => response.ok ? response.json() : [])
    .then(rows => {
      if (!rows.length) return;
      const preferred = Number(localStorage.getItem('reward-tracker'));
      const party = rows.find(row => row.id === preferred) || rows[0];
      const threshold = {standard: 1000, fast: 800, slow: 1200}[party.method];
      document.querySelector('#dashboard-xp-text').textContent =
        ` · ${party.name} · Level ${party.level} · ${threshold ? `${party.current_xp}/${threshold} XP` : 'Milestone advancement'}`;
      partyProgress.hidden = false;
    }).catch(() => {});
}
