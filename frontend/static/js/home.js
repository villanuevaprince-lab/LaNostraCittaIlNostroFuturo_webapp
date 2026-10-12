const list = document.querySelector("#report-list");
const status = document.querySelector("#list-status");
const search = document.querySelector("#search-input");
const neighborhood = document.querySelector("#filter-neighborhood");
const category = document.querySelector("#filter-category");
const state = document.querySelector("#filter-state");
const isAuthenticated = document.querySelector("[data-authenticated]")?.dataset.authenticated === "true";
const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
let searchTimer;
let requestController;

async function loadFilters() {
  const [quartieriResponse, categoriesResponse] = await Promise.all([
    fetch("/api/quartieri"), fetch("/api/categorie"),
  ]);
  const [quartieri, categories] = await Promise.all([quartieriResponse.json(), categoriesResponse.json()]);
  quartieri.forEach((row) => neighborhood.add(new Option(row.nome, row.id)));
  categories.forEach((row) => category.add(new Option(row.nome, row.id)));
}

async function loadReports() {
  requestController?.abort();
  requestController = new AbortController();
  status.textContent = "Caricamento…";
  list.replaceChildren();
  const params = new URLSearchParams();
  if (search.value.trim()) params.set("q", search.value.trim());
  if (neighborhood.value) params.set("quartiere", neighborhood.value);
  if (category.value) params.set("categoria", category.value);
  if (state.value) params.set("stato", state.value);
  try {
    const response = await fetch(`/api/segnalazioni?${params}`, {
      signal: requestController.signal, credentials: "same-origin",
    });
    const rows = await response.json();
    if (!response.ok) throw new Error(rows.error || "Impossibile caricare le segnalazioni.");
    rows.forEach((report) => list.append(createCard(report)));
    status.textContent = rows.length ? `${rows.length} contenuti trovati` : "Nessun contenuto trovato.";
  } catch (error) {
    if (error.name !== "AbortError") status.textContent = error.message;
  }
}

function createCard(report) {
  const card = document.createElement("article"); card.className = "report-card";
  const badge = document.createElement("span"); badge.className = "badge";
  badge.textContent = `${report.tipo} · ${String(report.stato).replaceAll("_", " ")}`;
  const title = document.createElement("h3"); title.textContent = report.titolo;
  const description = document.createElement("p"); description.textContent = report.descrizione;
  const meta = document.createElement("p"); meta.className = "report-meta";
  [report.indirizzo || "Luogo non indicato", report.autore, `${report.sostegni} sostegni`]
    .forEach((value) => { const item = document.createElement("span"); item.textContent = value; meta.append(item); });
  card.append(badge, title, description, meta);
  if (report.allegato_id) {
    const image = document.createElement("img"); image.src = `/api/allegati/${report.allegato_id}`;
    image.alt = `Allegato della segnalazione: ${report.titolo}`; image.loading = "lazy";
    image.className = "report-image"; card.append(image);
  }
  if (isAuthenticated) {
    const support = document.createElement("button"); support.className = "button button-secondary";
    support.textContent = "Caricamento sostegno…";
    const updateSupport = async (supported) => {
      const response = await fetch(`/api/segnalazioni/${report.id}/sostegno`, {
        method: supported ? "DELETE" : "PUT", credentials: "same-origin", headers: { "X-CSRFToken": csrf },
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Aggiornamento non riuscito.");
      support.dataset.supported = String(!supported);
      support.textContent = supported ? "Sostieni" : "Ritira sostegno";
    };
    fetch(`/api/segnalazioni/${report.id}/sostegno`, { credentials: "same-origin" })
      .then((response) => response.json()).then((data) => {
        support.dataset.supported = String(data.sostenuta);
        support.textContent = data.sostenuta ? "Ritira sostegno" : "Sostieni";
      }).catch(() => { support.textContent = "Sostegno non disponibile"; support.disabled = true; });
    support.addEventListener("click", async () => {
      support.disabled = true;
      try { await updateSupport(support.dataset.supported === "true"); }
      catch (error) { status.textContent = error.message; }
      finally { support.disabled = false; }
    });

    const comments = document.createElement("details");
    const summary = document.createElement("summary"); summary.textContent = "Commenti";
    const commentsList = document.createElement("div");
    const commentForm = document.createElement("form");
    const textarea = document.createElement("textarea"); textarea.name = "testo"; textarea.maxLength = 3000;
    textarea.required = true; textarea.placeholder = "Aggiungi un commento";
    const submit = document.createElement("button"); submit.className = "button"; submit.textContent = "Invia commento";
    commentForm.append(textarea, submit);
    const loadComments = async () => {
      const response = await fetch(`/api/segnalazioni/${report.id}`);
      const data = await response.json(); commentsList.replaceChildren();
      (data.commenti || []).forEach((comment) => {
        const p = document.createElement("p"); p.textContent = `${comment.autore || "Cittadino"}: ${comment.testo}`;
        commentsList.append(p);
      });
    };
    comments.addEventListener("toggle", () => { if (comments.open) loadComments(); });
    commentForm.addEventListener("submit", async (event) => {
      event.preventDefault(); submit.disabled = true;
      try {
        const response = await fetch(`/api/segnalazioni/${report.id}/commenti`, {
          method: "POST", credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
          body: JSON.stringify({ testo: textarea.value }),
        });
        const data = await response.json(); if (!response.ok) throw new Error(data.error);
        textarea.value = ""; await loadComments();
      } catch (error) { status.textContent = error.message; }
      finally { submit.disabled = false; }
    });
    comments.append(summary, commentsList, commentForm);
    card.append(support, comments);
  }
  return card;
}

search.addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadReports, 250); });
[neighborhood, category, state].forEach((select) => select.addEventListener("change", loadReports));
loadFilters().then(loadReports).catch((error) => { status.textContent = error.message; });
