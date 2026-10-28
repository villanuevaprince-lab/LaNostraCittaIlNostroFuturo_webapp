const reportRoot = document.querySelector("#moderation-reports");
const userRoot = document.querySelector("#moderation-users");
const status = document.querySelector("#moderation-status");
const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
const filter = document.querySelector("#moderation-filter");
const userSearch = document.querySelector("#user-search");
const usersStatus = document.querySelector("#users-status");
const selected = new Set();
let reportCursor = null;
const loadedReportIds = new Set();
let userCursor = null;
const loadedUserIds = new Set();
let loadingReports = false;
let queueGeneration = 0;
let pendingReset = false;
let userGeneration = 0;
let loadingUsers = false;
let pendingUserReset = false;
let userSearchTimer;

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
  const visible = [...reportRoot.querySelectorAll('input[type="checkbox"]:not(:disabled)')];
  document.querySelector("#select-all-reports").textContent =
    visible.length && visible.every((item) => item.checked) ? "Deseleziona le visibili" : "Seleziona tutte le visibili";
  document.querySelector("#select-all-reports").disabled = !visible.length;
  document.querySelector("#bulk-approve").textContent = filter.value === "rimossa" ? "Reinserisci selezionati" : "Approva selezionati";
}

async function action(ids, name) {
  if (name === "rifiuta" && !window.confirm(`Rimuovere ${ids.length} contenuti dalla bacheca?`)) return;
  try {
    const result = await requestJSON("/api/moderazione/segnalazioni/azioni", "POST", { ids, azione: name });
    for (const id of ids) selected.delete(id);
    selectionChanged();
    await loadReports(true);
    status.textContent = `${result.modificate} aggiornati, ${result.invariate} invariati, ${result.missing.length} non trovati.`;
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
    await loadUsers(true);
  } catch (error) { status.textContent = error.message; }
}

async function permanentBan(id, name) {
  if (!window.confirm(`Applicare un ban senza scadenza a ${name}? Le segnalazioni e i log resteranno conservati.`)) return;
  const reason = window.prompt("Motivazione del ban permanente (obbligatoria):");
  if (!reason?.trim()) return;
  try {
    await requestJSON(`/api/moderazione/utenti/${id}/ban-permanente`, "POST", { motivazione: reason.trim() });
    status.textContent = `Ban permanente applicato a ${name}.`;
    await loadUsers(true);
  } catch (error) { status.textContent = error.message; }
}

function renderReport(report, states) {
  const row = document.createElement("article"); row.className = "moderation-row";
  row.dataset.reportId = report.id;
  const check = document.createElement("input"); check.type = "checkbox";
  check.disabled = report.visibilita === "rimossa" && Boolean(report.ritirata_autore);
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
  const visibilityLabel = report.visibilita === "rimossa"
    ? report.ritirata_autore ? "ritirata dall'autore" : "rimossa dai moderatori"
    : report.visibilita;
  meta.textContent = `${report.tipo} · ${report.autore} · ${report.data_creazione.slice(0, 10)} · ${visibilityLabel}`;
  const badge = document.createElement("span"); setStateBadge(badge, report);
  body.append(heading, badge, meta);
  const controls = document.createElement("div"); controls.className = "toolbar";
  if (report.visibilita !== "pubblica" && !check.disabled) controls.append(button(
    report.visibilita === "rimossa" ? "Reinserisci" : "Approva", "button",
    () => action([report.id], "approva")));
  if (report.visibilita !== "rimossa") controls.append(button(
    "Rimuovi", "button button-danger", () => action([report.id], "rifiuta")));
  if (report.visibilita === "pubblica") controls.append(button(
    "Nascondi", "button button-secondary", () => action([report.id], "nascondi")));
  controls.append(button("Blocca autore", "button button-secondary", () => blockUser(report.autore_id, report.autore)));
  if (report.duplicate_of_id) {
    const note = document.createElement("a"); note.href = `/reports/${report.duplicate_of_id}`; note.textContent = `Unita al contenuto #${report.duplicate_of_id}`; controls.append(note);
  }
  const stateDefinition = states.find((item) => item.codice === report.stato);
  const stateLabel = document.createElement("label"); stateLabel.className = "state-control";
  stateLabel.textContent = "Stato";
  const stateSelect = document.createElement("select");
  const allowed = [report.stato, ...(stateDefinition?.prossimi || []).filter((code) => states.find((s) => s.codice === code)?.tipi.includes(report.tipo))];
  allowed.forEach((code) => {
    const state = states.find((item) => item.codice === code);
    stateSelect.add(new Option(state?.etichetta || code.replaceAll("_", " "), code));
  });
  stateSelect.value = report.stato;
  stateSelect.disabled = Boolean(report.duplicate_of_id) || allowed.length < 2;
  stateLabel.append(stateSelect);
  controls.append(stateLabel, button("Cambia stato", "button button-secondary", async () => {
    if (report.duplicate_of_id || stateSelect.value === report.stato) return;
    try {
      await requestJSON(`/api/segnalazioni/${report.id}/stato`, "PATCH", { stato: stateSelect.value });
      await loadReports(true);
      status.textContent = `Stato aggiornato per «${report.titolo}».`;
    } catch (error) { status.textContent = error.message; }
  }));
  if (report.visibilita === "pubblica" && !report.duplicate_of_id) controls.append(button("Unisci duplicato", "button button-secondary", async () => {
    const target = window.prompt("ID del contenuto principale dello stesso tipo (i sostegni saranno deduplicati e i commenti trasferiti):");
    if (!target) return;
    const reason = window.prompt("Motivazione dell'unione:");
    if (!reason) return;
    try {
      await requestJSON(`/api/moderazione/segnalazioni/${report.id}/duplicato`, "POST", { duplicate_of_id: Number(target), motivazione: reason });
      await loadReports(true); status.textContent = "Duplicato unito al contenuto principale.";
    } catch (error) { status.textContent = error.message; }
  }));
  row.append(check, body, controls);
  return row;
}

async function loadReports(reset = false) {
  if (reset) {
    queueGeneration += 1;
    reportCursor = null; loadedReportIds.clear(); reportRoot.replaceChildren();
    selected.clear(); selectionChanged();
  }
  if (loadingReports) { if (reset) pendingReset = true; return; }
  loadingReports = true;
  const generation = queueGeneration;
  const requestedCursor = reportCursor;
  status.textContent = "Caricamento coda…";
  try {
    const params = new URLSearchParams({ vista: filter.value, limit: requestedCursor ? "10" : "5" });
    if (reportCursor) params.set("cursor", reportCursor);
    const [page, states] = await Promise.all([
      requestJSON(`/api/moderazione/coda?${params}`), requestJSON("/api/stati"),
    ]);
    if (generation !== queueGeneration) return;
    const freshItems = page.items.filter((item) => !loadedReportIds.has(item.id));
    freshItems.forEach((item) => {
      loadedReportIds.add(item.id);
      reportRoot.append(renderReport(item, states));
    });
    // Evita richieste infinite se un proxy/API restituisce la stessa pagina o
    // un cursore non avanzato.
    reportCursor = page.next_cursor && page.next_cursor !== requestedCursor && freshItems.length
      ? page.next_cursor : null;
    document.querySelector("#moderation-next").hidden = !reportCursor;
    status.textContent = reportRoot.children.length ? "Coda aggiornata." : "Nessun contenuto in questa vista.";
    selectionChanged();
  } catch (error) { status.textContent = error.message; }
  finally {
    loadingReports = false;
    if (pendingReset) { pendingReset = false; loadReports(); }
  }
}

const blockLabels = {
  attivo: "Attivo", temporaneo: "Blocco temporaneo", permanente: "Ban permanente",
  scaduto: "Blocco scaduto, da revocare", bloccato_senza_dettagli: "Bloccato (storico)",
};

function renderUser(user) {
  const row = document.createElement("tr");
  const nameCell = document.createElement("td"); nameCell.textContent = `${user.nome} ${user.cognome} (#${user.id})`;
  const emailCell = document.createElement("td"); emailCell.textContent = user.email;
  const statusCell = document.createElement("td");
  const badge = document.createElement("span"); badge.className = "badge";
  badge.textContent = blockLabels[user.tipo_blocco] || "Bloccato";
  statusCell.append(badge);
  const endCell = document.createElement("td");
  endCell.textContent = user.blocco_fine ? user.blocco_fine.replace("T", " ") : "—";
  const actions = document.createElement("td");
  const controls = document.createElement("div"); controls.className = "toolbar";
  const name = `${user.nome} ${user.cognome}`;
  if (user.stato === "attivo") controls.append(
    button("Blocca 7 giorni", "button button-secondary", () => blockUser(user.id, name)));
  if (user.tipo_blocco !== "permanente") controls.append(
    button("Ban permanente", "button button-danger", () => permanentBan(user.id, name)));
  if (user.stato === "bloccato") controls.append(button("Revoca blocco", "button button-secondary", async () => {
    const reason = window.prompt("Motivo della revoca:");
    if (!reason?.trim()) return;
    try {
      await requestJSON(`/api/moderazione/utenti/${user.id}/sblocco`, "POST", { motivazione: reason.trim() });
      await loadUsers(true);
      status.textContent = "Blocco revocato.";
    } catch (error) { status.textContent = error.message; }
  }));
  actions.append(controls);
  row.append(nameCell, emailCell, statusCell, endCell, actions);
  return row;
}

async function loadUsers(reset = false) {
  if (reset) {
    userGeneration += 1; userCursor = null; loadedUserIds.clear(); userRoot.replaceChildren();
    document.querySelector("#users-next").hidden = true;
  }
  if (loadingUsers) { if (reset) pendingUserReset = true; return; }
  if (!reset && loadedUserIds.size && userCursor === null) return;
  loadingUsers = true;
  const generation = userGeneration;
  const requestedCursor = userCursor;
  document.querySelector("#users-next").disabled = true;
  usersStatus.textContent = "Caricamento utenti…";
  try {
    const params = new URLSearchParams();
    if (userCursor) params.set("cursor", userCursor);
    if (userSearch.value.trim()) params.set("q", userSearch.value.trim());
    const page = await requestJSON(`/api/moderazione/utenti?${params}`);
    if (generation !== userGeneration) return;
    const fresh = page.items.filter((item) => !loadedUserIds.has(Number(item.id)));
    fresh.forEach((item) => { loadedUserIds.add(Number(item.id)); userRoot.append(renderUser(item)); });
    const candidate = Number(page.next_cursor);
    userCursor = fresh.length && Number.isSafeInteger(candidate) && candidate > 0 &&
      (requestedCursor === null || candidate < requestedCursor) ? candidate : null;
    document.querySelector("#users-next").hidden = !userCursor;
    usersStatus.textContent = userRoot.children.length ? `${userRoot.children.length} utenti mostrati.` : "Nessun utente trovato.";
  } catch (error) { usersStatus.textContent = error.message; }
  finally {
    loadingUsers = false;
    document.querySelector("#users-next").disabled = false;
    if (pendingUserReset) { pendingUserReset = false; loadUsers(); }
  }
}

document.querySelector("#bulk-approve").addEventListener("click", () => action([...selected], "approva"));
document.querySelector("#bulk-reject").addEventListener("click", () => action([...selected], "rifiuta"));
document.querySelector("#moderation-next").addEventListener("click", () => loadReports());
document.querySelector("#select-all-reports").addEventListener("click", () => {
  const boxes = [...reportRoot.querySelectorAll('input[type="checkbox"]:not(:disabled)')];
  const shouldSelect = boxes.some((box) => !box.checked);
  for (const box of boxes) {
    const id = Number(box.closest("article").dataset.reportId);
    if (shouldSelect && !box.checked && selected.size >= 50) break;
    box.checked = shouldSelect;
    if (shouldSelect) selected.add(id); else selected.delete(id);
  }
  selectionChanged();
  if (shouldSelect && boxes.some((box) => !box.checked)) status.textContent = "Massimo 50 selezioni per operazione.";
});
document.querySelector("#users-next").addEventListener("click", () => loadUsers());
userSearch.addEventListener("input", () => {
  clearTimeout(userSearchTimer); userSearchTimer = setTimeout(() => loadUsers(true), 300);
});
filter.addEventListener("change", () => loadReports(true));
loadReports(true);
loadUsers();
