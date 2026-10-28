const list = document.querySelector("#report-list");
const status = document.querySelector("#list-status");
const search = document.querySelector("#search-input");
const neighborhood = document.querySelector("#filter-neighborhood");
const categoriesRoot = document.querySelector("#filter-categories");
const categorySummary = document.querySelector("#category-filter-summary");
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
  categories.forEach((row) => {
    const label = document.createElement("label"); label.className = "tag-option";
    const input = document.createElement("input"); input.type = "checkbox"; input.value = row.id;
    const text = document.createElement("span"); text.textContent = row.nome;
    label.append(input, text); categoriesRoot.append(label);
  });
  categorySummary.textContent = categories.length ? "Tutte le categorie" : "Nessuna categoria disponibile";
}

function updateCategorySummary() {
  const selected = [...categoriesRoot.querySelectorAll("input:checked")];
  categorySummary.textContent = selected.length ? `Categorie selezionate: ${selected.length}` : "Tutte le categorie";
}

async function loadReports() {
  requestController?.abort();
  requestController = new AbortController();
  status.textContent = "Caricamento…";
  const params = new URLSearchParams();
  if (search.value.trim()) params.set("q", search.value.trim());
  if (neighborhood.value) params.set("quartiere", neighborhood.value);
  categoriesRoot.querySelectorAll("input:checked").forEach((input) => params.append("categoria", input.value));
  if (state.value) params.set("stato", state.value);
  if (document.querySelector("#filter-type").value) params.set("tipo", document.querySelector("#filter-type").value);
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

function createCard(report) {
  const card = document.createElement("article");
  card.className = "report-card";
  const badge = document.createElement("span");
  badge.className = "badge";
  setStateBadge(badge, report);
  const title = document.createElement("h3");
  const detailLink = document.createElement("a");
  detailLink.href = `/reports/${report.id}`;
  detailLink.textContent = report.titolo;
  title.append(detailLink);
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
  if (report.tipo === "proposta") {
    const progress = document.createElement("p");
    progress.textContent = `${report.sostegni} / ${report.soglia_sostegni} sostegni · ${report.sostegni >= report.soglia_sostegni ? "Soglia raggiunta" : "Obiettivo della proposta"}`;
    card.append(progress);
  }
  if (report.categorie?.length) {
    const tags = document.createElement("div"); tags.className = "tag-list";
    report.categorie.forEach((category) => {
      const tag = document.createElement("span"); tag.className = "category-tag";
      tag.textContent = category.nome; tags.append(tag);
    });
    card.append(tags);
  }

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
  const summary = document.createElement("summary"); summary.textContent = `Commenti (${Number(report.commenti_count) || 0})`;
  const discussionRoot = document.createElement("div");
  let mounted = false;
  comments.addEventListener("toggle", () => {
    if (comments.open && !mounted) {
      mounted = true;
      mountDiscussion(discussionRoot, report.id, null, (count) => { summary.textContent = `Commenti (${count})`; });
    }
  });
  comments.append(summary, discussionRoot);
  card.append(comments);
  return card;
}

search.addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadReports, 250); });
[neighborhood, state, sort, document.querySelector("#filter-type")].forEach((element) => element.addEventListener("change", loadReports));
categoriesRoot.addEventListener("change", () => { updateCategorySummary(); loadReports(); });
loadFilters().then(loadReports).catch((error) => { status.textContent = error.message; });
