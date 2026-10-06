const reportList = document.querySelector("#report-list");
const listStatus = document.querySelector("#list-status");
const searchInput = document.querySelector("#search-input");
const reportForm = document.querySelector("#report-form");
const formStatus = document.querySelector("#form-status");

let searchTimer;

async function loadReports(search = "") {
  listStatus.textContent = "Caricamento…";
  reportList.replaceChildren();

  try {
    const response = await fetch(`/api/segnalazioni?q=${encodeURIComponent(search)}`);
    if (!response.ok) throw new Error("Impossibile caricare le segnalazioni.");

    const reports = await response.json();
    reports.forEach((report) => reportList.append(createReportCard(report)));
    listStatus.textContent = reports.length
      ? `${reports.length} contenuti trovati`
      : "Nessun contenuto trovato.";
  } catch (error) {
    listStatus.textContent = error.message;
  }
}

function createReportCard(report) {
  const article = document.createElement("article");
  article.className = "report-card";

  const badge = document.createElement("span");
  badge.className = "badge";
  badge.textContent = `${report.tipo} · ${formatState(report.stato)}`;

  const title = document.createElement("h3");
  title.textContent = report.titolo;

  const description = document.createElement("p");
  description.textContent = report.descrizione;

  const meta = document.createElement("p");
  meta.className = "report-meta";
  [
    report.indirizzo || "Luogo non indicato",
    report.autore,
    `${report.sostegni} sostegni`,
  ].forEach((text) => {
    const item = document.createElement("span");
    item.textContent = text;
    meta.append(item);
  });

  article.append(badge, title, description, meta);
  return article;
}

function formatState(state) {
  return String(state).replaceAll("_", " ");
}

searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadReports(searchInput.value.trim()), 250);
});

reportForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  formStatus.textContent = "Pubblicazione in corso…";

  const values = Object.fromEntries(new FormData(reportForm).entries());
  values.id_autore = Number(values.id_autore);

  try {
    const response = await fetch("/api/segnalazioni", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(values),
    });
    const result = await response.json();

    if (!response.ok) {
      const fieldErrors = Object.values(result.fields || {}).join(" ");
      throw new Error(fieldErrors || result.error || "Pubblicazione non riuscita.");
    }

    reportForm.reset();
    reportForm.elements.id_autore.value = 1;
    formStatus.textContent = "Contenuto pubblicato correttamente.";
    await loadReports(searchInput.value.trim());
  } catch (error) {
    formStatus.textContent = error.message;
  }
});

loadReports();

