const target = document.querySelector("#my-reports");
const status = document.querySelector("#dashboard-status");
fetch("/api/segnalazioni?mie=1", { credentials: "same-origin" })
  .then(async (response) => {
    const rows = await response.json();
    if (!response.ok) throw new Error(rows.error || "Caricamento non riuscito.");
    status.textContent = rows.length ? `${rows.length} contenuti pubblicati` : "Non hai ancora pubblicato contenuti.";
    rows.forEach((row) => {
      const card = document.createElement("article");
      card.className = "report-card";
      const title = document.createElement("h2"); title.textContent = row.titolo;
      const description = document.createElement("p"); description.textContent = row.descrizione;
      const meta = document.createElement("p"); meta.textContent = `${row.tipo} · ${row.stato}`;
      card.append(title, description, meta); target.append(card);
    });
  })
  .catch((error) => { status.textContent = error.message; });
