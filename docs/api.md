# API e form

Pagine e API condividono la stessa origine. Non sono necessari CORS o token JWT.
L'autenticazione usa il cookie di sessione firmato Flask, non localStorage.

## GET /api/health

Restituisce `{"status": "ok", "database": "demo"}` oppure `database: "aiven"`.
Indica il modo configurato: **non verifica la connessione MySQL**.

## GET /api/segnalazioni?q=lampione

Pubblico. Ricerca per titolo, descrizione e indirizzo. Restituisce un array con
`id`, `tipo`, `titolo`, `descrizione`, `stato`, `indirizzo`, `autore`,
`data_creazione`, `sostegni`. Non restituisce email o hash delle password.

## POST /api/segnalazioni

Richiede sessione autenticata e token CSRF nell'header `X-CSRFToken`.
Nelle pagine HTML il token è nel meta tag `csrf-token`.

```json
{
  "tipo": "segnalazione",
  "titolo": "Lampione spento",
  "descrizione": "Il lampione non funziona da alcuni giorni.",
  "indirizzo": "Via Roma, Milano"
}
```

Non inviare `id_autore`: il server lo ricava dall'utente autenticato. Qualsiasi
campo extra come autore, stato o visibilità viene ignorato.

- 201: segnalazione creata.
- 400: dati non validi, JSON non oggetto oppure CSRF mancante/errato/scaduto.
- 401: sessione assente o account non disponibile (dopo un controllo CSRF valido).
- 413: corpo della richiesta oltre il limite.
- 503: problema del database; dettagli interni non esposti.

Gli errori di validazione hanno la forma:

```json
{"error": "Dati non validi.", "fields": {"titolo": ["Inserisci il titolo."]}}
```

## Form HTML (application/x-www-form-urlencoded)

| POST | Campi richiesti |
| --- | --- |
| /register | nome, cognome, email, password, password_confirm, csrf_token |
| /login | email, password, csrf_token |
| /logout | csrf_token |
| /reports/new | tipo, titolo, descrizione, csrf_token; indirizzo facoltativo |

Login e registrazione accettano anche `next`, limitato a `/`, `/home`,
`/dashboard` e `/reports/new`. Al successo rispondono con 303 e nuova pagina GET.
La registrazione accede automaticamente. Gli errori rendono il form con stato
400, 401 (credenziali non valide) o 409 (email già registrata).
I limiti di tentativi producono 429.

La pagina dedicata usa il POST HTML a `/reports/new`: non richiede fetch e funziona
anche senza JavaScript. Al successo aggiunge il messaggio flash e reindirizza a `/`.
L'API JSON non aggiunge messaggi flash: un eventuale client API gestisce la propria UI.
