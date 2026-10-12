# La Nostra Città, Il Nostro Futuro

Webapp Flask per segnalazioni e proposte civiche. Il backend espone API JSON;
il frontend usa HTML, CSS responsive e moduli JavaScript vanilla. Il progetto
usa MySQL 8 quando configurato e include una modalità demo in memoria.

## Funzioni

- Registrazione e login con password Argon2id; gli hash scrypt/PBKDF2/Argon2
  preesistenti vengono verificati e aggiornati al login.
- Cookie di sessione HttpOnly, SameSite=Lax, CSRF per le richieste mutative e
  limiti per login/registrazione.
- Bacheca con ricerca per testo, quartiere, categoria e stato.
- Pagina profilo con modifica dei dati e cancellazione logica dell'account.
- Pagina dedicata per nuove segnalazioni: quartiere, una o più categorie,
  posizione, foto/video obbligatorio e descrizione accessibile.
- Validazione upload JPEG/PNG/WebP/MP4/WebM fino a 20 MB. Le immagini sono
  verificate con Pillow, le coordinate EXIF valide possono compilare la
  posizione e l'immagine viene risalvata senza metadati EXIF.
- Commenti e sostegni con controllo account e CSRF.
- Area moderazione protetta da ruolo DB: stato e visibilità dei contenuti,
  rimozione commenti e blocco/sblocco account con eventi di audit.
- Storico stato, evento di pubblicazione e allegato salvati nella stessa
  transazione MySQL della segnalazione.

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
| `backend/tests/` | Test con Flask test client e connessione MySQL vietata |

## Avvio demo

Richiesti Python 3.11 o superiore e pip.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python -m backend.app
```

Su Windows PowerShell attiva l'ambiente con `.venv\Scripts\Activate.ps1`.
Apri <http://localhost:5000>. La demo non contiene account predefiniti: crea
un account dalla pagina di registrazione. Gli utenti e i contenuti demo sono
in memoria e scompaiono al riavvio. Non usare la demo come deployment.

## Configurazione MySQL Aiven esistente

1. Crea `.env` copiando `.env.example`; `.env` è escluso da Git.
2. Imposta `APP_MODE=database`, una `SECRET_KEY` casuale di almeno 32 caratteri,
   i parametri `DB_*` e `DB_SSL_CA_PATH`. Inserisci localmente le credenziali.
3. Verifica lo schema reale e crea un backup prima di qualsiasi DDL.
4. Se il DB contiene solo lo schema iniziale, applica **una sola volta**
   `database/migrations/002_extend_existing_schema.sql`; poi applica
   `database/seeds/001_reference_data.sql`. La migrazione non è idempotente.
5. Se quartieri, stati, categorie, storico, allegati estesi e tabelle ponte sono
   già presenti, non rilanciare la migrazione: confronta lo schema e, se serve,
   esegui solo il seed idempotente.
6. Avvia l'app. La connessione richiede il certificato CA e verifica certificato
   e hostname TLS. L'app non esegue migrazioni automatiche.

`database/schema/001_full_schema.sql` serve a creare un **database nuovo** e
non deve essere eseguito sopra il DB Aiven popolato. Gli utenti del seed con
`HASH_DEMO_NON_VALIDO_*` non possono effettuare il login: registra un account
con una nuova email. Per abilitare un moderatore, un amministratore DB deve
aggiungere l'utente alla tabella `MODERATORE` dopo aver verificato l'ID.

I file sono conservati in `storage/uploads/`, escluso da Git. In produzione
monta un volume persistente e non condividere l'accesso alla cartella con altri
servizi. Una futura migrazione a object storage deve mantenere i controlli MIME,
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
| `GET /api/quartieri`, `GET /api/categorie` | Pubblico | Cataloghi attivi |
| `GET /api/segnalazioni` | Pubblico | Ricerca e filtri; `?mie=1` richiede login |
| `POST /api/segnalazioni` | Sessione | `multipart/form-data`, allegato obbligatorio |
| `GET /api/segnalazioni/<id>` | Pubblico | Dettaglio e commenti |
| `POST /api/segnalazioni/<id>/commenti` | Sessione | Pubblica un commento |
| `GET/PUT/DELETE /api/segnalazioni/<id>/sostegno` | Sessione | Legge, esprime o ritira sostegno |
| `GET /api/allegati/<id>` | Pubblico se segnalazione pubblica | Scarica allegato controllato |
| `PATCH /api/segnalazioni/<id>/stato` | Moderatore | Transizione di stato e storico |
| `/api/moderazione/*` | Moderatore | Visibilità, commenti e blocchi |

La documentazione dettagliata è in [`docs/api.md`](docs/api.md) e
[`docs/architettura.md`](docs/architettura.md).

## Test

```bash
python -m pytest -q
```

I test non si collegano ad Aiven: l'accesso al driver è sostituito da un errore
se un test tenta di aprire una connessione. Dopo i test automatici, verifica la
configurazione DB su un ambiente di test o in una finestra controllata.

## Produzione

Usa HTTPS, server WSGI, `SESSION_COOKIE_SECURE=true`, `FLASK_DEBUG=0`, segreti
persistenti e storage rate-limit condiviso (ad esempio Redis, con il relativo
extra `Flask-Limiter`). `memory://` è adatto solo a sviluppo o test. Prevedi
backup DB, retention degli allegati, scansione malware e monitoraggio. L'analisi
IA non prende decisioni automatiche: i risultati devono restare soggetti a
revisione umana.
