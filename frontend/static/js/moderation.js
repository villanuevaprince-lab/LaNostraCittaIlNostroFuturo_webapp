const reportRoot = document.querySelector("#moderation-reports");
const userRoot = document.querySelector("#moderation-users");
const status = document.querySelector("#moderation-status");
const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
const filter = document.querySelector("#moderation-filter");
const selected = new Set();
let reportCursor = null;
let userCursor = null;
let loadingReports = false;
let queueGeneration = 0;
let pendingReset = false;

async function requestJSON(url, method = "GET", payload) {
  const response = await fetch(url, {
    method, credentials: "same-origin",
    headers: payload ? { "Content-Type": "application/json", "X-CSRFToken": csrf } : { "X-CSRFToken": csrf },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Operazione non riuscita.");
  return data;
}

function selectionChanged() {
  document.querySelector("#selected-count").textContent = `${selected.size} selezionati`;
  for (const id of ["bulk-approve", "bulk-reject"]) document.getElementById(id).disabled = !selected.size;
}

async function action(ids, name) {
  if (name === "rifiuta" && !window.confirm(`Rifiutare ${ids.length} contenuti? Non saranno più pubblicabili.`)) return;
  try {
    const result = await requestJSON("/api/moderazione/segnalazioni/azioni", "POST", { ids, azione: name });
    status.textContent = `${result.modificate} aggiornati, ${result.invariate} invariati, ${result.missing.length} non trovati.`;
    for (const id of ids) selected.delete(id);
    selectionChanged();
    await loadReports(true);
  } catch (error) { status.textContent = error.message; }
}

function button(label, className, handler) {
  const element = document.createElement("button");
  element.type = "button"; element.className = className; element.textContent = label;
  element.addEventListener("click", async () => {
    element.disabled = true;
    try { await handler(); } finally { element.disabled = false; }
  });
  return element;
}

async function blockUser(id, name) {
  if (!window.confirm(`Bloccare ${name} per 7 giorni?`)) return;
  const reason = window.prompt("Motivazione del blocco (obbligatoria):");
  if (!reason?.trim()) return;
  try {
    await requestJSON(`/api/moderazione/utenti/${id}/blocco`, "POST", {
      motivazione: reason.trim(), giorni: 7,
    });
    status.textContent = `Account ${name} bloccato per 7 giorni.`;
  } catch (error) { status.textContent = error.message; }
}

function renderReport(report) {
  const row = document.createElement("article"); row.className = "moderation-row";
  const check = document.createElement("input"); check.type = "checkbox";
  check.setAttribute("aria-label", `Seleziona ${report.titolo}`);
  check.addEventListener("change", () => {
    if (check.checked && selected.size >= 50) {
      check.checked = false;
      status.textContent = "Puoi selezionare al massimo 50 contenuti per volta.";
      return;
    }
    if (check.checked) selected.add(report.id); else selected.delete(report.id);
    selectionChanged();
  });
  const body = document.createElement("div");
  const heading = document.createElement("h3");
  const link = document.createElement("a"); link.href = `/reports/${report.id}`; link.textContent = report.titolo;
  heading.append(link);
  const meta = document.createElement("p"); meta.className = "report-meta";
  meta.textContent = `${report.tipo} · ${report.autore} · ${report.data_creazione.slice(0, 10)} · ${report.visibilita}`;
  body.append(heading, meta);
  const controls = document.createElement("div"); controls.className = "toolbar";
  controls.append(
    button("Approva", "button", () => action([report.id], "approva")),
    button("Rifiuta", "button button-danger", () => action([report.id], "rifiuta")),
    button("Nascondi", "button button-secondary", () => action([report.id], "nascondi")),
    button("Blocca autore", "button button-secondary", () => blockUser(report.autore_id, report.autore)),
  );
  row.append(check, body, controls);
  return row;
}

async function loadReports(reset = false) {
  if (reset) {
    queueGeneration += 1;
    reportCursor = null; reportRoot.replaceChildren(); selected.clear(); selectionChanged();
  }
  if (loadingReports) { if (reset) pendingReset = true; return; }
  loadingReports = true;
  const generation = queueGeneration;
  status.textContent = "Caricamento coda…";
  try {
    const params = new URLSearchParams({ visibilita: filter.value, limit: "25" });
    if (reportCursor) params.set("cursor", reportCursor);
    const page = await requestJSON(`/api/moderazione/coda?${params}`);
    if (generation !== queueGeneration) return;
    page.items.forEach((item) => reportRoot.append(renderReport(item)));
    reportCursor = page.next_cursor;
    document.querySelector("#moderation-next").hidden = !reportCursor;
    status.textContent = page.items.length ? "Coda aggiornata." : "Nessun contenuto in questa vista.";
  } catch (error) { status.textContent = error.message; }
  finally {
    loadingReports = false;
    if (pendingReset) { pendingReset = false; loadReports(); }
  }
}

function renderUser(user) {
  const row = document.createElement("div"); row.className = "moderation-row";
  const label = document.createElement("span");
  label.textContent = `${user.nome} ${user.cognome} · ${user.stato}`;
  const name = `${user.nome} ${user.cognome}`;
  if (user.stato === "attivo") row.append(label,
    button("Blocca 7 giorni", "button button-secondary", () => blockUser(user.id, name)));
  else row.append(label, button("Revoca blocco", "button button-secondary", async () => {
    const reason = window.prompt("Motivo della revoca:");
    if (!reason?.trim()) return;
    try {
      await requestJSON(`/api/moderazione/utenti/${user.id}/sblocco`, "POST", { motivazione: reason.trim() });
      label.textContent = `${name} · attivo`;
      status.textContent = "Blocco revocato.";
    } catch (error) { status.textContent = error.message; }
  }));
  return row;
}

async function loadUsers() {
  try {
    const params = userCursor ? `?cursor=${userCursor}` : "";
    const page = await requestJSON(`/api/moderazione/utenti${params}`);
    page.items.forEach((item) => userRoot.append(renderUser(item)));
    userCursor = page.next_cursor;
    document.querySelector("#users-next").hidden = !userCursor;
  } catch (error) { status.textContent = error.message; }
}

document.querySelector("#bulk-approve").addEventListener("click", () => action([...selected], "approva"));
document.querySelector("#bulk-reject").addEventListener("click", () => action([...selected], "rifiuta"));
document.querySelector("#moderation-next").addEventListener("click", () => loadReports());
document.querySelector("#users-next").addEventListener("click", loadUsers);
filter.addEventListener("change", () => loadReports(true));
loadReports(true);
loadUsers();
