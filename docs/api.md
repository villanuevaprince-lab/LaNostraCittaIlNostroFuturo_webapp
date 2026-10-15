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

Richiedono sessione. Il `PATCH` accetta solo `nome`, `cognome` e `quartiere_id`;
l'email non è modificabile da questo endpoint. La cancellazione è logica:
imposta stato `cancellato`, registra l'evento e termina il cookie corrente.

## Cataloghi e segnalazioni

### `GET /api/quartieri`, `GET /api/categorie`, `GET /api/stati`

Restituiscono i cataloghi attivi. Quartieri e categorie provengono da MySQL;
la modalità demo usa un catalogo in memoria.

### `GET /api/segnalazioni`

Pubblico. Parametri facoltativi:

- `q`: cerca titolo, descrizione o indirizzo;
- `quartiere`: ID del quartiere;
- `categoria`: ID categoria;
- `stato`: codice stato;
- `ordina`: `recenti` (default) oppure `sostegni` (priorità per sostegni attivi);
- `mie=1`: contenuti dell'utente autenticato.

Risultati limitati a 100; l'ordinamento per sostegni usa data e ID come
discriminanti. Ogni riga include `sostegni`, `commenti_count`, `sostenuta`
per l'utente corrente e ID, MIME e descrizione del primo allegato.
Non include email/hash.

### `POST /api/segnalazioni`

Richiede sessione, CSRF e `multipart/form-data`. Campi:

| Campo | Regola |
| --- | --- |
| `tipo` | `segnalazione` oppure `proposta` |
| `titolo` | 3–200 caratteri |
| `descrizione` | 10–5000 caratteri |
| `quartiere_id` | ID di un quartiere attivo |
| `categoria_id` | Un ID categoria attiva, scelto dal menu a tendina |
| `indirizzo` | Facoltativo, massimo 255 caratteri |
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
la visibilità diventa pubblica solo dopo l'allegato. Se il DB fallisce,
il file appena scritto viene eliminato. La risposta è `201` e include la
destinazione `/` con messaggio flash di conferma.

Le coordinate non sono raccolte dal form né lette dall'EXIF: le nuove righe
usano NULL. La colonna `DescrizioneAccessibile` esistente viene compilata
automaticamente con il tipo di media e il titolo (non descrive dettagli visivi
non verificabili). Le immagini sono risalvate senza EXIF. I video
sono controllati tramite firme file MP4/WebM, non solo nome/estensione.

### `GET /api/segnalazioni/<id>`

Restituisce dettaglio e commenti pubblici della segnalazione. Contenuti nascosti
o rimossi restituiscono `404`.

### `GET /api/allegati/<id>`

Restituisce il file solo se collegato a segnalazione pubblica. Il percorso usa
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

- `GET /api/moderazione/utenti`: elenco limitato di account attivi escluso il moderatore corrente.
- `PATCH /api/segnalazioni/<id>/stato`: JSON `stato`, opzionale `motivazione`;
  valida transizioni, aggiorna `SEGNALAZIONE`, `STORICO_STATO` ed `EVENTO_LOG`.
- `PATCH /api/moderazione/segnalazioni/<id>`: JSON `visibilita` (`nascosta`,
  `rimossa`, `pubblica`) e evento audit.
- `DELETE /api/moderazione/commenti/<id>`: rende il commento `rimossa` e registra evento.
- `POST /api/moderazione/utenti/<id>/blocco`: JSON `motivazione` obbligatoria e
  `giorni` 1–365 o `null`; aggiorna `UTENTE`, `BLOCCO` ed evento.
- `POST /api/moderazione/utenti/<id>/sblocco`: JSON `motivazione` facoltativa;
  registra revoca e riattiva l'account.

## Errori

Gli errori API hanno forma JSON `{"error":"..."}`; la validazione può includere
`fields`. Codici usati: `400` dati/CSRF, `401` accesso richiesto o credenziali
non valide, `403` ruolo insufficiente, `404` elemento non visibile/inesistente,
`409` conflitto/duplicato, `413` body troppo grande, `429` limite richieste,
`503` DB non disponibile. Nessun errore SQL include password o query.
