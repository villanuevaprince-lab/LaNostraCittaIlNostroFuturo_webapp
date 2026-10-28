const notificationLabels = { nuovo_commento: "Nuovo commento al tuo contenuto", risposta_commento: "Nuova risposta al tuo commento", nuovo_sostegno: "Il tuo contenuto ha ricevuto un sostegno", cambio_stato: "È cambiato lo stato del tuo contenuto" };
(() => {
  const badge = document.querySelector("#notification-count");
  const root = document.querySelector("#notification-list");
  const next = document.querySelector("#notification-next");
  const message = document.querySelector("#notifications-status");
  const seen = new Set(); let cursor = null, loading = false;
  async function read(url, options) {
    const response = await fetch(url, { credentials: "same-origin", ...options });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Notifiche non disponibili.");
    return data;
  }
  function count(n) { if (badge) badge.textContent = n ? `(${n})` : ""; }
  async function load() {
    if (loading || (seen.size && cursor === null)) return;
    loading = true; if (next) next.disabled = true;
    try {
      const page = await read(`/api/notifiche${cursor ? `?cursor=${cursor}` : ""}`); count(page.non_lette);
      const fresh = page.items.filter((n) => !seen.has(n.id));
      for (const n of fresh) {
        seen.add(n.id);
        const item = document.createElement("li"); item.className = "comment-item";
        const link = document.createElement("a"); link.textContent = `${n.letta ? "" : "Nuova · "}${notificationLabels[n.tipo] || "Aggiornamento"} · #${n.report_id}`;
        link.href = `/reports/${n.report_id}${n.comment_id ? `#comment-${n.comment_id}` : ""}`;
        if (!n.letta) link.addEventListener("click", async (event) => {
          event.preventDefault();
          try { await read(`/api/notifiche/${n.id}`, { method: "PATCH", headers: { "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content } }); window.location.assign(link.href); }
          catch (error) { message.textContent = error.message; }
        });
        const date = document.createElement("p"); date.textContent = n.data.replace("T", " ");
        item.append(link, date); root.append(item);
      }
      cursor = fresh.length && page.next_cursor && (cursor === null || page.next_cursor < cursor) ? page.next_cursor : null;
      next.hidden = !cursor; message.textContent = seen.size ? "" : "Non hai ancora notifiche.";
    } catch (error) { if (message) message.textContent = error.message; }
    finally { loading = false; if (next) next.disabled = false; }
  }
  async function updateCount() {
    if (document.hidden) return;
    try { count((await read("/api/notifiche")).non_lette); } catch (_) { /* Il prossimo aggiornamento riprova. */ }
  }
  if (root) { next.addEventListener("click", load); load(); } else updateCount();
  setInterval(updateCount, 60000);
})();
