# API REST JSON

Le pagine e le API sono same-origin e servite da Flask. I browser inviano il
cookie di sessione automaticamente; niente JWT o token in `localStorage`.
Ogni mutazione (`POST`, `PUT`, `PATCH`, `DELETE`) richiede CSRF nell'header:

```js
const csrf = document.querySelector('meta[name="csrf-token"]').content;
await fetch("/api/auth/me", {
  method: "PATCH",
  credentials: "same-origin",
  headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
  body: JSON.stringify({ nome: "Ada", cognome: "Rossi", quartiere_id: 2 }),
});
```

## Autenticazione e profilo

### `POST /api/auth/register`

JSON: `nome`, `cognome`, `email`, `password`, `password_confirm`, opzionale
`next`. Password 12–128 caratteri. Nuovi hash Argon2id. Risposta `201` con
utente pubblico e destinazione; `409` per email duplicata; `400` per validazione.

### `POST /api/auth/login`

JSON: `email`, `password`, opzionale `next`. Il server verifica account attivo,
hash password e destinazione interna. Risposta `200`; credenziali o account non
validi restituiscono `401` con messaggio generico. Gli hash legacy validi sono
aggiornati ad Argon2id dopo l'accesso.

### `POST /api/auth/logout`

Svuota la sessione e risponde `{"ok": true, "redirect": "/"}`.

### `GET`, `PATCH`, `DELETE /api/auth/me`

Richiedono sessione. Il `PATCH` accetta `nome`, `cognome`, `quartiere_id`,
`bio` (massimo 500 caratteri) e `notifiche_email` (booleano);
l'email non è modificabile da questo endpoint. La cancellazione è logica:
imposta stato `cancellato`, registra l'evento e termina il cookie corrente.

`POST /api/auth/me/password` richiede JSON `password_attuale`,
`nuova_password`, `conferma_password`: verifica il vecchio hash, aggiorna con
CAS e audit, incrementa `SessionVersion` e ruota sessione/CSRF. Le altre
sessioni decadono alla richiesta successiva. Limite 5 tentativi/ora.
`POST /api/auth/me/avatar` riceve multipart `avatar` (JPEG/PNG/WebP, max 2 MB),
risalva senza EXIF in WebP su `UPLOAD_FOLDER/avatars`; `GET /api/auth/avatar/<id>`
serve l'immagine.

## Cataloghi e segnalazioni

### `GET /api/quartieri`, `GET /api/categorie`, `GET /api/stati`

Restituiscono i cataloghi attivi. Quartieri e categorie provengono da MySQL.

### `GET /api/segnalazioni`

Pubblico. Parametri facoltativi:

- `q`: cerca titolo, descrizione o indirizzo;
- `quartiere`: ID del quartiere;
- `categoria`: ID categoria ripetibile (fino a 10, logica OR: almeno una corrisponde);
- `stato`: codice stato;
- `ordina`: `recenti` (default) oppure `sostegni` (priorità per sostegni attivi);
- `mie=1`: contenuti dell'utente autenticato.

Risultati limitati a 100; l'ordinamento per sostegni usa data e ID come
discriminanti. Ogni riga include `sostegni`, `commenti_count`, `sostenuta`
per l'utente corrente e ID, MIME e descrizione del primo allegato.
Include `categorie` come array di oggetti `{id, nome}` per i tag; non include email/hash.

### `POST /api/segnalazioni`

Richiede sessione, CSRF e `multipart/form-data`. Campi:

| Campo | Regola |
| --- | --- |
| `tipo` | `segnalazione` oppure `proposta` |
| `titolo` | 3–200 caratteri |
| `descrizione` | 10–5000 caratteri |
| `quartiere_id` | ID di un quartiere attivo |
| `categoria_ids` | Da 1 a 5 ID distinti di categorie attive (campo ripetibile); `categoria_id` è accettato per compatibilità |
| `indirizzo` | Obbligatorio, 3–255 caratteri; correggibile dopo il posizionamento |
| `latitude`, `longitude` | Obbligatorie, coordinate del pin nell'area di Milano |
| `allegato` | Obbligatorio; JPEG, PNG, WebP, MP4 o WebM; massimo 20 MB |

Esempio browser:

```js
const response = await fetch("/api/segnalazioni", {
  method: "POST",
  credentials: "same-origin",
  headers: { "X-CSRFToken": csrf },
  body: new FormData(document.querySelector("#report-form")),
});
```

L'autore proviene dalla sessione; valori client come `id_autore`, stato e
visibilità non vengono usati. File, segnalazione inizialmente in bozza, categorie,
storico iniziale ed evento vengono registrati insieme nella transazione SQL;
la visibilità resta `bozza` finché il moderatore approva. Se il DB fallisce,
il file appena scritto viene eliminato. La risposta è `201` e include la
destinazione `/dashboard` con messaggio flash di conferma.

Le coordinate non sono lette dall'EXIF: arrivano dal pin e sono validate sul
server. La colonna `DescrizioneAccessibile` esistente viene compilata
automaticamente con il tipo di media e il titolo (non descrive dettagli visivi
non verificabili). Le immagini sono risalvate senza EXIF. I video
sono controllati tramite firme file MP4/WebM, non solo nome/estensione.

### `GET /api/segnalazioni/<id>`

Restituisce dettaglio, categorie, coordinate, allegato e commenti pubblici.
I contenuti non pubblici sono visibili solo all'autore e ai moderatori.
`GET /reports/<id>` mostra anche una mappa; segnalazioni storiche prive di
coordinate sono mostrate senza pin. `DELETE /api/segnalazioni/<id>` consente
all'autore il ritiro logico, irreversibile via UI, con evento di audit.

### `GET /api/allegati/<id>`

Restituisce il file se collegato a segnalazione pubblica o visibile ad autore/
moderatore (ma mai dopo il ritiro). Il percorso usa
un nome casuale generato dal server e viene confinato nella directory upload.

## Commenti e sostegni

- `POST /api/segnalazioni/<id>/commenti`: sessione + CSRF, JSON `{"testo":"..."}`,
  1–3000 caratteri. `201` a successo.
- `GET /api/segnalazioni/<id>/sostegno`: sessione, restituisce `sostenuta` boolean.
- `PUT /api/segnalazioni/<id>/sostegno`: sessione + CSRF, esprime o riattiva il
  sostegno; il vincolo unico impedisce duplicati.
- `DELETE /api/segnalazioni/<id>/sostegno`: sessione + CSRF, valorizza `DataRitiro`.
  Entrambe le mutazioni sono idempotenti e restituiscono `sostenuta` e
  `sostegni` aggiornati; solo i cambiamenti effettivi creano un evento audit.

## Moderazione

Tutti gli endpoint seguenti richiedono una riga corrispondente in `MODERATORE`
e CSRF sulle mutazioni.

- `GET /api/moderazione/coda?visibilita=bozza&cursor=<id>&limit=25`: coda
  keyset (`bozza`, `pubblica`, `nascosta`), `items` e `next_cursor`.
- `POST /api/moderazione/segnalazioni/azioni`: JSON `ids` (1–50 interi) e
  `azione` (`approva`, `rifiuta`, `nascondi`), transazione e audit per elemento.
- `GET /api/moderazione/utenti?cursor=<id>&q=<prefisso>`: account non moderatori
  in pagine da 25, ricerca per prefisso di nome, cognome, email oppure ID esatto;
  include email, `tipo_blocco` (`attivo`, `temporaneo`, `permanente`, `scaduto`)
  e `blocco_fine`. La UI seleziona tutte le righe caricate, max 50 per batch.
- `PATCH /api/segnalazioni/<id>/stato`: JSON `stato`, opzionale `motivazione`;
  valida transizioni, aggiorna `SEGNALAZIONE`, `STORICO_STATO` ed `EVENTO_LOG`.
- `PATCH /api/moderazione/segnalazioni/<id>`: JSON `visibilita` (`nascosta`,
  `rimossa`, `pubblica`) e evento audit.
- `DELETE /api/moderazione/commenti/<id>`: rende il commento `rimossa` e registra evento.
- `POST /api/moderazione/utenti/<id>/blocco`: JSON `motivazione` obbligatoria e
  `giorni` 1–365 o `null`; aggiorna `UTENTE`, `BLOCCO` ed evento.
- `POST /api/moderazione/utenti/<id>/ban-permanente`: JSON `motivazione`
  obbligatoria, massimo 3000 caratteri. Revoca il blocco temporaneo corrente,
  ne registra uno senza scadenza e disabilita l'accesso dell'utente; storico,
  contenuti e relazioni restano conservati. Non cancella fisicamente l'account.
- `POST /api/moderazione/utenti/<id>/sblocco`: JSON `motivazione` facoltativa;
  registra revoca e riattiva l'account.

`GET /api/stati` include `prossimi` con le transizioni consentite dalla
macchina a stati. `rimossa` è terminale: un contenuto ritirato o rifiutato non
può essere approvato nuovamente. Blocco utenti moderatori non consentito;
la revoca amministrativa può rimuovere anche un ban senza scadenza.

## Mappa

`GET /api/geo/search?q=<indirizzo>` e `/api/geo/reverse?lat=<numero>&lng=<numero>`
richiedono login e sono limitati globalmente (1 richiesta/s, 1000/giorno nello
storage di rate limit). Il geocoder è invocato solo su ricerca esplicita o
spostamento del pin; non è un servizio di autocomplete. Nessuna chiamata dal
browser direttamente a Nominatim; le tile OSM sono caricate dal browser con
attribuzione.

## Errori

Gli errori API hanno forma JSON `{"error":"..."}`; la validazione può includere
`fields`. Codici usati: `400` dati/CSRF, `401` accesso richiesto o credenziali
non valide, `403` ruolo insufficiente, `404` elemento non visibile/inesistente,
`409` conflitto/duplicato, `413` body troppo grande, `429` limite richieste,
`503` DB non disponibile. Nessun errore SQL include password o query.
