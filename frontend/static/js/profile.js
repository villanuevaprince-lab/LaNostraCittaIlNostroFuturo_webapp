const form = document.querySelector("#profile-form");
const status = document.querySelector("#profile-status");
const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
const neighborhood = document.querySelector("#profile-neighborhood");

async function loadProfile() {
  const [userResponse, neighborhoodResponse] = await Promise.all([
    fetch("/api/auth/me", { credentials: "same-origin" }),
    fetch("/api/quartieri", { credentials: "same-origin" }),
  ]);
  const { user } = await userResponse.json();
  const options = await neighborhoodResponse.json();
  options.forEach((row) => neighborhood.add(new Option(row.nome, row.id)));
  form.elements.nome.value = user.nome;
  form.elements.cognome.value = user.cognome;
  form.elements.email.value = user.email;
  if (user.quartiere_id) neighborhood.value = user.quartiere_id;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const response = await fetch("/api/auth/me", {
    method: "PATCH", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
    body: JSON.stringify({ nome: form.elements.nome.value, cognome: form.elements.cognome.value,
      quartiere_id: neighborhood.value || null }),
  });
  const result = await response.json();
  status.textContent = response.ok ? "Profilo aggiornato." : result.error;
});

document.querySelector("#delete-account").addEventListener("click", async () => {
  if (!window.confirm("Confermi la cancellazione del tuo account?")) return;
  const response = await fetch("/api/auth/me", {
    method: "DELETE", credentials: "same-origin", headers: { "X-CSRFToken": csrf },
  });
  const result = await response.json();
  if (response.ok) window.location.assign(result.redirect || "/");
  else status.textContent = result.error || "Operazione non riuscita.";
});

loadProfile().catch((error) => { status.textContent = error.message; });
