# Architettura applicativa

Il progetto usa Flask con HTML/Jinja, CSS e JavaScript vanilla serviti dalla
stessa origine. Le pagine contengono la struttura e il token CSRF; i moduli
JavaScript inviano i dati alle API JSON. L'autenticazione usa cookie di sessione
firmati Flask, senza token JWT esposti al browser.

## Rotte web

| Rotta | Accesso | Scopo |
| --- | --- | --- |
| `/` | Pubblico | Bacheca con filtri, commenti e sostegni |
| `/login`, `/register` | Pubblico | Accesso e creazione account |
| `/reports/new` | Autenticato | Form dedicato per segnalazioni e proposte |
| `/dashboard` | Autenticato | Bacheca personale con le proprie segnalazioni |
| `/profilo` | Autenticato | Modifica dati e cancellazione logica account |
| `/moderazione` | Ruolo moderatore | Strumenti di moderazione |

`/reports/new` è una pagina separata dalla home. Il POST applicativo è
`multipart/form-data` su `/api/segnalazioni`: l'utente deve essere autenticato,
il token CSRF è verificato e il server ricava l'autore dalla sessione. Dopo
l'invio, la pagina mostra una conferma e riporta alla home.

## Struttura del codice

```text
backend/
├── api/             # endpoint JSON per auth e cataloghi
├── repositories/    # query SQL e modalità demo
├── services/        # regole di validazione e casi d'uso
├── app.py           # application factory, errori e intestazioni
├── auth.py          # form HTML di login e registrazione
├── reports.py       # endpoint segnalazioni e moderazione
├── security.py      # sessione, CSRF, ruoli e password
└── users.py         # accesso utenti e profilo
frontend/
├── templates/       # pagine HTML/Jinja
└── static/          # CSS e JavaScript per pagina
database/
├── migrations/      # migrazione manuale per il database iniziale
└── seeds/           # quartieri, categorie e stati di riferimento
```

## Autenticazione e autorizzazione

La tabella `UTENTE` è riutilizzata. Nuove password sono salvate con Argon2id;
gli hash legacy scrypt, PBKDF2 e Argon2 già esistenti sono verificati e
aggiornati al login riuscito. Il cookie è `HttpOnly`, `SameSite=Lax`, dura due
ore ed è marcato `Secure` quando configurato per HTTPS. Flask-WTF protegge tutte
le richieste che modificano dati, incluse le richieste JSON.

L'utente viene ricaricato dal database a ogni richiesta. Il ruolo moderatore
viene controllato in `MODERATORE` lato server; un campo inviato dal browser non
può concedere permessi. I redirect post-login accettano solo destinazioni
interne previste.

## Segnalazioni, allegati e database

Il service valida i campi, i quartieri e le categorie attive, verifica coordinate
e allegato, poi il repository inserisce segnalazione, allegato, categorie,
storico iniziale ed evento di audit nella stessa transazione MySQL. Se il
salvataggio DB fallisce, il file viene rimosso. Gli upload hanno limite 20 MB,
nomi casuali, verifica della firma e, per le immagini, decodifica e riscrittura
Pillow per rimuovere metadati EXIF. Coordinate GPS EXIF possono precompilare la
posizione.

Sostegni, commenti, stato e moderazione usano endpoint autenticati dove
necessario; cambi di stato, blocchi e azioni moderate scrivono il log previsto
dallo schema. La modalità demo usa uno store in memoria isolato per app/test.

Il pool MySQL viene creato solo quando la modalità database lo richiede. La
connessione richiede variabili DB e certificato CA; verifica certificato e
identità TLS. Nessuna migrazione viene eseguita all'avvio.

## Migrazione Aiven

`database/migrations/002_extend_existing_schema.sql` è una migrazione manuale
una tantum per lo schema iniziale fornito; non è idempotente. Il progetto non
ha verificato lo schema attualmente presente su Aiven. Prima di usare
`APP_MODE=database`, confrontare lo schema live con `database/schema/001_full_schema.sql`
e la migrazione, fare un backup e applicare solo le modifiche mancanti. Eseguire
anche `database/seeds/001_reference_data.sql` se mancano i dati di riferimento.
La migrazione `003_enforce_attachment_publication.sql` aggiunge i trigger che
vietano la pubblicazione senza allegato e la rimozione dell'ultimo allegato
pubblico; va applicata una volta dopo aver controllato i dati preesistenti.
Non eseguire la migrazione alla cieca su un database già aggiornato.

Impostare in locale `APP_MODE`, `SECRET_KEY`, `DB_HOST`, `DB_PORT`, `DB_NAME`,
`DB_USER`, `DB_PASSWORD`, `DB_SSL_CA_PATH` e, se serve, `UPLOAD_FOLDER`.
Credenziali e certificati restano fuori da Git. L'app usa per default la modalità
demo finché `APP_MODE=database` non è configurato.

## Limiti operativi

Gli upload locali sono adatti allo sviluppo; in produzione servono storage
durabile, backup e controlli antimalware. Il rate limiter usa memoria per
default e va configurato con storage condiviso su deployment multi-worker.
Il cookie firmato non supporta revoca centralizzata immediata; per quella
funzione serve uno store sessioni server-side. Email verification, recupero
password e integrazioni SPID/CIE non sono incluse.
