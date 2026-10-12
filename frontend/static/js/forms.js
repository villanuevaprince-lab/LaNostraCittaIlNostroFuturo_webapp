// Le pagine inviano dati alle API JSON; credenziali e token restano fuori da localStorage.
const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || "";

document.querySelectorAll("[data-api-form]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const button = form.querySelector('button[type="submit"]');
    const status = form.querySelector("[data-form-status]");
    button.disabled = true;
    form.setAttribute("aria-busy", "true");
    status.textContent = "Invio in corso…";
    const payload = Object.fromEntries(new FormData(form));
    delete payload.csrf_token;
    try {
      const response = await fetch(form.action, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) {
        const details = result.fields ? Object.values(result.fields).flat().join(" ") : "";
        throw new Error([result.error, details].filter(Boolean).join(" "));
      }
      window.location.assign(result.redirect || "/");
    } catch (error) {
      status.textContent = error.message || "Invio non riuscito. Riprova.";
      status.focus?.();
      button.disabled = false;
      form.removeAttribute("aria-busy");
    }
  });
});

document.querySelectorAll("[data-api-action]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const response = await fetch(form.action, {
      method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": csrfToken() },
    });
    const result = await response.json();
    window.location.assign(result.redirect || "/");
  });
});
