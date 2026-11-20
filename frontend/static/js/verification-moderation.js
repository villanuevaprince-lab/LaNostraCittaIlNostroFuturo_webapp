// Dashboard moderatori della verifica AI. Testo sempre inserito con textContent.
const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
const list = document.querySelector("#verification-list");
const status = document.querySelector("#verification-status");
const filter = document.querySelector("#verification-filter");
const next = document.querySelector("#verification-next");
const STATE_LABELS = {
  in_valutazione: "In valutazione", in_attesa_modello: "In attesa del modello", pubblicata: "Pubblicata",
  respinta_automatica: "Respinta automaticamente", respinta_moderatore: "Respinta dai moderatori",
  da_revisionare: "Da revisionare", in_ricorso: "In ricorso",
};
const DECISION_LABELS = { pubblica: "pubblicare", respingi: "respingere", revisione: "revisione umana" };
const CATEGORY_LABELS = { coerenza: "Coerenza", scopo: "Scopo civico", linguaggio: "Linguaggio", plausibilita: "Plausibilità", altro: "Altro" };
let cursor = null, generation = 0;

async function requestJSON(url, options = {}) {
  const response = await fetch(url, { credentials: "same-origin", ...options });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Operazione non riuscita.");
  return data;
}
const el = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = text;
  if (className) node.className = className;
  return node;
};
const percent = (value) => (value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`);

async function loadCounts() {
  try {
    const counts = await requestJSON("/api/moderazione/verifiche/conteggi");
    const root = document.querySelector("#verification-counts");
    root.replaceChildren(...Object.entries(STATE_LABELS).map(([state, label]) => {
      const item = el("li", `${label}: ${counts[state] || 0}`, "badge");
      item.dataset.state = state;
      if (["da_revisionare", "in_ricorso"].includes(state) && counts[state]) item.classList.add("verification-priority");
      return item;
    }));
  } catch (_) { /* i conteggi sono accessori */ }
}

function renderDetail(detail, container, summary) {
  container.replaceChildren();
  container.append(el("p", detail.descrizione, "verification-text"));
  if (detail.indirizzo) container.append(el("p", `Luogo: ${detail.indirizzo}`, "hint"));
  const latest = detail.esiti[0];
  if (latest) {
    container.append(el("h4", `Valutazione del modello (versione ${latest.versione}, ${latest.modello})`));
    container.append(el("p", `Suggerimento: ${DECISION_LABELS[latest.esito_suggerito] || "—"} · Decisione applicata: ${DECISION_LABELS[latest.decisione]} · Confidenza: ${percent(latest.confidenza)}`));
    container.append(el("p", `Motivazione: ${latest.motivazione}`));
    if (latest.note_moderatore) container.append(el("p", `Note per il moderatore: ${latest.note_moderatore}`, "verification-notes"));
    if (latest.errore) container.append(el("p", `Errore del modello: ${latest.errore}`, "verification-error"));
    if (latest.violazioni.length) {
      const table = el("table", null, "verification-violations");
      const head = el("tr"); ["Criterio", "Gravità", "Spiegazione", "Fonte"].forEach((h) => head.append(el("th", h)));
      table.append(head);
      latest.violazioni.forEach((v) => {
        const row = el("tr");
        row.append(el("td", CATEGORY_LABELS[v.categoria] || v.categoria), el("td", `${v.gravita} su 3`),
          el("td", v.spiegazione), el("td", v.origine === "filtro_linguaggio" ? "Filtro automatico" : "Modello"));
        table.append(row);
      });
      container.append(table);
    } else container.append(el("p", "Nessuna violazione rilevata.", "hint"));
  } else container.append(el("p", "Il modello non ha ancora valutato questo contenuto.", "hint"));
  const job = detail.job[0];
  if (job) container.append(el("p", `Coda: ${job.stato.replaceAll("_", " ")} · tentativi ${job.tentativi}${job.ultimo_errore ? ` · ultimo errore: ${job.ultimo_errore}` : ""}`, "hint"));
  container.append(el("h4", "Storico delle decisioni"));
  const history = el("ol", null, "verification-history");
  detail.storico.forEach((d) => history.append(el("li",
    `${d.data.replace("T", " ")} · ${d.origine}${d.utente ? ` (${d.utente})` : ""} · ${d.azione}: ${STATE_LABELS[d.stato_precedente] || "—"} → ${STATE_LABELS[d.stato_successivo] || d.stato_successivo}${d.ribaltamento ? " · ribaltamento" : ""}${d.motivazione ? ` · ${d.motivazione}` : ""}`)));
  container.append(history);
  container.append(decisionForm(detail, latest, summary));
}

function decisionForm(detail, latest, summary) {
  const form = el("form", null, "verification-decision");
  const label = el("label", "Motivo della decisione (obbligatorio, visibile all'autore)", "field");
  const reason = el("textarea"); reason.name = "motivazione"; reason.rows = 3; reason.minLength = 3; reason.maxLength = 1000; reason.required = true;
  label.append(reason);
  const output = el("p", "", "status"); output.setAttribute("role", "status");
  const actions = el("div", null, "toolbar");
  const make = (action) => {
    const overturn = latest && ((latest.decisione === "pubblica" && action === "respingi") || (latest.decisione === "respingi" && action === "approva"));
    const text = action === "approva" ? (overturn ? "Ribalta e pubblica" : "Approva e pubblica") : (overturn ? "Ribalta e respingi" : "Respingi");
    const button = el("button", text, action === "approva" ? "button" : "button button-danger");
    button.type = "button";
    button.disabled = (action === "approva" && detail.stato_verifica === "pubblicata") || (action === "respingi" && detail.stato_verifica === "respinta_moderatore");
    button.addEventListener("click", async () => {
      if (!reason.reportValidity()) return;
      button.disabled = true;
      try {
        const result = await requestJSON(`/api/moderazione/verifiche/${detail.id}/decisione`, {
          method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
          body: JSON.stringify({ azione: action, motivazione: reason.value }),
        });
        status.textContent = `«${detail.titolo}»: ${STATE_LABELS[result.stato_verifica]}${result.ribaltamento ? " (decisione del modello ribaltata)" : ""}.`;
        summary.remove(); loadCounts();
      } catch (error) { output.textContent = error.message; button.disabled = false; }
    });
    return button;
  };
  actions.append(make("approva"), make("respingi"));
  form.append(label, actions, output);
  return form;
}

function renderItem(item) {
  const row = el("article", null, "moderation-row verification-row");
  const body = el("div");
  const heading = el("h3"); const link = el("a", item.titolo); link.href = `/reports/${item.id}`; heading.append(link);
  const badge = el("span", STATE_LABELS[item.stato_verifica] || item.stato_verifica, "badge verification-state");
  badge.dataset.state = item.stato_verifica;
  const meta = el("p", [item.tipo, item.autore, item.data_creazione.slice(0, 10), `versione ${item.versione}`,
    item.reinvii ? `reinvii ${item.reinvii}` : null].filter(Boolean).join(" · "), "report-meta");
  const model = el("p", item.decisione_modello
    ? `Modello: ${DECISION_LABELS[item.decisione_modello]} · confidenza ${percent(item.confidenza)} · gravità massima ${item.gravita_massima || 0}`
    : `Coda: ${(item.stato_job || "—").replaceAll("_", " ")}${item.tentativi ? ` · tentativi ${item.tentativi}` : ""}`, "hint");
  const toggle = el("button", "Dettagli e decisione", "button button-secondary"); toggle.type = "button";
  toggle.setAttribute("aria-expanded", "false");
  const detail = el("div", null, "verification-detail"); detail.hidden = true;
  toggle.addEventListener("click", async () => {
    const open = detail.hidden;
    detail.hidden = !open; toggle.setAttribute("aria-expanded", String(open));
    if (open && !detail.dataset.loaded) {
      detail.textContent = "Caricamento…";
      try { renderDetail(await requestJSON(`/api/moderazione/verifiche/${item.id}`), detail, row); detail.dataset.loaded = "1"; }
      catch (error) { detail.textContent = error.message; }
    }
  });
  body.append(heading, badge, meta, model, toggle, detail);
  row.append(body);
  return row;
}

async function load(reset = false) {
  if (reset) { generation += 1; cursor = null; list.replaceChildren(); }
  const current = generation;
  next.disabled = true; status.textContent = "Caricamento…";
  const params = new URLSearchParams({ vista: filter.value }); if (cursor) params.set("cursor", cursor);
  try {
    const page = await requestJSON(`/api/moderazione/verifiche?${params}`);
    if (current !== generation) return;
    page.items.forEach((item) => list.append(renderItem(item)));
    cursor = page.next_cursor; next.hidden = !cursor;
    status.textContent = list.children.length ? `${list.children.length} contenuti mostrati.` : "Nessun contenuto in questa vista.";
  } catch (error) { if (current === generation) status.textContent = error.message; }
  finally { next.disabled = false; }
}

filter.addEventListener("change", () => load(true));
next.addEventListener("click", () => load());
loadCounts(); load(true);
