const detail = document.querySelector(".detail");
const status = document.querySelector("#detail-status");
fetch(`/api/segnalazioni/${detail.dataset.reportId}`, { credentials: "same-origin" })
  .then(async (response) => {
    const report = await response.json();
    if (!response.ok) throw new Error(report.error || "Scheda non disponibile.");
    document.querySelector("#detail-title").textContent = report.titolo;
    const badge = document.querySelector("#detail-badge");
    badge.hidden = false;
    badge.textContent = `${report.tipo} · ${report.visibilita === "bozza" ? "in revisione" : report.visibilita}`;
    document.querySelector("#detail-description").textContent = report.descrizione;
    document.querySelector("#detail-meta").textContent = [report.autore, report.quartiere,
      report.categorie, report.stato?.replaceAll("_", " "), report.data_creazione?.slice(0, 10)]
      .filter(Boolean).join(" · ");
    document.querySelector("#detail-address").textContent = report.indirizzo || "Indirizzo non indicato";
    if (report.allegato_id && report.visibilita !== "rimossa") {
      const media = report.allegato_tipo?.startsWith("video/")
        ? document.createElement("video") : document.createElement("img");
      media.src = `/api/allegati/${report.allegato_id}`;
      media.className = "report-image";
      if (media.tagName === "VIDEO") media.controls = true;
      else media.alt = `Allegato: ${report.titolo}`;
      document.querySelector("#detail-media").append(media);
    }
    const list = document.querySelector("#detail-comments");
    (report.commenti || []).forEach((comment) => {
      const item = document.createElement("li"); item.className = "comment-item";
      const author = document.createElement("strong"); author.textContent = comment.autore;
      const body = document.createElement("p"); body.textContent = comment.testo;
      item.append(author, body); list.append(item);
      if (detail.dataset.moderator === "true") {
        const remove = document.createElement("button");
        remove.className = "button button-secondary"; remove.type = "button";
        remove.textContent = "Rimuovi commento";
        remove.addEventListener("click", async () => {
          remove.disabled = true;
          try {
            const response = await fetch(`/api/moderazione/commenti/${comment.id}`, {
              method: "DELETE", credentials: "same-origin",
              headers: { "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content },
            });
            if (!response.ok) throw new Error((await response.json()).error || "Operazione non riuscita.");
            item.remove(); status.textContent = "Commento rimosso.";
          } catch (error) { status.textContent = error.message; remove.disabled = false; }
        });
        item.append(remove);
      }
    });
    if (!report.commenti?.length) list.textContent = "Nessun commento visibile.";
    const lat = Number(report.latitude), lng = Number(report.longitude);
    if (report.latitude !== null && report.longitude !== null && Number.isFinite(lat) && Number.isFinite(lng)) {
      setupMap(document.querySelector("#detail-map"), { interactive: false, lat, lng });
      document.querySelector("#detail-coordinates").textContent = `${lat.toFixed(6)}, ${lng.toFixed(6)}`;
    } else {
      document.querySelector("#detail-map").remove();
      document.querySelector("#detail-coordinates").textContent = "Posizione precisa non disponibile per questa segnalazione storica.";
    }
    status.textContent = "";
  })
  .catch((error) => { status.textContent = error.message; });
