const target = document.querySelector("#my-reports");
const status = document.querySelector("#dashboard-status");
const filter = document.querySelector("#dashboard-filter");
const next = document.querySelector("#dashboard-next");
const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
let reports = [];
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

function createCard(report) {
  const card = document.createElement("article"); card.className = "report-card";
  const badge = document.createElement("span"); badge.className = "badge";
  badge.textContent = {
    pubblica: "Pubblicata", bozza: "In revisione", nascosta: "Nascosta",
    rimossa_moderazione: "Rimossa dai moderatori", rimossa_autore: "Ritirata da te",
  }[reportGroup(report)] || report.visibilita;
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
