const reportRoot = document.querySelector("#moderation-reports");
const userRoot = document.querySelector("#moderation-users");
const status = document.querySelector("#moderation-status");
const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
const states = ["nuova", "aperta", "in_valutazione", "in_lavorazione", "presa_in_carico", "risolta", "chiusa"];

async function send(url, method, payload) {
  const response = await fetch(url, { method, credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrf }, body: JSON.stringify(payload) });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Operazione non riuscita.");
}

async function load() {
  const [reportsResponse, usersResponse] = await Promise.all([
    fetch("/api/segnalazioni"), fetch("/api/moderazione/utenti", { credentials: "same-origin" }),
  ]);
  const reports = await reportsResponse.json();
  const users = await usersResponse.json();
  if (!reportsResponse.ok || !usersResponse.ok) throw new Error("Non è stato possibile caricare i dati.");
  reports.forEach((report) => {
    const card = document.createElement("article"); card.className = "report-card";
    const title = document.createElement("h3"); title.textContent = report.titolo;
    const select = document.createElement("select"); states.forEach((s) => select.add(new Option(s.replaceAll("_", " "), s)));
    select.value = report.stato;
    const update = document.createElement("button"); update.className = "button"; update.textContent = "Aggiorna stato";
    update.addEventListener("click", async () => {
      try { await send(`/api/segnalazioni/${report.id}/stato`, "PATCH", { stato: select.value }); status.textContent = "Stato aggiornato."; }
      catch (error) { status.textContent = error.message; }
    });
    const hide = document.createElement("button"); hide.className = "button button-secondary"; hide.textContent = "Nascondi";
    hide.addEventListener("click", async () => {
      try { await send(`/api/moderazione/segnalazioni/${report.id}`, "PATCH", { visibilita: "nascosta" }); card.remove(); }
      catch (error) { status.textContent = error.message; }
    });
    const comments = document.createElement("details");
    const summary = document.createElement("summary"); summary.textContent = "Modera commenti";
    comments.append(summary);
    fetch(`/api/segnalazioni/${report.id}`).then((response) => response.json()).then((data) => {
      (data.commenti || []).forEach((comment) => {
        const line = document.createElement("p");
        line.textContent = `${comment.autore || "Cittadino"}: ${comment.testo} `;
        const remove = document.createElement("button"); remove.className = "button button-danger";
        remove.textContent = "Rimuovi commento";
        remove.addEventListener("click", async () => {
          try { await send(`/api/moderazione/commenti/${comment.id}`, "DELETE"); line.remove(); }
          catch (error) { status.textContent = error.message; }
        });
        line.append(remove); comments.append(line);
      });
    });
    card.append(title, select, update, hide, comments); reportRoot.append(card);
  });
  users.forEach((user) => {
    const row = document.createElement("p"); row.textContent = `${user.nome} ${user.cognome} `;
    const block = document.createElement("button"); block.className = "button button-danger"; block.textContent = "Blocca per 7 giorni";
    block.addEventListener("click", async () => {
      try { await send(`/api/moderazione/utenti/${user.id}/blocco`, "POST", { giorni: 7, motivazione: "Blocco deciso dal moderatore." }); row.remove(); }
      catch (error) { status.textContent = error.message; }
    });
    row.append(block); userRoot.append(row);
  });
  status.textContent = "Dati caricati.";
}

load().catch((error) => { status.textContent = error.message; });
