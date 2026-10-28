// Un unico componente per bacheca e dettaglio: testo sempre via textContent.
function mountDiscussion(root, reportId, initial, onCount = () => {}) {
  const userId = Number(document.body.dataset.userId) || null;
  const moderator = document.body.dataset.moderator === "true";
  const token = document.querySelector('meta[name="csrf-token"]').content;
  const list = document.createElement("ul"); list.className = "comment-list";
  const message = document.createElement("p"); message.className = "status"; message.setAttribute("role", "status");
  const form = document.createElement("form");
  const label = document.createElement("label"); label.textContent = "Scrivi un commento";
  const text = document.createElement("textarea"); text.required = true; text.maxLength = 3000; text.rows = 3; label.append(text);
  const submit = document.createElement("button"); submit.type = "submit"; submit.className = "button"; submit.textContent = "Pubblica commento";
  const cancel = document.createElement("button"); cancel.type = "button"; cancel.className = "button button-secondary"; cancel.textContent = "Annulla risposta"; cancel.hidden = true;
  const replyTo = document.createElement("p"); replyTo.setAttribute("role", "status");
  let parentId = null;
  const resetReply = () => { parentId = null; replyTo.textContent = ""; cancel.hidden = true; };
  cancel.addEventListener("click", resetReply);
  form.append(replyTo, label, submit, cancel);
  root.replaceChildren(list, message);
  if (userId) root.append(form);
  else { const link = document.createElement("a"); link.href = "/login"; link.textContent = "Accedi per partecipare alla discussione"; root.append(link); }
  async function request(url, method = "GET", body) {
    const response = await fetch(url, { method, credentials: "same-origin", headers: { "X-CSRFToken": token, "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Operazione non riuscita.");
    return data;
  }
  function action(label, handler) {
    const button = document.createElement("button"); button.type = "button"; button.className = "button button-secondary"; button.textContent = label;
    button.addEventListener("click", async () => { button.disabled = true; try { await handler(); } catch (error) { message.textContent = error.message; } finally { button.disabled = false; } });
    return button;
  }
  function render(comments) {
    list.replaceChildren();
    const depths = new Map();
    const ids = new Set(comments.map((c) => c.id));
    const children = new Map();
    for (const comment of comments) {
      const parent = ids.has(comment.parent_id) ? comment.parent_id : null;
      if (!children.has(parent)) children.set(parent, []);
      children.get(parent).push(comment);
    }
    const ordered = [], stack = [...(children.get(null) || [])].reverse();
    const visited = new Set();
    while (stack.length) {
      const comment = stack.pop();
      if (visited.has(comment.id)) continue;
      visited.add(comment.id); ordered.push(comment);
      stack.push(...[...(children.get(comment.id) || [])].reverse());
    }
    ordered.forEach((comment) => {
      const item = document.createElement("li"); item.id = `comment-${comment.id}`;
      const depth = comment.parent_id ? Math.min((depths.get(comment.parent_id) || 0) + 1, 3) : 0;
      depths.set(comment.id, depth); item.className = `comment-item thread-level-${depth}`;
      const removed = comment.visibilita && comment.visibilita !== "pubblica";
      const author = document.createElement("strong"); author.textContent = removed ? "Commento rimosso" : comment.autore;
      const body = document.createElement("p"); body.textContent = comment.testo;
      item.append(author);
      if (comment.parent_id) { const parent = document.createElement("a"); parent.href = `#comment-${comment.parent_id}`; parent.textContent = `In risposta al commento #${comment.parent_id}`; item.append(parent); }
      item.append(body);
      if (userId && !removed) {
        item.append(action("Rispondi", () => { parentId = comment.id; replyTo.textContent = `In risposta a ${comment.autore}`; cancel.hidden = false; text.focus(); }));
        if (Number(comment.autore_id) === userId) item.append(action("Elimina il mio commento", async () => {
          if (!window.confirm("Eliminare il tuo commento? Le risposte rimarranno visibili.")) return;
          await request(`/api/commenti/${comment.id}`, "DELETE"); await refresh();
          if (parentId === comment.id) resetReply();
          message.textContent = "Commento eliminato.";
        }));
        if (moderator) item.append(action("Rimuovi commento", async () => { await request(`/api/moderazione/commenti/${comment.id}`, "DELETE"); await refresh(); }));
      }
      list.append(item);
    });
    const anchor = window.location.hash.slice(1);
    if (/^comment-\d+$/.test(anchor)) root.querySelector(`#${anchor}`)?.scrollIntoView?.({ block: "center" });
    onCount(comments.filter((c) => !c.visibilita || c.visibilita === "pubblica").length);
    message.textContent = comments.length ? "" : "Nessun commento. Inizia la discussione.";
  }
  async function refresh() { const data = await request(`/api/segnalazioni/${reportId}`); render(data.commenti || []); }
  form.addEventListener("submit", async (event) => {
    event.preventDefault(); if (!text.value.trim()) return;
    submit.disabled = true;
    try {
      await request(`/api/segnalazioni/${reportId}/commenti`, "POST", { testo: text.value.trim(), parent_id: parentId });
      text.value = ""; resetReply(); await refresh(); message.textContent = "Commento pubblicato.";
    } catch (error) { message.textContent = error.message; }
    finally { submit.disabled = false; }
  });
  if (initial) render(initial); else refresh().catch((error) => { message.textContent = error.message; root.append(action("Riprova", refresh)); });
}
