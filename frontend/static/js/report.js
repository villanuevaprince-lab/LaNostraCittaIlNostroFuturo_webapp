const form = document.querySelector("#report-form");
const status = form.querySelector("[data-form-status]");
const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";

async function fillSelect(url, select, emptyLabel) {
  const response = await fetch(url, { credentials: "same-origin" });
  if (!response.ok) throw new Error("Impossibile caricare le opzioni del modulo.");
  const rows = await response.json();
  select.replaceChildren();
  select.add(new Option(`Seleziona ${emptyLabel}`, ""));
  if (!rows.length) {
    select.options[0].textContent = `Nessun ${emptyLabel} disponibile`;
    select.disabled = true;
    return;
  }
  rows.forEach((row) => select.add(new Option(row.nome, row.id)));
}

Promise.all([
  fillSelect("/api/quartieri", document.querySelector("#neighborhood-select"), "quartiere"),
  fillSelect("/api/categorie", document.querySelector("#category-select"), "categoria"),
]).catch((error) => { status.textContent = error.message; });

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  form.setAttribute("aria-busy", "true");
  status.textContent = "Pubblicazione in corso…";
  try {
    const response = await fetch(form.action, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrf }, body: new FormData(form),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Pubblicazione non riuscita.");
    window.location.assign(result.redirect || "/");
  } catch (error) {
    status.textContent = error.message;
    button.disabled = false;
    form.removeAttribute("aria-busy");
  }
});
