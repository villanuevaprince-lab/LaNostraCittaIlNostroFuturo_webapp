# La Nostra Città, Il Nostro Futuro

Webapp Flask per segnalazioni e proposte civiche. Il backend espone API JSON;
il frontend usa HTML, CSS responsive e moduli JavaScript vanilla. Il progetto
legge e scrive esclusivamente MySQL 8 su Aiven. Account, segnalazioni,
commenti e sostegni sono salvati nel database.

## Funzioni

- Registrazione e login con password Argon2id; gli hash scrypt/PBKDF2/Argon2
  preesistenti vengono verificati e aggiornati al login.
- Cookie di sessione HttpOnly, SameSite=Lax, CSRF per le richieste mutative e
  limiti per login/registrazione.
- Bacheca con ricerca per testo, quartiere, categorie multiple (almeno una
  corrispondente) e stato; le categorie appaiono come tag sulle schede.
- Profilo con bio, quartiere di interesse, preferenza notifiche, avatar e cambio
  password verificato; modifica password invalida le altre sessioni.
- Pagina dedicata con mappa Leaflet, ricerca indirizzo su richiesta, pin
  trascinabile, selezione di 1–5 categorie, coordinate e indirizzo salvati in
  MySQL; foto/video obbligatorio.
  I nuovi contenuti attendono approvazione e sono visibili subito all'autore.
- Validazione upload JPEG/PNG/WebP/MP4/WebM fino a 20 MB. Le immagini sono
  verificate con Pillow e risalvate senza metadati EXIF; non si estraggono
  coordinate GPS.
- Commenti pubblici visibili anche agli ospiti; pubblicazione e sostegno
  richiedono account e CSRF. I sostegni ripetuti sono idempotenti.
- Coda moderazione a paginazione keyset, selezione di tutte le righe caricate
  (massimo 50 per operazione), cambio di stato, azioni individuali o batch;
  tabella utenti ricercabile con email e tipo di blocco. Ban senza scadenza,
  blocchi temporanei e revoche sono registrati negli eventi di audit.
- Scheda dettaglio con posizione su mappa e ritiro autonomo dalla dashboard.
- Storico stato, evento di invio e allegato salvati nella stessa
  transazione MySQL della segnalazione. La pubblicazione avviene dopo la revisione;
  i trigger impediscono la pubblicazione senza allegato e la rimozione
  dell'ultimo allegato di una segnalazione pubblica.

## Struttura

| Percorso | Contenuto |
| --- | --- |
| `backend/app.py` | Application factory Flask, configurazione, errori e middleware |
| `backend/api/` | API JSON per autenticazione e cataloghi |
| `backend/auth.py`, `backend/security.py` | Form web, sessioni, CSRF, hash e ruoli |
| `backend/repositories/` | Query SQL parametrizzate per cataloghi e segnalazioni |
| `backend/services/` | Regole di pubblicazione e validazione/salvataggio allegati |
| `backend/reports.py`, `backend/pages.py` | Blueprint per API segnalazioni e pagine |
| `frontend/templates/` | Pagine HTML accessibili servite da Flask |
| `frontend/static/` | CSS e moduli ES vanilla |
| `database/` | Schema completo, estensione del DB esistente e seed di riferimento |
| `backend/tests/` | Test con Flask test client e connessione MySQL simulata |

## Avvio locale

Richiesti Python 3.11 o superiore e pip.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cp .env.example .env
# Compila .env con SECRET_KEY, DB_HOST, DB_PORT, DB_USER e DB_PASSWORD;
# copia il certificato CA Aiven in certificates/ca.pem.
python -m backend.app
```

Su Windows PowerShell attiva l'ambiente con `.venv\Scripts\Activate.ps1`, copia
`.env.example` in `.env` con `Copy-Item .env.example .env` e avvia sempre dalla
radice con `python -m backend.app` (non `python backend/app.py`). Apri
<http://localhost:3000>; `GET /api/health` restituisce `ok` solo se la
connessione MySQL è effettiva. Senza credenziali o certificato CA le API che
richiedono il database rispondono `503`; non vengono mostrati dati fittizi.
Rimuovi `APP_MODE=demo` da eventuali vecchi `.env`: non è più supportato.

## Configurazione MySQL Aiven esistente

1. Crea `.env` copiando `.env.example`; `.env` è escluso da Git.
2. Imposta una `SECRET_KEY` casuale di almeno 32 caratteri,
   i parametri `DB_*` e `DB_SSL_CA_PATH`. Inserisci localmente le credenziali.
3. Verifica lo schema reale e crea un backup prima di qualsiasi DDL.
4. Se il DB contiene solo lo schema iniziale, applica **una sola volta**
   `database/migrations/002_extend_existing_schema.sql`; poi applica
   `database/seeds/001_reference_data.sql`. Le migrazioni non sono idempotenti.
   Controlla eventuali segnalazioni già pubbliche senza allegato:

   ```sql
   SELECT s.IdSegnalazione FROM SEGNALAZIONE s
   LEFT JOIN ALLEGATO a ON a.IdSegnalazione = s.IdSegnalazione
   WHERE s.Visibilita = 'pubblica'
   GROUP BY s.IdSegnalazione HAVING COUNT(a.IdAllegato) = 0;
   ```

   Risolvi i casi trovati e applica **una sola volta**
   `database/migrations/003_enforce_attachment_publication.sql` tramite il
   client `mysql` (lo script usa `DELIMITER`).
5. Se quartieri, stati, categorie, storico, allegati estesi e tabelle ponte sono
   già presenti, non rilanciare la migrazione 002: confronta lo schema e, se
   serve, esegui il seed idempotente e la migrazione 003 solo se mancano i trigger.
   Il seed aggiunge gli 88 NIL del Comune di
   Milano e rende inattivi i nove raggruppamenti generici del vecchio seed,
   senza cancellare righe o alterare i riferimenti delle segnalazioni esistenti.
6. Per questa versione, dopo un backup, applica **una sola volta**
   `database/migrations/004_civic_features.sql` su Aiven. Aggiunge Bio,
   NotificheEmail, AvatarRiferimento, SessionVersion e un indice sulla coda.
   L'app non la esegue automaticamente: avvia il nuovo codice solo dopo la
   migrazione. Verifica prima che tali colonne/indice non esistano già.
6. Avvia l'app. La connessione richiede il certificato CA e verifica certificato
   e hostname TLS. L'app non esegue migrazioni automatiche.

Le funzioni di selezione multipla, tag e ban permanente usano le tabelle
`SEGNALAZIONE_CATEGORIA` e `BLOCCO` già presenti: non serve una nuova
migrazione oltre alla 004 per questa modifica.

Gli 88 NIL provengono dal dataset pubblico DS964 del Comune di Milano:
<https://dati.comune.milano.it/dataset/e8e765fc-d882-40b8-95d8-16ff3d39eb7c>.
Non mettere password, certificato CA o `.env` nel repository; il seed SQL si
applica manualmente al tuo database, preferibilmente dopo un backup.
Se una password Aiven è già stata inserita in un commit pubblico, cambiala
su Aiven: sostituire il valore nel file corrente non la rimuove dalla cronologia
Git. Aggiorna quindi soltanto il tuo `.env` locale con la nuova password.

`database/schema/001_full_schema.sql` serve a creare un **database nuovo** e
non deve essere eseguito sopra il DB Aiven popolato. Gli utenti del seed con
`HASH_DEMO_NON_VALIDO_*` non possono effettuare il login: registra un account
con una nuova email. Per abilitare un moderatore, un amministratore DB deve
aggiungere l'utente alla tabella `MODERATORE` dopo aver verificato l'ID.

I file sono conservati in `storage/uploads/` rispetto alla radice del progetto,
indipendentemente dalla directory di avvio, ed esclusi da Git. Per conservare
anche foto e video dopo riavvii o nuove installazioni, configura `UPLOAD_FOLDER`
su un volume persistente con backup. MySQL conserva i riferimenti ai file,
non i byte degli allegati. Non condividere la cartella con altri servizi.
Una futura migrazione a object storage deve mantenere i controlli MIME,
dimensione, nomi casuali e autorizzazione alla lettura.

## API principali

Le richieste che modificano dati richiedono il token CSRF nell'header
`X-CSRFToken`, disponibile nel meta `csrf-token` delle pagine.

| Metodo e percorso | Accesso | Uso |
| --- | --- | --- |
| `POST /api/auth/register` | Pubblico | Registrazione JSON e sessione |
| `POST /api/auth/login` | Pubblico | Accesso JSON |
| `POST /api/auth/logout` | Sessione | Uscita |
| `GET/PATCH/DELETE /api/auth/me` | Sessione | Profilo e cancellazione logica |
| `POST /api/auth/me/password`, `POST /api/auth/me/avatar` | Sessione | Password e immagine profilo |
| `GET /api/geo/search`, `GET /api/geo/reverse` | Sessione | Geocodifica di Milano su richiesta |
| `GET /api/quartieri`, `GET /api/categorie` | Pubblico | Cataloghi attivi |
| `GET /api/segnalazioni` | Pubblico | Ricerca, filtri; `categoria` ripetibile; `?mie=1` richiede login |
| `POST /api/segnalazioni` | Sessione | `multipart/form-data`, 1–5 `categoria_ids`, allegato obbligatorio |
| `GET /api/segnalazioni/<id>` | Pubblico | Dettaglio e commenti |
| `DELETE /api/segnalazioni/<id>` | Autore | Ritiro logico del contenuto |
| `POST /api/segnalazioni/<id>/commenti` | Sessione | Pubblica un commento |
| `GET/PUT/DELETE /api/segnalazioni/<id>/sostegno` | Sessione | Legge, esprime o ritira sostegno (richieste ripetute idempotenti) |
| `GET /api/allegati/<id>` | Pubblico se segnalazione pubblica | Scarica allegato controllato |
| `PATCH /api/segnalazioni/<id>/stato` | Moderatore | Transizione di stato e storico |
| `/api/moderazione/*` | Moderatore | Coda, azioni batch, ricerca utenti e blocchi permanenti/temporanei |

La documentazione dettagliata è in [`docs/api.md`](docs/api.md) e
[`docs/architettura.md`](docs/architettura.md).
Per la procedura completa di installazione e configurazione Aiven consulta
[`docs/configurazione.md`](docs/configurazione.md).

## Test

```bash
python -m pytest -q
```

I test non si collegano ad Aiven: simulano l'accesso al database e bloccano
le connessioni di rete. Dopo i test automatici, verifica la configurazione DB
su un ambiente di test o in una finestra controllata.

## Produzione

Usa HTTPS, server WSGI, `SESSION_COOKIE_SECURE=true`, `FLASK_DEBUG=0`, segreti
persistenti e storage rate-limit condiviso (ad esempio Redis, con il relativo
extra `Flask-Limiter`). `memory://` è adatto solo a sviluppo o test. Prevedi
backup DB, retention degli allegati, scansione malware e monitoraggio. L'analisi
IA non prende decisioni automatiche: i risultati devono restare soggetti a
revisione umana.

La ricerca usa Nominatim pubblico solo dopo il click dell'utente (mai
autocomplete), con limite globale configurato nello storage rate-limit e cache
di processo. Mostra attribuzione OpenStreetMap. Per volumi elevati usa un
geocoder/servizio tile dedicato o self-hosted e una cache condivisa, rispettando
le condizioni del fornitore. La preferenza notifiche è salvata, ma non invia
email finché non è integrato un servizio di consegna.
