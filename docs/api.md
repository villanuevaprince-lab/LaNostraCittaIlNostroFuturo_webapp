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
l'email si cambia con `POST /api/auth/me/email` (sotto). La cancellazione è logica:
imposta stato `cancellato`, registra l'evento e termina il cookie corrente.

`POST /api/auth/me/password` richiede JSON `password_attuale`,
`nuova_password`, `conferma_password`: verifica il vecchio hash, aggiorna con
CAS e audit, incrementa `SessionVersion` e ruota sessione/CSRF. Le altre
sessioni decadono alla richiesta successiva. Limite 5 tentativi/ora.
`POST /api/auth/me/avatar` riceve multipart `avatar` (JPEG/PNG/WebP, max 2 MB),
risalva senza EXIF in WebP su `UPLOAD_FOLDER/avatars`; `GET /api/auth/avatar/<id>`
serve l'immagine.

### Cambio email

`POST /api/auth/me/email` (sessione, CSRF, 5/ora) riceve JSON `nuova_email` e
`password` (password attuale). L'indirizzo viene normalizzato (trim, minuscole) e
validato. Se è libero, al nuovo indirizzo arriva un link `/email/conferma/<token>`
valido `EMAIL_CHANGE_MAX_AGE` secondi (default 3600); se è già usato non parte
nessuna email, ma la risposta è identica (`200 {ok, message}`), così l'endpoint
non rivela quali indirizzi sono registrati. `GET` sul link mostra solo un
pulsante; il `POST` aggiorna `UTENTE.Email` se l'indirizzo attuale coincide
ancora con quello del token (monouso), registra `EVENTO_LOG`/`VARIAZIONE_LOG` e
avvisa il vecchio indirizzo. Un conflitto con la UNIQUE risponde `409`.

### Reset della password

`GET/POST /password/dimenticata` (form HTML, CSRF; 5/minuto e 20/ora per IP,
3/ora per indirizzo) risponde sempre con la stessa pagina e lo stesso codice
`200`, registrato o no l'indirizzo. Se l'account esiste (attivo o bannato, non
cancellato) parte un link `/password/reimposta/<token>`. Il token è firmato con
`itsdangerous.URLSafeTimedSerializer` (`SECRET_KEY`, salt dedicato), scade dopo
`PASSWORD_RESET_MAX_AGE` secondi (default 1800) e contiene un'impronta dell'hash
attuale della password: dopo il reset l'impronta non corrisponde più, quindi il
link è monouso. La pagina di reset chiede password e conferma (12–128 caratteri,
come la registrazione), salva l'hash Argon2id con un aggiornamento condizionato
all'hash precedente, incrementa `SessionVersion` (tutte le sessioni decadono),
svuota la sessione corrente e invia un avviso. Le pagine con token rispondono con
`Referrer-Policy: no-referrer`.

### Utenti bannati

Un account con `StatoAccount='bloccato'` può accedere; il redirect dopo il login
porta a `/profilo`. A ogni richiesta `load_current_user` rilegge stato e ultimo
blocco non revocato (`BLOCCO`): un blocco temporaneo scaduto viene chiuso e
l'account riattivato automaticamente. Finché il ban è attivo, un `before_request`
globale consente solo la lettura dell'area personale (`/profilo`, `/dashboard`,
`/api/auth/me`, `/api/me/segnalazioni`, cataloghi, stati, allegati, avatar),
il logout e il recupero password; ogni altra richiesta risponde `403`
(`{"error": ..., "bannato": true}` per le API, pagina d'errore per l'HTML).
`GET /api/auth/me` include `ban` con `motivo`, `data_inizio`, `data_fine`.

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
visibilità non vengono usati. File, segnalazione, categorie, pubblicazione,
storico iniziale ed evento vengono registrati nella stessa transazione SQL;
la visibilità passa a `pubblica` dopo aver inserito l'allegato. Se il DB fallisce,
il file appena scritto viene eliminato. La risposta è `201` e include la
destinazione `/dashboard` con messaggio flash di pubblicazione.

Le coordinate arrivano dal pin e sono validate sul server (entro Milano); se
mancano e la foto contiene un GPS EXIF valido a Milano, si usa quello (l'indirizzo
resta obbligatorio). Con `AI_ENABLED=true` le categorie sono facoltative (l'IA ne
propone fino a 3, `Origine='ia'`); senza categorie né proposta l'API risponde `400`.
La risposta `201` contiene `report.visibilita` (`pubblica` oppure `bozza` se il
comitato deve verificarlo) e `report.ia = {esito, messaggi}`. Un testo offensivo o
d'odio ad alta confidenza è rifiutato con `400` e `{error}`. La colonna `DescrizioneAccessibile` esistente viene compilata
automaticamente con il tipo di media e il titolo (non descrive dettagli visivi
non verificabili). Le immagini sono risalvate senza EXIF (il GPS è letto prima). I video
sono controllati tramite firme file MP4/WebM, non solo nome/estensione.

### Supporto IA al form (login e CSRF richiesti)

- `POST /api/ia/suggerisci-categorie`: JSON `titolo` (3–200) e `descrizione`
  (10–5000). Risposta `{disponibile, categorie: [{id, nome, confidenza}]}`;
  `{disponibile: false, categorie: []}` se l'IA è disattivata; `503` se Ollama non risponde.
  Limite 10/minuto.
- `POST /api/ia/analizza-foto`: multipart con `allegato` (immagine). Legge solo il GPS
  EXIF, senza modello: `{gps: {latitude, longitude, in_milan} | null}`. Limite 20/minuto.

`GET /api/moderazione/coda` aggiunge a ogni elemento `analisi_ia`
(`tipo`, `esito`, `confidenza`, `revisione`, `motivo`); `?vista=bozza` mostra i
contenuti in revisione. Approvare o rimuovere un contenuto chiude le analisi
in attesa (`respinta` se pubblicato, `confermata` altrimenti). Le categorie del
dettaglio includono `origine` (`utente`, `ia`, `moderatore`).

### `GET /api/segnalazioni/<id>`

Restituisce dettaglio, categorie, coordinate, allegato e commenti pubblici.
I contenuti non pubblici sono visibili solo all'autore e ai moderatori.
`GET /reports/<id>` mostra anche una mappa; segnalazioni storiche prive di
coordinate sono mostrate senza pin. `DELETE /api/segnalazioni/<id>` consente
all'autore il ritiro logico, irreversibile via UI, con evento di audit.
Per `?mie=1`, le righe includono `ritirata_autore` così la dashboard distingue
una rimozione del moderatore da un ritiro volontario.

`GET /api/me/segnalazioni?vista=<vista>&cursor=<id>` richiede login e alimenta
la dashboard in pagine da 25. Le viste sono `tutte`, `pubblica`, `bozza`,
`nascosta`, `rimossa_moderazione` e `rimossa_autore`; restituisce `items` e
`next_cursor`. La separazione dei ritiri è verificata sul server tramite
gli eventi di audit.

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

- `GET /api/moderazione/coda?vista=aperta&cursor=<id>&limit=10`: coda filtrata
  per stato (`nuova`, `aperta`, `in_valutazione`, `in_lavorazione`,
  `presa_in_carico`, `risolta`, `chiusa`). `vista=tutte` include tutte le
  segnalazioni tranne quelle nascoste o eliminate; `vista=rimossa` raccoglie
  gli eliminati. La UI richiede 5 elementi iniziali e poi 10 per clic. Il
  parametro precedente `visibilita` resta accettato per compatibilità. La
  risposta usa paginazione keyset con `items` e `next_cursor`; la vista
  `rimossa` include `ritirata_autore`.
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
  `giorni` 1–365 o `null`; aggiorna `UTENTE`, `BLOCCO` ed evento. Vale dalla
  richiesta successiva dell'utente, anche con una sessione già aperta.
- `POST /api/moderazione/utenti/<id>/ban-permanente`: JSON `motivazione`
  obbligatoria, massimo 3000 caratteri. Revoca il blocco temporaneo corrente,
  ne registra uno senza scadenza; l'utente può ancora accedere ma solo in sola lettura
  della propria area (vedi «Utenti bannati»); storico,
  contenuti e relazioni restano conservati. Non cancella fisicamente l'account.
- `POST /api/moderazione/utenti/<id>/sblocco`: JSON `motivazione` facoltativa;
  registra revoca e riattiva l'account.

`GET /api/stati` include `prossimi` con le transizioni consentite dalla
macchina a stati. Un moderatore può ripubblicare i contenuti che ha rimosso:
la transizione viene registrata in `EVENTO_LOG`. Il ritiro dell'autore resta
definitivo. Blocco utenti moderatori non consentito;
la revoca amministrativa può rimuovere anche un ban senza scadenza.

## Mappa

`GET /api/map-items` (pubblico) restituisce i soli campi necessari alla mappa
della homepage: `{items: [{id, tipo, lat, lng, titolo, stato}], senza_coordinate,
troncato}`. Include i contenuti pubblici non uniti come duplicati, con
`Latitudine` e `Longitudine` valorizzate (`DECIMAL(9,6)`, indice
`idx_segnalazione_coordinate`), fino a 5000 elementi dal più recente
(`troncato=true` se ce ne sono altri). Quelli senza coordinate non sono un
errore: sono contati in `senza_coordinate` e mostrati in legenda. Le coordinate
vengono salvate alla creazione dal pin sulla mappa (clic o trascinamento),
dalla ricerca di un indirizzo geocodificato oppure dal GPS EXIF della foto, e
sono sempre validate sul server entro l'area di Milano.

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
