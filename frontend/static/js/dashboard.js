const target = document.querySelector("#my-reports");
const status = document.querySelector("#dashboard-status");
const filter = document.querySelector("#dashboard-filter");
const next = document.querySelector("#dashboard-next");
const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
let reports = [];
let maxResubmits = 3;
// Verifica AI prima della pubblicazione: etichetta, passo (su 4) e spiegazione per l'autore.
const VERIFICATION = {
  in_valutazione: ["In fase di valutazione", 2, "La verifica automatica è in corso: riceverai una notifica con l'esito."],
  in_attesa_modello: ["In fase di valutazione", 2, "Il servizio di verifica è momentaneamente non disponibile: la valutazione riprenderà da sola e il contenuto non andrà perso."],
  da_revisionare: ["In revisione dal comitato", 3, "Un moderatore esaminerà il contenuto prima della pubblicazione."],
  in_ricorso: ["Ricorso in esame", 3, "Hai chiesto la revisione: un moderatore deciderà a breve."],
  respinta_automatica: ["Respinta automaticamente", 4, ""],
  respinta_moderatore: ["Respinta dal comitato", 4, ""],
  pubblicata: ["Pubblicata", 4, ""],
};
const STEP_NAMES = ["", "Inviata", "Verifica automatica", "Revisione umana", "Esito"];
let cursor = null;
let generation = 0;

function reportGroup(report) {
  if (report.visibilita === "rimossa") {
    return report.ritirata_autore ? "rimossa_autore" : "rimossa_moderazione";
  }
  return report.visibilita;
}

function renderDashboard() {
  target.replaceChildren(...reports.map(createCard));
  status.textContent = reports.length ? `${reports.length} contenuti mostrati.` : "Nessun contenuto in questa vista.";
}

async function loadPage(reset = false) {
  if (reset) {
    generation += 1; cursor = null; reports = []; target.replaceChildren(); next.hidden = true;
  }
  const current = generation;
  next.disabled = true;
  status.textContent = "Caricamento…";
  const params = new URLSearchParams({ vista: filter.value });
  if (cursor) params.set("cursor", cursor);
  try {
    const response = await fetch(`/api/me/segnalazioni?${params}`, { credentials: "same-origin" });
    const page = await response.json();
    if (current !== generation) return;
    if (!response.ok) throw new Error(page.error || "Caricamento non riuscito.");
    if (page.max_reinvii) maxResubmits = page.max_reinvii;
    reports.push(...page.items);
    cursor = page.next_cursor;
    next.hidden = !cursor;
    renderDashboard();
    return true;
  } catch (error) {
    if (current === generation) status.textContent = error.message;
    return false;
  } finally {
    if (current === generation) next.disabled = false;
  }
}

async function postJSON(url, body) {
  const response = await fetch(url, {
    method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrf }, body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Operazione non riuscita.");
  return data;
}

function verificationPanel(report) {
  const info = VERIFICATION[report.stato_verifica];
  if (!info || report.stato_verifica === "pubblicata" || report.visibilita === "rimossa") return null;
  const [label, step, text] = info;
  const box = document.createElement("div"); box.className = "verify-box";
  box.dataset.verification = report.stato_verifica;
  const title = document.createElement("p"); title.className = "verify-label";
  title.textContent = `Verifica: ${label}`;
  const progress = document.createElement("progress");
  progress.max = 4; progress.value = step;
  progress.setAttribute("aria-label", `Avanzamento della verifica: passo ${step} di 4, ${STEP_NAMES[step]}`);
  const steps = document.createElement("p"); steps.className = "verify-steps hint";
  steps.textContent = STEP_NAMES.slice(1).map((name, index) => (index + 1 === step ? `▸ ${name}` : name)).join(" · ");
  box.append(title, progress, steps);
  if (text) { const hint = document.createElement("p"); hint.className = "hint"; hint.textContent = text; box.append(hint); }
  if (report.motivazione_verifica && report.stato_verifica.startsWith("respinta")) {
    const reason = document.createElement("p"); reason.className = "verify-reason";
    reason.textContent = `Motivazione: ${report.motivazione_verifica}`; box.append(reason);
  }
  if (report.stato_verifica === "respinta_automatica") box.append(...rejectionActions(report));
  return box;
}

function rejectionActions(report) {
  const output = document.createElement("p"); output.className = "status"; output.setAttribute("role", "status");
  const actions = document.createElement("div"); actions.className = "toolbar";
  const left = Math.max(0, maxResubmits - (report.reinvii || 0));
  const form = document.createElement("form"); form.className = "verify-resubmit"; form.hidden = true;
  form.innerHTML = `<label class="field">Titolo<input name="titolo" minlength="3" maxlength="200" required></label>
    <label class="field">Descrizione<textarea name="descrizione" rows="4" minlength="10" maxlength="5000" required></textarea></label>
    <button class="button" type="submit">Reinvia alla verifica</button>`;
  form.elements.titolo.value = report.titolo; form.elements.descrizione.value = report.descrizione || "";
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    form.querySelector("button").disabled = true;
    try {
      const data = await postJSON(`/api/segnalazioni/${report.id}/reinvio`, {
        titolo: form.elements.titolo.value, descrizione: form.elements.descrizione.value });
      if (await loadPage(true)) status.textContent = data.message;
    } catch (error) { output.textContent = error.message; form.querySelector("button").disabled = false; }
  });
  const edit = document.createElement("button"); edit.type = "button"; edit.className = "button button-secondary";
  edit.textContent = left ? `Modifica e reinvia (${left} rimasti)` : "Reinvii esauriti";
  edit.disabled = !left;
  edit.addEventListener("click", () => { form.hidden = !form.hidden; if (!form.hidden) form.elements.titolo.focus(); });
  const appeal = document.createElement("button"); appeal.type = "button"; appeal.className = "button button-secondary";
  appeal.textContent = "Chiedi la revisione di un moderatore";
  appeal.addEventListener("click", async () => {
    const reason = window.prompt("Spiega perché il rifiuto automatico è sbagliato (almeno 10 caratteri):");
    if (!reason) return;
    appeal.disabled = true;
    try {
      const data = await postJSON(`/api/segnalazioni/${report.id}/ricorso`, { motivazione: reason });
      if (await loadPage(true)) status.textContent = data.message;
    } catch (error) { output.textContent = error.message; appeal.disabled = false; }
  });
  actions.append(edit, appeal);
  return [actions, form, output];
}

function createCard(report) {
  const card = document.createElement("article"); card.className = "report-card";
  const badge = document.createElement("span"); badge.className = "badge";
  badge.textContent = {
    pubblica: "Pubblicata", bozza: "In revisione", nascosta: "Nascosta",
    rimossa_moderazione: "Rimossa dai moderatori", rimossa_autore: "Ritirata da te",
  }[reportGroup(report)] || report.visibilita;
  const verification = VERIFICATION[report.stato_verifica];
  if (verification && report.visibilita === "bozza") badge.textContent = verification[0];
  const heading = document.createElement("h3");
  const link = document.createElement("a"); link.href = `/reports/${report.id}`;
  link.textContent = report.titolo; heading.append(link);
  const description = document.createElement("p"); description.textContent = report.descrizione;
  const meta = document.createElement("p"); meta.className = "report-meta";
  meta.textContent = [report.tipo, report.quartiere || report.indirizzo,
    report.stato?.replaceAll("_", " "), report.data_creazione?.slice(0, 10)]
    .filter(Boolean).join(" · ");
  const stateBadge = document.createElement("span");
  setStateBadge(stateBadge, report);
  card.append(badge, stateBadge, heading, description, meta);
  const verificationBox = verificationPanel(report);
  if (verificationBox) card.append(verificationBox);
  if (report.categorie?.length) {
    const tags = document.createElement("div"); tags.className = "tag-list";
    report.categorie.forEach((category) => {
      const tag = document.createElement("span"); tag.className = "category-tag";
      tag.textContent = category.nome; tags.append(tag);
    });
    card.append(tags);
  }
  if (report.duplicate_of_id) {
    const note = document.createElement("p"); note.textContent = `Unita al contenuto #${report.duplicate_of_id}`; card.append(note);
  }
  if (report.visibilita !== "rimossa") {
    const action = document.createElement("button"); action.type = "button";
    action.className = "button button-secondary"; action.textContent = "Ritira contenuto";
    action.addEventListener("click", async () => {
      if (!window.confirm("Ritirare definitivamente questo contenuto? Non sarà più visibile nella bacheca.")) return;
      action.disabled = true;
      try {
        const response = await fetch(`/api/segnalazioni/${report.id}`, {
          method: "DELETE", credentials: "same-origin", headers: { "X-CSRFToken": csrf },
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Ritiro non riuscito.");
        if (await loadPage(true)) status.textContent = "Contenuto ritirato.";
      } catch (error) { status.textContent = error.message; action.disabled = false; }
    });
    card.append(action);
  }
  return card;
}

filter.addEventListener("change", () => loadPage(true));
next.addEventListener("click", () => loadPage());
loadPage(true);
