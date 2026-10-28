// I nomi e le transizioni arrivano dal vocabolario del backend.
const civicStates = fetch("/api/stati").then((r) => {
  if (!r.ok) throw new Error("Stati non disponibili");
  return r.json();
});
civicStates.catch(() => {});
function setStateBadge(element, report) {
  element.className = "badge state-badge";
  element.dataset.state = report.stato;
  element.textContent = `${report.tipo} · ${report.stato.replaceAll("_", " ")}`;
  civicStates.then((states) => {
    const state = states.find((s) => s.codice === report.stato);
    element.textContent = `${report.tipo} · ${state?.etichetta || report.stato}`;
  }).catch(() => {});
}
