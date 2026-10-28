const detail = document.querySelector(".detail");
const status = document.querySelector("#detail-status");
fetch(`/api/segnalazioni/${detail.dataset.reportId}`, { credentials: "same-origin" })
  .then(async (response) => {
    const report = await response.json();
    if (!response.ok) throw new Error(report.error || "Scheda non disponibile.");
    document.querySelector("#detail-title").textContent = report.titolo;
    const badge = document.querySelector("#detail-badge");
    badge.hidden = false;
    setStateBadge(badge, report);
    document.querySelector("#detail-description").textContent = report.descrizione;
    document.querySelector("#detail-meta").textContent = [report.autore, report.quartiere,
      report.stato?.replaceAll("_", " "), report.data_creazione?.slice(0, 10)]
      .filter(Boolean).join(" · ");
    const tags = document.querySelector("#detail-categories");
    (report.categorie || []).forEach((category) => {
      const tag = document.createElement("span"); tag.className = "category-tag";
      tag.textContent = category.nome; tags.append(tag);
    });
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
    const resolutionForm = document.querySelector("#resolution-form");
    if (resolutionForm && report.tipo === "segnalazione" && report.visibilita === "pubblica") resolutionForm.hidden = false;
    if (report.tipo === "proposta") {
      const progress = document.querySelector("#proposal-progress"); progress.hidden = false;
      progress.textContent = `${report.sostegni} / ${report.soglia_sostegni} sostegni. ${report.sostegni >= report.soglia_sostegni ? "Soglia raggiunta: proposta pronta per la valutazione." : "Sostieni questa idea di quartiere."}`;
    }
    if (report.tipo === "segnalazione" && report.stato === "risolta" && report.visibilita !== "rimossa") {
      document.querySelector("#resolution-comparison").hidden = false;
      document.querySelector("#resolution-description").textContent = report.risoluzione || "Intervento concluso.";
      for (const role of ["prima", "dopo"]) {
        const figure = document.createElement("figure");
        const caption = document.createElement("figcaption"); caption.textContent = role === "prima" ? "Prima" : "Dopo";
        figure.append(caption);
        const photos = (report.allegati || []).filter((a) => a.ruolo === role && a.mime.startsWith("image/"));
        if (!photos.length) { const note = document.createElement("p"); note.textContent = "Foto non disponibile."; figure.append(note); }
        photos.forEach((photo) => {
          const img = document.createElement("img"); img.src = `/api/allegati/${photo.id}`;
          img.alt = `${caption.textContent} l'intervento: ${report.titolo}`; img.loading = "lazy"; figure.append(img);
        });
        document.querySelector("#comparison-images").append(figure);
      }
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


document.querySelector("#resolution-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget, button = form.querySelector("button");
  const message = form.querySelector("[data-resolution-status]");
  button.disabled = true;
  try {
    const response = await fetch(`/api/moderazione/segnalazioni/${detail.dataset.reportId}/risoluzione`, {
      method: "POST", credentials: "same-origin", body: new FormData(form),
      headers: { "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content },
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Salvataggio non riuscito.");
    window.location.reload();
  } catch (error) { message.textContent = error.message; button.disabled = false; }
});
