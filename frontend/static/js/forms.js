// Il browser invia normali form POST; sessioni e autorizzazioni restano sul server.
// Questo file migliora solo l'esperienza, senza salvare password o token in localStorage.
document.querySelectorAll("[data-submit-form]").forEach((form) => {
  form.addEventListener("submit", () => {
    const button = form.querySelector('button[type="submit"]');
    button.dataset.originalLabel = button.textContent;
    button.textContent = button.dataset.busyLabel;
    button.disabled = true;
    form.setAttribute("aria-busy", "true");
  });
});

// Tornando indietro dalla cache del browser il form deve essere nuovamente utilizzabile.
window.addEventListener("pageshow", () => {
  document.querySelectorAll("[data-submit-form]").forEach((form) => {
    const button = form.querySelector('button[type="submit"]');
    if (button.dataset.originalLabel) button.textContent = button.dataset.originalLabel;
    button.disabled = false;
    form.removeAttribute("aria-busy");
  });
});

document.querySelector("[data-error-summary]")?.focus();
