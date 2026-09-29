import { api, clearCsrfToken } from './api.js';

const app = document.querySelector('#app');
const toast = document.querySelector('#toast');
const state = { user: null, metadata: null, map: null };

const escapeHtml = (value = '') => String(value)
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#039;');

const formatDate = (value) => new Intl.DateTimeFormat('it-IT', {
  dateStyle: 'medium', timeStyle: 'short'
}).format(new Date(value));

const truncate = (text, max = 145) => text.length > max ? `${text.slice(0, max).trim()}…` : text;
const isModerator = () => state.user && ['base', 'amministratore'].includes(state.user.ruolo);

function showToast(message, type = 'success') {
  toast.textContent = message;
  toast.className = `toast ${type === 'error' ? 'error' : ''}`;
  toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => { toast.hidden = true; }, 4500);
}

function errorMarkup(error) {
  const details = error.details
    ? `<ul>${Object.entries(error.details).flatMap(([field, messages]) =>
        messages.map((message) => `<li><strong>${escapeHtml(field)}:</strong> ${escapeHtml(message)}</li>`)
      ).join('')}</ul>`
    : '';
  return `<div class="panel error-message" role="alert"><p>${escapeHtml(error.message)}</p>${details}</div>`;
}

function setLoading(label = 'Caricamento…') {
  app.innerHTML = `<div class="loading" role="status">${escapeHtml(label)}</div>`;
}

function updateAuthUI() {
  document.querySelectorAll('[data-auth-only]').forEach((element) => { element.hidden = !state.user; });
  document.querySelectorAll('[data-guest-only]').forEach((element) => { element.hidden = Boolean(state.user); });
  document.querySelectorAll('[data-moderator-only]').forEach((element) => { element.hidden = !isModerator(); });
}

function focusMain() {
  document.querySelector('#contenuto').focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function requireUser() {
  if (state.user) return true;
  showToast('Accedi per utilizzare questa funzione.', 'error');
  location.hash = '#login';
  return false;
}

function options(items, valueKey, labelKey, selected, placeholder = 'Tutti') {
  return [
    `<option value="">${escapeHtml(placeholder)}</option>`,
    ...items.map((item) => `<option value="${escapeHtml(item[valueKey])}" ${String(selected) === String(item[valueKey]) ? 'selected' : ''}>${escapeHtml(item[labelKey])}</option>`)
  ].join('');
}

function categoryChips(categories = []) {
  return categories.map((category) =>
    `<span class="chip">${escapeHtml(category.nome)}</span>`
  ).join('');
}

function reportCard(report) {
  const media = report.anteprimaTipo?.startsWith('image/')
    ? `<img class="card-media" src="${escapeHtml(report.anteprima)}" alt="${escapeHtml(report.anteprimaAlt || '')}" loading="lazy">`
    : `<div class="card-media video-placeholder" aria-label="La segnalazione contiene un video">▶ Video allegato</div>`;
  return `
    <article class="report-card">
      ${media}
      <div class="card-body">
        <div class="meta-row">
          <span class="chip">${escapeHtml(report.tipo)}</span>
          <span class="status">${escapeHtml(report.stato.replaceAll('_', ' '))}</span>
        </div>
        <h3><a href="#report/${report.id}">${escapeHtml(report.titolo)}</a></h3>
        <p>${escapeHtml(truncate(report.descrizione))}</p>
        <div class="chips">${categoryChips(report.categorie)}</div>
        <div class="card-footer">
          <small>${escapeHtml(report.quartiere || report.indirizzo || 'Milano')}</small>
          <span class="support-count" aria-label="${report.numeroSostegni} sostegni">♥ ${report.numeroSostegni}</span>
        </div>
      </div>
    </article>`;
}

async function renderHome() {
  setLoading();
  const query = new URLSearchParams(location.hash.split('?')[1] ?? '');
  const filters = Object.fromEntries(query.entries());
  app.innerHTML = `
    <section class="hero">
      <p class="eyebrow">Insieme per Milano</p>
      <h1>La città cambia quando la voce di tutti diventa una priorità.</h1>
      <p>Segnala un problema, proponi un’idea e sostieni gli interventi che possono migliorare il tuo quartiere.</p>
      <div class="hero-actions">
        <a class="button" href="${state.user ? '#new' : '#register'}">${state.user ? 'Crea una segnalazione' : 'Partecipa alla community'}</a>
        <a class="button button-secondary" href="#reports">Esplora le priorità</a>
      </div>
    </section>

    <section id="reports">
      <div class="section-heading">
        <div><p class="eyebrow">Priorità cittadine</p><h2>Segnalazioni e proposte</h2></div>
        <p id="results-count" aria-live="polite"></p>
      </div>
      <form class="filter-panel filter-grid" id="filter-form" role="search">
        <label class="field"><span>Cerca</span><input name="q" value="${escapeHtml(filters.q || '')}" placeholder="Titolo, descrizione o indirizzo"></label>
        <label class="field"><span>Tipo</span><select name="tipo">${options([{id:'segnalazione',nome:'Segnalazione'},{id:'proposta',nome:'Proposta'}], 'id', 'nome', filters.tipo)}</select></label>
        <label class="field"><span>Stato</span><select name="stato">${options(state.metadata.stati, 'codice', 'etichetta', filters.stato)}</select></label>
        <label class="field"><span>Quartiere</span><select name="idQuartiere">${options(state.metadata.quartieri, 'id', 'nome', filters.idQuartiere)}</select></label>
        <label class="field"><span>Categoria</span><select name="idCategoria">${options(state.metadata.categorie, 'id', 'nome', filters.idCategoria)}</select></label>
        <label class="field"><span>Ordina</span><select name="ordine"><option value="recenti">Più recenti</option><option value="sostenute" ${filters.ordine === 'sostenute' ? 'selected' : ''}>Più sostenute</option></select></label>
        <button class="button" type="submit">Filtra</button>
      </form>
      <div id="report-results" class="loading" role="status">Caricamento segnalazioni…</div>
    </section>`;

  document.querySelector('#filter-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const params = new URLSearchParams(new FormData(event.currentTarget));
    [...params.entries()].forEach(([key, value]) => { if (!value) params.delete(key); });
    location.hash = `#home?${params}`;
  });
  await loadReportResults(filters);
}

async function loadReportResults(filters) {
  const target = document.querySelector('#report-results');
  const params = new URLSearchParams(filters);
  try {
    const data = await api(`/api/reports?${params}`);
    document.querySelector('#results-count').textContent = `${data.totale} risultati`;
    if (!data.items.length) {
      target.className = 'empty-state';
      target.innerHTML = '<h3>Nessun risultato</h3><p>Prova a modificare i filtri oppure pubblica la prima segnalazione.</p>';
      return;
    }
    target.className = '';
    target.innerHTML = `
      <div class="report-grid">${data.items.map(reportCard).join('')}</div>
      ${data.pagine > 1 ? `<nav class="pagination" aria-label="Pagine dei risultati">${Array.from({ length: data.pagine }, (_, index) => {
        const page = index + 1;
        return `<button class="button button-small" data-page="${page}" ${page === data.pagina ? 'aria-current="page"' : ''}>${page}</button>`;
      }).join('')}</nav>` : ''}`;
    target.querySelectorAll('[data-page]').forEach((button) => button.addEventListener('click', () => {
      const next = new URLSearchParams(filters);
      next.set('pagina', button.dataset.page);
      location.hash = `#home?${next}`;
    }));
  } catch (error) {
    target.className = '';
    target.innerHTML = errorMarkup(error);
  }
}

function attachmentMarkup(attachment) {
  if (attachment.tipo.startsWith('image/')) {
    return `<img class="detail-media" src="${escapeHtml(attachment.url)}" alt="${escapeHtml(attachment.descrizione)}">`;
  }
  return `<video class="detail-media" controls preload="metadata"><source src="${escapeHtml(attachment.url)}" type="${escapeHtml(attachment.tipo)}">Il browser non supporta questo video.</video><p class="hint">${escapeHtml(attachment.descrizione)}</p>`;
}

async function renderReport(id) {
  setLoading('Caricamento della segnalazione…');
  try {
    const { report } = await api(`/api/reports/${id}`);
    const mayRemove = state.user && (state.user.id === report.idAutore || isModerator());
    app.innerHTML = `
      <div class="section-heading"><a href="#home">← Torna alle segnalazioni</a></div>
      <div class="detail-layout">
        <div class="detail-main">
          <article class="panel">
            <div class="meta-row"><span class="chip">${escapeHtml(report.tipo)}</span><span class="status">${escapeHtml(report.stato.replaceAll('_', ' '))}</span></div>
            <h1 class="detail-title">${escapeHtml(report.titolo)}</h1>
            <div class="chips">${categoryChips(report.categorie)}</div>
            <p class="hint">Pubblicata da ${escapeHtml(report.autore)} il ${formatDate(report.dataCreazione)}</p>
            <p class="prose">${escapeHtml(report.descrizione)}</p>
            ${report.allegati.map(attachmentMarkup).join('')}
          </article>
          ${report.latitudine !== null && report.longitudine !== null ? `<section class="panel"><h2>Posizione</h2><p>${escapeHtml(report.indirizzo || 'Coordinate indicate dall’utente')}</p><div id="map" class="map" aria-label="Mappa della posizione segnalata"></div></section>` : ''}
          <section class="panel">
            <div class="section-heading"><div><p class="eyebrow">Discussione</p><h2>Commenti</h2></div><span>${report.commenti.length}</span></div>
            <div>${report.commenti.length ? report.commenti.map((comment) => `
              <article class="comment">
                <header><strong>${escapeHtml(comment.autore)}</strong><time datetime="${escapeHtml(comment.dataPubblicazione)}">${formatDate(comment.dataPubblicazione)}</time></header>
                <p>${escapeHtml(comment.testo)}</p>
                ${isModerator() ? `<button class="button button-small button-danger" data-remove-comment="${comment.id}">Rimuovi</button>` : ''}
              </article>`).join('') : '<p class="hint">Non ci sono ancora commenti.</p>'}</div>
            ${state.user ? `<form id="comment-form" class="stack"><label class="field"><span>Aggiungi un commento</span><textarea name="testo" minlength="2" maxlength="1500" required></textarea></label><button class="button" type="submit">Pubblica commento</button></form>` : '<p><a href="#login">Accedi</a> per commentare.</p>'}
          </section>
        </div>
        <aside class="detail-sidebar">
          <section class="panel">
            <p class="eyebrow">Partecipazione</p>
            <strong class="support-count">♥ ${report.numeroSostegni} sostegni</strong>
            ${state.user ? `<button id="support-button" class="button ${report.sostenutaDaMe ? 'button-secondary' : ''}" type="button">${report.sostenutaDaMe ? 'Ritira sostegno' : 'Sostieni questa priorità'}</button>` : '<a class="button" href="#login">Accedi per sostenere</a>'}
            ${mayRemove ? '<button id="remove-report" class="button button-danger" type="button">Rimuovi segnalazione</button>' : ''}
          </section>
          ${isModerator() ? `<section class="panel"><h2>Gestione stato</h2><form id="state-form" class="stack"><label class="field"><span>Nuovo stato</span><select name="stato" required>${options(state.metadata.stati, 'codice', 'etichetta', report.stato, 'Seleziona')}</select></label><label class="field"><span>Motivazione</span><textarea name="motivazione" maxlength="500"></textarea></label><button class="button" type="submit">Aggiorna stato</button></form></section>` : ''}
          <section class="panel"><h2>Informazioni</h2><dl><dt>Quartiere</dt><dd>${escapeHtml(report.quartiere || 'Non indicato')}</dd><dt>Indirizzo</dt><dd>${escapeHtml(report.indirizzo || 'Non indicato')}</dd></dl></section>
          <section class="panel"><h2>Cronologia</h2><ol class="timeline">${report.storico.length ? report.storico.map((item) => `<li><strong>${escapeHtml(item.statoSuccessivo.replaceAll('_', ' '))}</strong><br><small>${formatDate(item.dataModifica)} · ${escapeHtml(item.autore)}</small>${item.motivazione ? `<p>${escapeHtml(item.motivazione)}</p>` : ''}</li>`).join('') : '<li>Nessuna variazione registrata.</li>'}</ol></section>
        </aside>
      </div>`;

    if (report.latitudine !== null && report.longitudine !== null) initMap(Number(report.latitudine), Number(report.longitudine), report.titolo);
    bindReportActions(report);
  } catch (error) {
    app.innerHTML = errorMarkup(error);
  }
}

function initMap(latitude, longitude, title) {
  if (!window.L) {
    document.querySelector('#map').innerHTML = `<p class="error-message">Mappa non disponibile. Coordinate: ${latitude}, ${longitude}</p>`;
    return;
  }
  state.map?.remove();
  state.map = window.L.map('map').setView([latitude, longitude], 16);
  window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors', maxZoom: 19
  }).addTo(state.map);
  window.L.marker([latitude, longitude]).addTo(state.map).bindPopup(escapeHtml(title)).openPopup();
}

function bindReportActions(report) {
  document.querySelector('#support-button')?.addEventListener('click', async () => {
    try {
      await api(`/api/reports/${report.id}/support`, { method: report.sostenutaDaMe ? 'DELETE' : 'PUT' });
      showToast(report.sostenutaDaMe ? 'Sostegno ritirato.' : 'Grazie per il tuo sostegno!');
      await renderReport(report.id);
    } catch (error) { showToast(error.message, 'error'); }
  });

  document.querySelector('#comment-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const submit = event.currentTarget.querySelector('button');
    submit.disabled = true;
    try {
      await api(`/api/reports/${report.id}/comments`, { method: 'POST', body: Object.fromEntries(new FormData(event.currentTarget)) });
      showToast('Commento pubblicato.');
      await renderReport(report.id);
    } catch (error) { showToast(error.message, 'error'); submit.disabled = false; }
  });

  document.querySelector('#state-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await api(`/api/reports/${report.id}/state`, { method: 'PATCH', body: Object.fromEntries(new FormData(event.currentTarget)) });
      showToast('Stato aggiornato.');
      await renderReport(report.id);
    } catch (error) { showToast(error.message, 'error'); }
  });

  document.querySelector('#remove-report')?.addEventListener('click', async () => {
    if (!window.confirm('Vuoi rimuovere questa segnalazione? L’operazione verrà registrata.')) return;
    try {
      await api(`/api/reports/${report.id}`, { method: 'DELETE' });
      showToast('Segnalazione rimossa.');
      location.hash = '#home';
    } catch (error) { showToast(error.message, 'error'); }
  });

  document.querySelectorAll('[data-remove-comment]').forEach((button) => button.addEventListener('click', async () => {
    if (!window.confirm('Rimuovere questo commento?')) return;
    try {
      await api(`/api/moderation/comments/${button.dataset.removeComment}`, { method: 'DELETE' });
      showToast('Commento rimosso.');
      await renderReport(report.id);
    } catch (error) { showToast(error.message, 'error'); }
  }));
}

async function renderNewReport() {
  if (!requireUser()) return;
  app.innerHTML = `
    <div class="section-heading"><div><p class="eyebrow">Partecipa</p><h1>Nuova segnalazione o proposta</h1><p>Descrivi la priorità in modo chiaro e allega una prova visiva.</p></div></div>
    <form id="report-form" class="panel stack" enctype="multipart/form-data">
      <div class="filter-grid">
        <label class="field"><span>Tipo</span><select name="tipo" required><option value="segnalazione">Segnalazione</option><option value="proposta">Proposta</option></select></label>
        <label class="field"><span>Quartiere</span><select name="idQuartiere">${options(state.metadata.quartieri, 'id', 'nome', state.user.idQuartiere, 'Seleziona')}</select></label>
      </div>
      <label class="field"><span>Titolo</span><input name="titolo" minlength="5" maxlength="200" required placeholder="Es. Illuminazione insufficiente in via…"></label>
      <label class="field"><span>Descrizione</span><textarea name="descrizione" minlength="20" maxlength="5000" required placeholder="Spiega cosa accade, da quanto tempo e perché è importante intervenire."></textarea></label>
      <fieldset><legend>Categorie (da 1 a 5)</legend><div class="category-options">${state.metadata.categorie.map((category) => `<label class="check-option"><input type="checkbox" name="categorie" value="${category.id}"><span><strong>${escapeHtml(category.nome)}</strong><br><small>${escapeHtml(category.descrizione || '')}</small></span></label>`).join('')}</div></fieldset>
      <div class="filter-grid">
        <label class="field"><span>Indirizzo</span><input name="indirizzo" maxlength="255" placeholder="Via e numero civico"></label>
        <label class="field"><span>Latitudine</span><input name="latitudine" type="number" min="-90" max="90" step="0.000001"></label>
        <label class="field"><span>Longitudine</span><input name="longitudine" type="number" min="-180" max="180" step="0.000001"></label>
        <button class="button button-secondary" id="location-button" type="button">Usa la mia posizione</button>
      </div>
      <label class="field"><span>Foto o video obbligatorio</span><input name="allegato" id="attachment-input" type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/webm" required><small class="hint">JPG, PNG, WebP, MP4 o WebM. Massimo 12 MB.</small></label>
      <div id="file-preview"></div>
      <label class="field"><span>Descrizione accessibile dell’allegato</span><textarea name="descrizioneAccessibile" minlength="5" maxlength="1000" required placeholder="Descrivi ciò che si vede per chi usa un lettore di schermo."></textarea></label>
      <div id="form-error"></div>
      <div class="form-actions"><button class="button" type="submit">Pubblica</button><a class="button button-secondary" href="#home">Annulla</a></div>
    </form>`;

  const form = document.querySelector('#report-form');
  document.querySelector('#location-button').addEventListener('click', () => {
    if (!navigator.geolocation) return showToast('Geolocalizzazione non supportata.', 'error');
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        form.elements.latitudine.value = coords.latitude.toFixed(6);
        form.elements.longitudine.value = coords.longitude.toFixed(6);
        showToast('Coordinate inserite. Controlla che siano corrette.');
      },
      () => showToast('Non è stato possibile ottenere la posizione.', 'error'),
      { enableHighAccuracy: true, timeout: 10_000 }
    );
  });
  document.querySelector('#attachment-input').addEventListener('change', (event) => {
    const file = event.target.files[0];
    const preview = document.querySelector('#file-preview');
    preview.innerHTML = '';
    if (!file) return;
    const url = URL.createObjectURL(file);
    preview.innerHTML = file.type.startsWith('image/')
      ? `<img class="preview" src="${url}" alt="Anteprima del file selezionato">`
      : `<video class="preview" src="${url}" controls aria-label="Anteprima del video selezionato"></video>`;
  });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const selected = [...form.querySelectorAll('[name="categorie"]:checked')].map((input) => Number(input.value));
    if (!selected.length || selected.length > 5) {
      document.querySelector('#form-error').innerHTML = '<p class="error-message" role="alert">Seleziona da una a cinque categorie.</p>';
      return;
    }
    const data = new FormData(form);
    data.delete('categorie');
    data.set('categorie', JSON.stringify(selected));
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;
    submit.textContent = 'Pubblicazione…';
    try {
      const result = await api('/api/reports', { method: 'POST', body: data });
      showToast('Segnalazione pubblicata con successo.');
      location.hash = `#report/${result.report.id}`;
    } catch (error) {
      document.querySelector('#form-error').innerHTML = errorMarkup(error);
      submit.disabled = false;
      submit.textContent = 'Pubblica';
    }
  });
}

function renderAuth(mode) {
  const register = mode === 'register';
  app.innerHTML = `
    <div class="auth-layout">
      <section class="auth-copy"><p class="eyebrow">Community verificabile</p><h1>${register ? 'La tua città ha bisogno della tua voce.' : 'Bentornato nella tua città.'}</h1><p>Ogni azione è collegata a un profilo: meno spam, più fiducia e proposte concrete.</p></section>
      <form id="auth-form" class="auth-card stack">
        <h2>${register ? 'Crea il tuo account' : 'Accedi'}</h2>
        ${register ? `<div class="filter-grid"><label class="field"><span>Nome</span><input name="nome" autocomplete="given-name" minlength="2" maxlength="100" required></label><label class="field"><span>Cognome</span><input name="cognome" autocomplete="family-name" minlength="2" maxlength="100" required></label></div>` : ''}
        <label class="field"><span>Email</span><input name="email" type="email" autocomplete="email" maxlength="254" required></label>
        <label class="field"><span>Password</span><input name="password" type="password" autocomplete="${register ? 'new-password' : 'current-password'}" minlength="${register ? '10' : '1'}" maxlength="128" required>${register ? '<small class="hint">Almeno 10 caratteri, una maiuscola, una minuscola e un numero.</small>' : ''}</label>
        ${register ? `<label class="field"><span>Quartiere</span><select name="idQuartiere">${options(state.metadata.quartieri, 'id', 'nome', '', 'Seleziona (facoltativo)')}</select></label>` : ''}
        <div id="auth-error"></div>
        <button class="button" type="submit">${register ? 'Registrati' : 'Accedi'}</button>
        <p>${register ? 'Hai già un account? <a href="#login">Accedi</a>' : 'Non hai un account? <a href="#register">Registrati</a>'}</p>
      </form>
    </div>`;
  document.querySelector('#auth-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const body = Object.fromEntries(new FormData(form));
    if (body.idQuartiere === '') body.idQuartiere = null;
    const submit = form.querySelector('button');
    submit.disabled = true;
    try {
      const data = await api(`/api/auth/${register ? 'register' : 'login'}`, { method: 'POST', body });
      state.user = data.user;
      updateAuthUI();
      showToast(register ? 'Account creato. Benvenuto!' : 'Accesso effettuato.');
      location.hash = '#home';
    } catch (error) {
      document.querySelector('#auth-error').innerHTML = errorMarkup(error);
      submit.disabled = false;
    }
  });
}

function renderProfile() {
  if (!requireUser()) return;
  app.innerHTML = `
    <div class="section-heading"><div><p class="eyebrow">Account</p><h1>Il tuo profilo</h1><p>Gestisci le informazioni associate alle tue attività.</p></div></div>
    <div class="detail-layout">
      <form id="profile-form" class="panel stack">
        <label class="field"><span>Nome</span><input name="nome" value="${escapeHtml(state.user.nome)}" minlength="2" maxlength="100" required></label>
        <label class="field"><span>Cognome</span><input name="cognome" value="${escapeHtml(state.user.cognome)}" minlength="2" maxlength="100" required></label>
        <label class="field"><span>Email</span><input value="${escapeHtml(state.user.email)}" disabled><small class="hint">L’email non è modificabile da questa schermata.</small></label>
        <label class="field"><span>Quartiere</span><select name="idQuartiere">${options(state.metadata.quartieri, 'id', 'nome', state.user.idQuartiere, 'Nessun quartiere')}</select></label>
        <button class="button" type="submit">Salva modifiche</button>
      </form>
      <aside class="panel"><h2>Sicurezza e privacy</h2><p>Il tuo ruolo è <strong>${escapeHtml(state.user.ruolo)}</strong>. La cancellazione è logica per mantenere l’integrità e la tracciabilità delle attività.</p><button id="delete-account" class="button button-danger" type="button">Cancella account</button></aside>
    </div>`;
  document.querySelector('#profile-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.currentTarget));
    if (!body.idQuartiere) body.idQuartiere = null;
    try {
      const data = await api('/api/auth/me', { method: 'PUT', body });
      state.user = data.user;
      showToast('Profilo aggiornato.');
      renderProfile();
    } catch (error) { showToast(error.message, 'error'); }
  });
  document.querySelector('#delete-account').addEventListener('click', async () => {
    if (!window.confirm('Confermi la cancellazione del tuo account? Non potrai più accedere.')) return;
    try {
      await api('/api/auth/me', { method: 'DELETE' });
      state.user = null;
      clearCsrfToken();
      updateAuthUI();
      showToast('Account cancellato.');
      location.hash = '#home';
    } catch (error) { showToast(error.message, 'error'); }
  });
}

async function renderModeration() {
  if (!requireUser()) return;
  if (!isModerator()) {
    app.innerHTML = '<div class="panel error-message"><h1>Accesso negato</h1><p>Questa sezione è riservata ai membri del comitato.</p></div>';
    return;
  }
  setLoading('Caricamento dashboard…');
  try {
    const [users, events] = await Promise.all([api('/api/moderation/users'), api('/api/moderation/events')]);
    app.innerHTML = `
      <div class="section-heading"><div><p class="eyebrow">Comitato</p><h1>Dashboard di moderazione</h1><p>Gestisci account e controlla le attività recenti.</p></div></div>
      <section class="panel"><h2>Utenti</h2><div class="table-wrap"><table><thead><tr><th>Utente</th><th>Ruolo</th><th>Stato</th><th>Quartiere</th><th>Azioni</th></tr></thead><tbody>${users.items.map((user) => `<tr><td><strong>${escapeHtml(user.nome)} ${escapeHtml(user.cognome)}</strong><br><small>${escapeHtml(user.email)}</small></td><td>${escapeHtml(user.ruolo)}</td><td>${escapeHtml(user.statoAccount)}</td><td>${escapeHtml(user.quartiere || '—')}</td><td>${user.id === state.user.id || user.statoAccount === 'cancellato' ? '—' : user.statoAccount === 'bloccato' ? `<button class="button button-small" data-unblock="${user.id}">Sblocca</button>` : `<button class="button button-small button-danger" data-block="${user.id}">Blocca</button>`}</td></tr>`).join('')}</tbody></table></div></section>
      <section class="panel"><h2>Attività recenti</h2><div class="table-wrap"><table><thead><tr><th>Data</th><th>Azione</th><th>Esecutore</th><th>Dettagli</th></tr></thead><tbody>${events.items.map((event) => `<tr><td>${formatDate(event.dataOra)}</td><td>${escapeHtml(event.tipo)}</td><td>${escapeHtml(event.esecutore || 'Sistema')}</td><td>${escapeHtml(event.dettagli)}</td></tr>`).join('')}</tbody></table></div></section>`;
    document.querySelectorAll('[data-block]').forEach((button) => button.addEventListener('click', async () => {
      const reason = window.prompt('Motivazione del blocco (almeno 10 caratteri):');
      if (!reason) return;
      try {
        await api(`/api/moderation/users/${button.dataset.block}/block`, { method: 'POST', body: { motivazione: reason, dataFinePrevista: null } });
        showToast('Account bloccato.');
        await renderModeration();
      } catch (error) { showToast(error.message, 'error'); }
    }));
    document.querySelectorAll('[data-unblock]').forEach((button) => button.addEventListener('click', async () => {
      const reason = window.prompt('Motivo della revoca del blocco:');
      if (!reason) return;
      try {
        await api(`/api/moderation/users/${button.dataset.unblock}/unblock`, { method: 'POST', body: { motivoRevoca: reason } });
        showToast('Account sbloccato.');
        await renderModeration();
      } catch (error) { showToast(error.message, 'error'); }
    }));
  } catch (error) { app.innerHTML = errorMarkup(error); }
}

function renderAccessibility() {
  app.innerHTML = `
    <div class="section-heading"><div><p class="eyebrow">Informazioni</p><h1>Accessibilità e privacy</h1></div></div>
    <article class="panel prose"><h2>Accessibilità</h2><p>L’interfaccia usa elementi semantici, navigazione da tastiera, focus visibile, testi alternativi obbligatori per gli allegati e controlli per contrasto, dimensione del testo e lettura vocale. Se incontri una barriera, segnalala al comitato.</p><h2>Privacy</h2><p>Inserisci soltanto informazioni necessarie alla segnalazione. Evita volti, targhe, documenti e altri dati personali nelle immagini. Le coordinate sono facoltative e devono essere controllate prima della pubblicazione.</p><h2>Limiti della lettura vocale</h2><p>La funzione usa le voci disponibili nel browser e non sostituisce un lettore di schermo completo.</p></article>`;
}

async function router() {
  const route = (location.hash || '#home').slice(1).split('?')[0];
  state.map?.remove();
  state.map = null;
  try {
    if (route === 'home' || route === '') await renderHome();
    else if (route.startsWith('report/')) await renderReport(route.split('/')[1]);
    else if (route === 'new') await renderNewReport();
    else if (route === 'login') renderAuth('login');
    else if (route === 'register') renderAuth('register');
    else if (route === 'profile') renderProfile();
    else if (route === 'moderation') await renderModeration();
    else if (route === 'accessibility') renderAccessibility();
    else app.innerHTML = '<div class="empty-state"><h1>Pagina non trovata</h1><a class="button" href="#home">Torna alla homepage</a></div>';
  } catch (error) {
    app.innerHTML = errorMarkup(error);
  }
  focusMain();
}

function setupGlobalControls() {
  const menuButton = document.querySelector('#menu-button');
  const nav = document.querySelector('#main-nav');
  menuButton.addEventListener('click', () => {
    const open = nav.classList.toggle('open');
    menuButton.setAttribute('aria-expanded', String(open));
  });
  nav.addEventListener('click', () => {
    nav.classList.remove('open');
    menuButton.setAttribute('aria-expanded', 'false');
  });

  const contrast = document.querySelector('#contrast-button');
  const font = document.querySelector('#font-button');
  const storedContrast = localStorage.getItem('highContrast') === 'true';
  const storedFont = localStorage.getItem('largeText') === 'true';
  document.body.classList.toggle('high-contrast', storedContrast);
  document.body.classList.toggle('large-text', storedFont);
  contrast.setAttribute('aria-pressed', String(storedContrast));
  font.setAttribute('aria-pressed', String(storedFont));

  contrast.addEventListener('click', () => {
    const enabled = document.body.classList.toggle('high-contrast');
    contrast.setAttribute('aria-pressed', String(enabled));
    localStorage.setItem('highContrast', String(enabled));
  });
  font.addEventListener('click', () => {
    const enabled = document.body.classList.toggle('large-text');
    font.setAttribute('aria-pressed', String(enabled));
    localStorage.setItem('largeText', String(enabled));
  });
  document.querySelector('#speech-button').addEventListener('click', (event) => {
    if (!('speechSynthesis' in window)) return showToast('Lettura vocale non disponibile.', 'error');
    if (window.speechSynthesis.speaking) {
      window.speechSynthesis.cancel();
      event.currentTarget.textContent = 'Leggi la pagina';
      return;
    }
    const utterance = new SpeechSynthesisUtterance(app.textContent);
    utterance.lang = 'it-IT';
    utterance.onend = () => { event.currentTarget.textContent = 'Leggi la pagina'; };
    event.currentTarget.textContent = 'Interrompi lettura';
    window.speechSynthesis.speak(utterance);
  });
  document.querySelector('#logout-button').addEventListener('click', async () => {
    try {
      await api('/api/auth/logout', { method: 'POST' });
      state.user = null;
      clearCsrfToken();
      updateAuthUI();
      showToast('Sessione terminata.');
      location.hash = '#home';
    } catch (error) { showToast(error.message, 'error'); }
  });
}

async function init() {
  setupGlobalControls();
  try {
    const [auth, metadata] = await Promise.all([api('/api/auth/me'), api('/api/metadata')]);
    state.user = auth.user;
    state.metadata = metadata;
    updateAuthUI();
    window.addEventListener('hashchange', router);
    await router();
  } catch (error) {
    app.innerHTML = `<div class="panel error-message"><h1>Applicazione non disponibile</h1><p>${escapeHtml(error.message)}</p><p>Controlla la configurazione del server e del database.</p></div>`;
  }
}

init();
