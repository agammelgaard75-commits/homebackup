(() => {
  const button = document.getElementById('copy-all-emails');
  const form = document.getElementById('service-search-form');
  const feedback = document.getElementById('copy-feedback');
  const fallback = document.getElementById('email-fallback');
  const manual = document.getElementById('manual-copy');
  if (!button || !form) return;
  button.addEventListener('click', async () => {
    feedback.textContent = 'Preparing addresses…';
    manual.hidden = true;
    try {
      const query = new URLSearchParams(new FormData(form));
      const response = await fetch(`${button.dataset.exportUrl}?${query}`, {credentials: 'same-origin', cache: 'no-store'});
      if (!response.ok) throw new Error('Unable to collect addresses. Try the search again.');
      const result = await response.json();
      if (!result.count) {
        feedback.textContent = 'No email addresses match these filters.';
        return;
      }
      try {
        await navigator.clipboard.writeText(result.emails);
        feedback.textContent = `Copied ${result.count} email address${result.count === 1 ? '' : 'es'}.`;
      } catch (_) {
        fallback.value = result.emails;
        manual.hidden = false;
        fallback.focus();
        fallback.select();
        feedback.textContent = `Clipboard access was unavailable. Select and copy ${result.count} address${result.count === 1 ? '' : 'es'} from the field below.`;
      }
    } catch (_) {
      feedback.textContent = 'Unable to collect addresses. Try the search again.';
    }
  });
})();
