const form = document.querySelector("#profile-form");
const status = document.querySelector("#profile-status");
const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
const neighborhood = document.querySelector("#profile-neighborhood");

function avatarPreview(user) {
  const image = document.querySelector("#profile-avatar");
  image.hidden = !user.avatar_riferimento;
  if (user.avatar_riferimento) image.src = `/api/auth/avatar/${user.id}?v=${Date.now()}`;
}

async function readJSON(response) {
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Operazione non riuscita.");
  return data;
}

async function loadProfile() {
  const [userResponse, neighborhoodResponse] = await Promise.all([
    fetch("/api/auth/me", { credentials: "same-origin" }),
    fetch("/api/quartieri", { credentials: "same-origin" }),
  ]);
  const { user } = await readJSON(userResponse);
  const options = await readJSON(neighborhoodResponse);
  options.forEach((row) => neighborhood.add(new Option(row.nome, row.id)));
  form.elements.nome.value = user.nome;
  form.elements.cognome.value = user.cognome;
  form.elements.email.value = user.email;
  if (user.quartiere_id) neighborhood.value = user.quartiere_id;
  form.elements.bio.value = user.bio || "";
  form.elements.notifiche_email.checked = Boolean(user.notifiche_email);
  avatarPreview(user);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  status.textContent = "Salvataggio…";
  try { const response = await fetch("/api/auth/me", {
    method: "PATCH", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
    body: JSON.stringify({ nome: form.elements.nome.value, cognome: form.elements.cognome.value,
      quartiere_id: neighborhood.value || null, bio: form.elements.bio.value,
      notifiche_email: form.elements.notifiche_email.checked }),
  });
  await readJSON(response);
  status.textContent = "Profilo aggiornato.";
  } catch (error) { status.textContent = error.message; }
});

document.querySelector("#password-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const passwordForm = event.currentTarget;
  const output = document.querySelector("#password-status");
  const button = passwordForm.querySelector("button"); button.disabled = true;
  try {
    const response = await fetch("/api/auth/me/password", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify(Object.fromEntries(new FormData(passwordForm))),
    });
    await readJSON(response);
    passwordForm.reset();
    // Il backend ruota anche il CSRF token e invalida le altre sessioni.
    window.location.assign("/profilo");
  } catch (error) { output.textContent = error.message; button.disabled = false; }
});

document.querySelector("#avatar-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const avatarForm = event.currentTarget;
  const output = document.querySelector("#avatar-status");
  const button = avatarForm.querySelector("button"); button.disabled = true;
  try {
    const response = await fetch("/api/auth/me/avatar", {
      method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": csrf },
      body: new FormData(avatarForm),
    });
    const data = await readJSON(response);
    const image = document.querySelector("#profile-avatar");
    image.src = `${data.avatar_url}?v=${Date.now()}`; image.hidden = false;
    avatarForm.reset(); output.textContent = "Avatar aggiornato.";
  } catch (error) { output.textContent = error.message; }
  finally { button.disabled = false; }
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
