const list = document.querySelector("#report-list");
const status = document.querySelector("#list-status");
const search = document.querySelector("#search-input");
const neighborhood = document.querySelector("#filter-neighborhood");
const category = document.querySelector("#filter-category");
const state = document.querySelector("#filter-state");
const sort = document.querySelector("#sort-reports");
const isAuthenticated = document.querySelector("[data-authenticated]")?.dataset.authenticated === "true";
const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
let searchTimer;
let requestController;

async function readJSON(response) {
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Richiesta non riuscita.");
  return data;
}

async function loadFilters() {
  const [quartieri, categories] = await Promise.all([
    fetch("/api/quartieri").then(readJSON), fetch("/api/categorie").then(readJSON),
  ]);
  quartieri.forEach((row) => neighborhood.add(new Option(row.nome, row.id)));
  categories.forEach((row) => category.add(new Option(row.nome, row.id)));
}

async function loadReports() {
  requestController?.abort();
  requestController = new AbortController();
  status.textContent = "Caricamento…";
  const params = new URLSearchParams();
  if (search.value.trim()) params.set("q", search.value.trim());
  if (neighborhood.value) params.set("quartiere", neighborhood.value);
  if (category.value) params.set("categoria", category.value);
  if (state.value) params.set("stato", state.value);
  params.set("ordina", sort.value);
  try {
    const rows = await fetch(`/api/segnalazioni?${params}`, {
      signal: requestController.signal, credentials: "same-origin",
    }).then(readJSON);
    list.replaceChildren(...rows.map(createCard));
    status.textContent = rows.length ? `${rows.length} contenuti trovati` : "Nessun contenuto trovato.";
  } catch (error) {
    if (error.name !== "AbortError") status.textContent = error.message;
  }
}

function createComment(comment) {
  const item = document.createElement("li");
  item.className = "comment-item";
  const author = document.createElement("strong");
  author.textContent = comment.autore || "Cittadino";
  const body = document.createElement("p");
  body.textContent = comment.testo;
  item.append(author, body);
  return item;
}

function createCard(report) {
  const card = document.createElement("article");
  card.className = "report-card";
  const badge = document.createElement("span");
  badge.className = "badge";
  badge.textContent = `${report.tipo} · ${String(report.stato).replaceAll("_", " ")}`;
  const title = document.createElement("h3");
  title.textContent = report.titolo;
  const description = document.createElement("p");
  description.textContent = report.descrizione;
  const meta = document.createElement("p");
  meta.className = "report-meta";
  [report.quartiere || report.indirizzo || "Milano", report.autore].forEach((value) => {
    const item = document.createElement("span");
    item.textContent = value;
    meta.append(item);
  });
  card.append(badge, title, description, meta);

  if (report.allegato_id) {
    const url = `/api/allegati/${report.allegato_id}`;
    const description = report.allegato_descrizione || `Allegato della segnalazione: ${report.titolo}`;
    if (report.allegato_tipo?.startsWith("video/")) {
      const video = document.createElement("video"); video.src = url; video.controls = true;
      video.preload = "metadata"; video.setAttribute("aria-label", description);
      video.className = "report-image"; card.append(video);
    } else if (report.allegato_tipo?.startsWith("image/")) {
      const image = document.createElement("img"); image.src = url;
      image.alt = description; image.loading = "lazy";
      image.className = "report-image"; card.append(image);
    }
  }

  const actions = document.createElement("div");
  actions.className = "report-actions";
  const count = document.createElement("span");
  count.className = "support-count";
  const setCount = (value) => { count.textContent = `${value} ${value === 1 ? "sostegno" : "sostegni"}`; };
  setCount(Number(report.sostegni) || 0);
  actions.append(count);
  const actionStatus = document.createElement("p");
  actionStatus.className = "status action-status";
  actionStatus.setAttribute("role", "status");

  if (isAuthenticated) {
    const support = document.createElement("button");
    support.type = "button";
    support.className = "button button-secondary";
    const setSupported = (value) => {
      report.sostenuta = Boolean(value);
      support.textContent = value ? "Ritira sostegno" : "Sostieni";
      support.setAttribute("aria-pressed", String(Boolean(value)));
    };
    setSupported(report.sostenuta);
    support.addEventListener("click", async () => {
      support.disabled = true;
      actionStatus.textContent = "";
      try {
        const result = await fetch(`/api/segnalazioni/${report.id}/sostegno`, {
          method: report.sostenuta ? "DELETE" : "PUT", credentials: "same-origin",
          headers: { "X-CSRFToken": csrf },
        }).then(readJSON);
        setSupported(result.sostenuta);
        setCount(result.sostegni);
      } catch (error) {
        actionStatus.textContent = error.message;
      } finally {
        support.disabled = false;
      }
    });
    actions.append(support);
  } else {
    const login = document.createElement("a");
    login.href = `/login?next=${encodeURIComponent("/")}`;
    login.textContent = "Accedi per sostenere";
    actions.append(login);
  }
  actions.append(actionStatus);
  card.append(actions);

  const comments = document.createElement("details");
  const summary = document.createElement("summary");
  let commentCount = Number(report.commenti_count) || 0;
  const updateSummary = () => {
    summary.textContent = `Commenti (${commentCount})`;
  };
  updateSummary();
  const commentsList = document.createElement("ul");
  commentsList.className = "comment-list";
  const commentsStatus = document.createElement("p");
  commentsStatus.className = "status";
  commentsStatus.setAttribute("role", "status");
  let loaded = false;
  let commentsRequest = 0;
  async function loadComments() {
    const currentRequest = ++commentsRequest;
    commentsStatus.textContent = "Caricamento commenti…";
    try {
      const data = await fetch(`/api/segnalazioni/${report.id}`).then(readJSON);
      if (currentRequest !== commentsRequest) return;
      commentsList.replaceChildren(...data.commenti.map(createComment));
      commentCount = data.commenti.length;
      updateSummary();
      loaded = true;
      commentsStatus.textContent = commentCount ? "" : "Nessun commento. Inizia la discussione!";
    } catch (error) {
      if (currentRequest === commentsRequest) commentsStatus.textContent = error.message;
    }
  }
  comments.addEventListener("toggle", () => {
    if (comments.open && !loaded) loadComments();
  });
  comments.append(summary, commentsList, commentsStatus);

  if (isAuthenticated) {
    const form = document.createElement("form");
    const label = document.createElement("label");
    label.textContent = "Scrivi un commento";
    const textarea = document.createElement("textarea");
    textarea.name = "testo";
    textarea.maxLength = 3000;
    textarea.required = true;
    textarea.rows = 3;
    label.append(textarea);
    const submit = document.createElement("button");
    submit.className = "button";
    submit.textContent = "Pubblica commento";
    form.append(label, submit);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const testo = textarea.value.trim();
      if (!testo) return;
      submit.disabled = true;
      commentsStatus.textContent = "";
      try {
        const comment = await fetch(`/api/segnalazioni/${report.id}/commenti`, {
          method: "POST", credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
          body: JSON.stringify({ testo }),
        }).then(readJSON);
        textarea.value = "";
        if (loaded) {
          commentsList.append(createComment(comment));
          commentCount += 1;
          updateSummary();
          commentsStatus.textContent = "Commento pubblicato.";
        } else {
          // Annulla logicamente l'eventuale GET iniziale in corso.
          commentsRequest += 1;
          commentCount += 1;
          updateSummary();
          await loadComments();
          if (loaded) commentsStatus.textContent = "Commento pubblicato.";
        }
      } catch (error) {
        commentsStatus.textContent = error.message;
      } finally {
        submit.disabled = false;
      }
    });
    comments.append(form);
  } else {
    const loginToComment = document.createElement("a");
    loginToComment.href = "/login?next=%2F";
    loginToComment.textContent = "Accedi per commentare";
    comments.append(loginToComment);
  }
  card.append(comments);
  return card;
}

search.addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadReports, 250); });
[neighborhood, category, state, sort].forEach((select) => select.addEventListener("change", loadReports));
loadFilters().then(loadReports).catch((error) => { status.textContent = error.message; });
