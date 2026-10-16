const form = document.querySelector("#report-form");
const status = form.querySelector("[data-form-status]");
const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
const locationStatus = document.querySelector("#location-status");
const address = document.querySelector("#selected-address");
const latitude = document.querySelector("#selected-latitude");
const longitude = document.querySelector("#selected-longitude");
const results = document.querySelector("#location-results");
const searchInput = document.querySelector("#location-search");
let pointVersion = 0;
let picker;

const setCoordinates = (lat, lng) => {
  latitude.value = Number(lat).toFixed(6);
  longitude.value = Number(lng).toFixed(6);
};

async function reverseAddress(lat, lng) {
  const version = ++pointVersion;
  setCoordinates(lat, lng);
  address.value = "";
  locationStatus.textContent = "Ricerca indirizzo del punto…";
  try {
    const response = await fetch(`/api/geo/reverse?lat=${encodeURIComponent(latitude.value)}&lng=${encodeURIComponent(longitude.value)}`);
    const data = await response.json();
    if (version !== pointVersion) return;
    if (!response.ok) throw new Error(data.error || "Indirizzo non disponibile.");
    address.value = data.indirizzo || "";
    locationStatus.textContent = "Posizione selezionata. Verifica l'indirizzo prima di inviare.";
  } catch (error) {
    if (version === pointVersion) locationStatus.textContent = `${error.message} Inserisci l'indirizzo manualmente.`;
  }
}

try {
  picker = setupMap(document.querySelector("#location-map"), { onMove: reverseAddress });
} catch (error) { locationStatus.textContent = error.message; }

async function searchLocation() {
  const query = searchInput.value.trim();
  if (query.length < 3) { locationStatus.textContent = "Inserisci almeno tre caratteri."; return; }
  const button = document.querySelector("#location-search-button");
  button.disabled = true;
  locationStatus.textContent = "Ricerca del luogo…";
  try {
    const response = await fetch(`/api/geo/search?q=${encodeURIComponent(query)}`);
    const places = await response.json();
    if (!response.ok) throw new Error(places.error || "Ricerca non riuscita.");
    results.replaceChildren();
    const selectPlace = (place) => {
      ++pointVersion;
      picker?.setPoint(place.lat, place.lng);
      setCoordinates(place.lat, place.lng);
      address.value = place.indirizzo;
      locationStatus.textContent = "Posizione trovata. Puoi trascinare il segnaposto per correggerla.";
    };
    places.forEach((place) => {
      const choice = document.createElement("button");
      choice.type = "button";
      choice.className = "location-choice";
      choice.textContent = place.indirizzo;
      choice.addEventListener("click", () => selectPlace(place));
      results.append(choice);
    });
    if (places.length) selectPlace(places[0]);
    else locationStatus.textContent = "Nessun risultato nell'area di Milano. Prova un'altra via o zona.";
  } catch (error) { locationStatus.textContent = error.message; }
  finally { button.disabled = false; }
}

document.querySelector("#location-search-button").addEventListener("click", searchLocation);
searchInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") { event.preventDefault(); searchLocation(); }
});

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

async function fillCategories() {
  const response = await fetch("/api/categorie", { credentials: "same-origin" });
  if (!response.ok) throw new Error("Impossibile caricare le categorie.");
  const categories = await response.json();
  const container = document.querySelector("#category-options");
  container.replaceChildren();
  categories.forEach((category) => {
    const label = document.createElement("label"); label.className = "tag-option";
    const input = document.createElement("input");
    input.type = "checkbox"; input.name = "categoria_ids"; input.value = category.id;
    input.addEventListener("change", () => {
      const chosen = container.querySelectorAll('input:checked');
      if (chosen.length > 5) {
        input.checked = false;
        status.textContent = "Puoi scegliere al massimo cinque categorie.";
      }
    });
    const text = document.createElement("span"); text.textContent = category.nome;
    label.append(input, text); container.append(label);
  });
  if (!categories.length) throw new Error("Nessuna categoria disponibile.");
}

Promise.all([
  fillSelect("/api/quartieri", document.querySelector("#neighborhood-select"), "quartiere"),
  fillCategories(),
]).catch((error) => { status.textContent = error.message; });

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!latitude.value || !longitude.value) {
    locationStatus.textContent = "Seleziona un punto sulla mappa o dalla ricerca.";
    searchInput.focus();
    return;
  }
  if (!form.reportValidity()) return;
  if (!form.querySelector('input[name="categoria_ids"]:checked')) {
    status.textContent = "Seleziona almeno una categoria.";
    form.querySelector('input[name="categoria_ids"]')?.focus();
    return;
  }
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
