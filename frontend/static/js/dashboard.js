const target = document.querySelector("#my-reports");
const status = document.querySelector("#dashboard-status");
const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
fetch("/api/segnalazioni?mie=1", { credentials: "same-origin" })
  .then(async (response) => {
    const rows = await response.json();
    if (!response.ok) throw new Error(rows.error || "Caricamento non riuscito.");
    status.textContent = rows.length ? `${rows.length} contenuti nel tuo archivio` : "Non hai ancora inviato contenuti.";
    rows.forEach((row) => {
      const card = document.createElement("article");
      card.className = "report-card";
      const title = document.createElement("h2");
      const link = document.createElement("a"); link.href = `/reports/${row.id}`;
      link.textContent = row.titolo; title.append(link);
      const description = document.createElement("p"); description.textContent = row.descrizione;
      const badge = document.createElement("span"); badge.className = "badge";
      badge.textContent = { bozza: "In revisione", pubblica: "Pubblicata",
        nascosta: "Nascosta", rimossa: "Ritirata" }[row.visibilita] || row.visibilita;
      const meta = document.createElement("p"); meta.className = "report-meta";
      meta.textContent = `${row.tipo} · ${row.stato?.replaceAll("_", " ")}`;
      card.append(badge, title, description, meta);
      if (row.visibilita !== "rimossa") {
        const action = document.createElement("button"); action.type = "button";
        action.className = "button button-secondary"; action.textContent = "Ritira contenuto";
        action.addEventListener("click", async () => {
          if (!window.confirm("Ritirare definitivamente questo contenuto? Non sarà più visibile nella bacheca.")) return;
          action.disabled = true;
          try {
            const response = await fetch(`/api/segnalazioni/${row.id}`, {
              method: "DELETE", credentials: "same-origin", headers: { "X-CSRFToken": csrf },
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || "Ritiro non riuscito.");
            badge.textContent = "Ritirata"; row.visibilita = "rimossa";
            action.remove(); status.textContent = "Contenuto ritirato.";
          } catch (error) { status.textContent = error.message; action.disabled = false; }
        });
        card.append(action);
      }
      target.append(card);
    });
  })
  .catch((error) => { status.textContent = error.message; });
