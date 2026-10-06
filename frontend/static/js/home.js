const reportList = document.querySelector("#report-list");
const listStatus = document.querySelector("#list-status");
const searchInput = document.querySelector("#search-input");

let searchTimer;
let pendingRequest;

async function loadReports(search = "") {
  pendingRequest?.abort();
  const controller = new AbortController();
  pendingRequest = controller;
  listStatus.textContent = "Caricamento…";
  reportList.replaceChildren();

  try {
    const response = await fetch(`/api/segnalazioni?q=${encodeURIComponent(search)}`, {
      signal: controller.signal,
      credentials: "same-origin",
    });
    if (!response.ok) throw new Error("Impossibile caricare le segnalazioni.");

    const reports = await response.json();
    reports.forEach((report) => reportList.append(createReportCard(report)));
    listStatus.textContent = reports.length
      ? `${reports.length} contenuti trovati`
      : "Nessun contenuto trovato.";
  } catch (error) {
    if (error.name === "AbortError") return;
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

loadReports();
