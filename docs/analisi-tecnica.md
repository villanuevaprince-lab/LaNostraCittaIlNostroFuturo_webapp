# Analisi tecnica — La Nostra Città, Il Nostro Futuro

La sezione 1 e la tabella della sezione 2 descrivono **lo stato iniziale prima
dell'implementazione**. Lo stato corrente è riepilogato nelle sezioni 8 e 9.
Analisi statica del repository disponibile il 12 ottobre 2026. Non sono state
usate credenziali né aperte connessioni verso Aiven. Il file
`analisi_requisiti_esercizio_1.md` citato nel prompt non è presente; per i
requisiti funzionali ho usato `requisiti_la_nostra_citta_il_nostro_futuro.md`.

## 1. Stato attuale del progetto

### Struttura e tecnologie

Il progetto versionato è organizzato in `backend/`, `frontend/`, `database/`,
`docs/`, `certificates/` e `storage/`. Sono presenti anche directory locali
ignorate (`node_modules/`, `client/`, `server/`) senza sorgenti applicativi
tracciati. Non risultano `package.json`, lockfile JavaScript o codice Node
versionato: l'app corrente è Python/Flask.

| Area | Stato osservato |
| --- | --- |
| Backend | Python, Flask application factory in `backend/app.py`; blueprint per auth, pagine e segnalazioni |
| Frontend | Template Jinja serviti da Flask, CSS e JavaScript vanilla in `frontend/static/` |
| Database | MySQL Connector/Python; Aiven configurabile tramite variabili d'ambiente e CA TLS |
| Dipendenze | `backend/requirements.txt`, versioni con intervalli, non pin esatti |
| Avvio | `python -m venv .venv`, installazione requirements, `python -m backend.app` |
| Test | Pytest e Flask test client in `backend/tests/`; query DB verificate con connessioni simulate |
| Configurazione | `.env` escluso da Git; `.env.example` contiene host, porta e utente DB più password segnaposto |
| File caricati | `storage/uploads/.gitkeep`; nessuna funzione upload implementata |

Funzioni attualmente implementate: bacheca pubblica con ricerca, registrazione,
login/logout, sessione Flask firmata, form dedicato per creare segnalazioni o
proposte e API JSON per consultazione e creazione. Le funzioni DB effettivamente
usate sono lettura e inserimento su `UTENTE`, `SEGNALAZIONE` e conteggio dei
`SOSTEGNI` attivi.

Mancano le API e le pagine per quartieri, categorie, allegati, sostegni,
commenti, profilo, moderazione e transizioni di stato. Non è attiva una gestione
di ruoli lato backend. L'API non copre ancora tutti i domini e alcune pagine
inviano form HTML tradizionali invece di chiamare esclusivamente API JSON.

### Configurazione e sicurezza osservabili

`.gitignore` esclude `.env`, `.venv/`, cache, `node_modules/`, upload e certificati.
Non è presente un `.env` locale nel workspace. `.env.example` ha password
segnaposto, nessuna password reale è stata letta o usata in questa analisi.
La connessione MySQL verifica CA e identità TLS; le query viste sono
parametrizzate. I cookie sono HttpOnly e SameSite=Lax; `Secure` è configurabile.
Flask-WTF protegge i POST HTML e JSON. Limiti di login e registrazione usano
Flask-Limiter, che per impostazione di sviluppo usa storage in memoria.

Limiti tecnici riscontrati: i nuovi account generano hash scrypt, non Argon2id
come prescritto; la dipendenza Argon2 è usata per verificare hash legacy. La
connessione apre un collegamento per operazione e non usa un pool. La sessione è
nel cookie firmato, quindi non è revocabile centralmente prima della scadenza.
`/api/health` descrive solo la modalità configurata e non verifica la
connettività del database.

## 2. Conformità ai requisiti

Legenda: ✓ presente; ~ parziale; — assente.

| ID | Requisito | Presente | Parzialmente presente | Assente | File coinvolti | Problema | Soluzione proposta | Priorità |
| --- | --- | :---: | :---: | :---: | --- | --- | --- | --- |
| R01 | Bacheca pubblica e ricerca | ✓ |  |  | `backend/pages.py`, `backend/reports.py`, `backend/database.py`, `frontend/` | Ricerca testuale semplice; nessun filtro per stato, zona o categoria | Aggiungere filtri API paginati e filtri UI | media |
| R02 | Registrazione e accesso | ✓ |  |  | `backend/auth.py`, `backend/users.py`, `backend/forms.py` | Registrazione email/password, senza verifica email o recupero password | Conservare auth e pianificare i flussi account mancanti | media |
| R03 | Hash password Argon2id |  | ✓ |  | `backend/auth.py`, `backend/security.py`, `backend/requirements.txt` | Nuovi hash scrypt; Argon2 usato solo per compatibilità legacy | Usare esplicitamente Argon2id e testare migrazione al login | alta |
| R04 | Sessione sicura e CSRF | ✓ |  |  | `backend/app.py`, `backend/security.py`, `backend/tests/` | Cookie firmato client-side, senza revoca centrale | Mantenere CSRF; usare session store server-side se serve revoca globale | alta |
| R05 | Ruoli e permessi moderatore |  | ✓ |  | `database/schema/001_full_schema.sql`, `backend/security.py` | Tabella `MODERATORE` esiste, ma non ci sono decoratore `role_required` o API protette per ruolo | Implementare controllo ruoli e verifiche backend | alta |
| R06 | Pagina personale, modifica e cancellazione account |  |  | ✓ | `backend/`, `frontend/templates/` | Non implementate | Aggiungere API e pagine profilo, con cancellazione logica | media |
| R07 | Quartieri e appartenenza utenti |  | ✓ |  | `database/schema/001_full_schema.sql`, migrazione | Tabelle/relazioni previste nel nuovo schema ma nessuna API/UI; nel DB esistente dipende dalla migrazione | Migrazione verificata e CRUD/API quartieri e profilo | alta |
| R08 | Creazione segnalazione in pagina dedicata | ✓ |  |  | `backend/reports.py`, `frontend/templates/report_new.html` | La pagina non raccoglie quartiere, categorie, coordinate o allegati | Estendere il flusso dopo aver attivato API e schema necessari | alta |
| R09 | Allegato foto/video obbligatorio alla pubblicazione |  |  | ✓ | `database/schema/001_full_schema.sql`, `backend/reports.py`, `frontend/` | Nessun upload; una segnalazione viene pubblicata senza allegato | Implementare upload multipart, validazione Pillow e associazione transazionale | critica |
| R10 | Verifica MIME, dimensione, nome/path sicuro ed EXIF |  |  | ✓ | `backend/`, `storage/uploads/` | Nessuna pipeline upload | Limite byte, MIME reale, nome casuale, EXIF controllato/rimosso e cleanup su rollback | critica |
| R11 | Categorie e relazione molti-a-molti |  | ✓ |  | schema, migrazione, seed | Tabelle previste e categorie seminate; mancano API, UI e associazioni nel form | API categorie e associazione parametrizzata alla segnalazione | alta |
| R12 | Sostegno e prevenzione duplicati |  | ✓ |  | schema, migrazione, `backend/database.py` | Vincolo UNIQUE presente; conta sostegni esistenti, ma manca endpoint per aggiungere/ritirare | Endpoint auth con transazione e gestione conflitto UNIQUE | alta |
| R13 | Commenti |  | ✓ |  | schema, `backend/` | Tabella presente nel modello, nessuna API o UI | CRUD minimo con moderazione e CSRF | media |
| R14 | Stato corrente e ciclo di vita |  | ✓ |  | `SEGNALAZIONE`, `STATO_SEGNALAZIONE`, migrazione | Stato in tabella e dizionario stati predisposti; assenti API di modifica e regole transizioni | Servizio transizioni con autorizzazione e audit | alta |
| R15 | Storico degli stati |  | ✓ |  | `STORICO_STATO`, migrazione | Tabella progettata ma nessuna scrittura automatica o consultazione | Registrare stato precedente/successivo nella stessa transazione | alta |
| R16 | Moderazione, blocco e sospensione |  | ✓ |  | `MODERATORE`, `BLOCCO`, `EVENTO_LOG` | Schema disponibile, azioni e autorizzazioni non implementate | API moderate protette per ruolo e log transazionale | alta |
| R17 | Tracciamento eventi |  | ✓ |  | `EVENTO_LOG`, `VARIAZIONE_LOG` | Tabelle previste, l'app non registra operazioni | Service layer che scrive evento e variazioni in transazione | media |
| R18 | Localizzazione e mappa |  | ✓ |  | `SEGNALAZIONE` | Campi coordinate/indirizzo e indici esistono; form e mappa assenti | Validazione coordinate e UI mappa accessibile | media |
| R19 | Predisposizione analisi IA |  | ✓ |  | `ANALISI_IA`, migrazione | Tabella JSON predisposta, nessuna coda, worker o revisione moderatore | Tenere elaborazione asincrona separata e risultati revisionabili | bassa |
| R20 | Accessibilità e uso responsive |  | ✓ |  | `frontend/templates/`, CSS, JS | Etichette/ARIA e layout responsive presenti; lettura vocale non verificata e non va confusa con uno screen reader | Audit WCAG manuale/automatico; semantica e tastiera | media |
| R21 | API JSON sotto `/api` per tutti i domini |  | ✓ |  | `backend/reports.py`, `backend/pages.py`, `docs/api.md` | Solo health e due endpoint segnalazioni; form web con POST HTML | Espandere API per dominio; JS usa fetch e template solo struttura | alta |
| R22 | Livelli route → service → repository |  | ✓ |  | `backend/` | DB in `database.py`, logica direttamente nelle route; repository non separati | Estrarre servizi e repository per i casi d'uso aggiunti | media |
| R23 | Connessioni in pool |  |  | ✓ | `backend/database.py`, requirements | Una connessione per operazione | Valutare pool del driver/configurazione e limiti Aiven | media |
| R24 | Rate limiting condiviso |  | ✓ |  | `backend/app.py`, requirements, `.env.example` | Configurabile, ma default `memory://` non è condiviso tra worker | Configurare Redis o storage condiviso in produzione | alta |
| R25 | Versioni dipendenze fissate |  | ✓ |  | `backend/requirements.txt` | Intervalli di versione, senza lock riproducibile | Pin compatibili e testati; mantenere aggiornamento controllato | media |
| R26 | Test pytest con DB di test separato |  | ✓ |  | `backend/tests/` | Test applicativi e SQL simulato; nessun MySQL di test end-to-end | Aggiungere test d'integrazione opzionale su database isolato | media |
| R27 | `.env`, upload e segreti esclusi da Git | ✓ |  |  | `.gitignore`, `.env.example` | Configurazione attuale usa segnaposto e ignore corretti | Mantenere i controlli; credenziali inserite localmente dall'utente | alta |
| R28 | Errori coerenti JSON e protezione stack trace |  | ✓ |  | `backend/app.py`, `backend/reports.py` | Error handler JSON per `/api` e HTML per pagine; copertura API parziale | Standardizzare errori e codici per tutte le API | media |

## 3. Analisi del database

Sono presenti tre artefatti SQL distinti:

- `database/schema/001_full_schema.sql`: schema completo per una nuova
  installazione; database `nostra_citta`, `utf8mb4_unicode_ci`, tabelle InnoDB.
- `database/migrations/002_extend_existing_schema.sql`: aggiunge al modello
  iniziale quartieri, stati, categorie, colonne, indici e nuove tabelle.
- `database/seeds/001_reference_data.sql`: valori di stato, categorie e nove
  quartieri, con upsert sulle chiavi uniche.

Lo schema completo contiene `UTENTE`, `MODERATORE`, `SEGNALAZIONE`, `ALLEGATO`,
`SEGNALAZIONE_CATEGORIA`, `COMMENTO`, `SOSTEGNO`, `QUARTIERE`,
`STATO_SEGNALAZIONE`, `STORICO_STATO`, `ANALISI_IA`, `VERIFICA_IDENTITA`,
`BLOCCO`, `EVENTO_LOG`, `VARIAZIONE_LOG` e `SESSIONE_WEB`, oltre alla vista
`V_CLASSIFICA_SEGNALAZIONI`.

Le PK sono interi unsigned auto-incrementali per le entità; codici per gli
stati; chiave composta `(IdSegnalazione, IdCategoria)` per la tabella ponte e
`(IdEvento, NomeCampo)` per le variazioni. Email, nomi di quartiere/categoria,
riferimento file e coppia utente/segnalazione hanno vincoli unici. Le FK
modellano autore, quartiere, stato, moderatore, allegati, categorie, sostegni,
commenti, storico, analisi e log. I sostegni duplicati sono impediti dal DB.

Il modello è relazionale e le associazioni N:M hanno tabelle ponte, quindi è
compatibile con la normalizzazione fino alla 3NF per le dipendenze rappresentate.
Sono presenti indici per bacheca, autore, quartiere, coordinate, commenti,
sostegni, log e revisioni IA; ricerca titolo/descrizione usa FULLTEXT. Coordinate
DECIMAL hanno check sui limiti geografici; confidenza IA è DECIMAL(5,4) con
check 0–1; risultati IA sono JSON.

Limiti e rischi da risolvere prima dell'implementazione DB:

1. La migrazione è una tantum e non idempotente: usa `CREATE TABLE` e `ALTER`
   senza guardie di versione. Non rilanciarla alla cieca su Aiven.
2. La migrazione presuppone il vecchio schema iniziale e l'insieme di valori già
   presenti in `SEGNALAZIONE.Stato`; i dati effettivi su Aiven non sono stati
   interrogati, quindi FK e CHECK vanno verificati con una copia/backup.
3. Non risultano trigger né uso di `SIGNAL SQLSTATE`; le regole non rappresentate
   da CHECK/FK (almeno un allegato prima della pubblicazione, coerenza tra
   allegato e segnalazione, transizioni di stato) richiedono transazioni,
   procedure/trigger deliberati o servizi applicativi.
4. `STORICO_STATO.IdAutoreModifica` è obbligatorio anche per cambi automatici;
   va chiarita la rappresentazione degli eventi di sistema.
5. `ANALISI_IA.IdAllegato` non garantisce da sola che l'allegato appartenga alla
   stessa segnalazione indicata in `IdSegnalazione`; serve vincolo composito o
   validazione applicativa.
6. `SESSIONE_WEB` è presente nello schema, ma Flask usa attualmente il cookie
   firmato predefinito e non questa tabella.

Lo script completo è per installazioni nuove; per il database Aiven esistente
si deve identificare lo schema effettivo e costruire/verificare migrazioni
incrementali con backup. La modalità database attuale, tuttavia, usa soltanto
le colonne originarie necessarie a login, bacheca e creazione base.

## 4. Stack e scelte tecniche

| Area | Scelta concreta | Motivazione / adeguamento necessario |
| --- | --- | --- |
| Backend | Flask application factory e Blueprint, Python 3.11+ | Già presente; aggiungere blueprint per domini solo quando implementati |
| Frontend | HTML5, CSS responsive, moduli ES vanilla | Già presente; spostare la logica delle azioni sui moduli `fetch` e mantenere i template senza business logic |
| Database | MySQL 8, InnoDB, `utf8mb4`, MySQL Connector/Python | Driver già presente; query parametrizzate; valutare un pool esplicito |
| Autenticazione | Cookie Flask firmato, HttpOnly, SameSite=Lax, Secure in HTTPS | Già presente; per revoca globale valutare sessioni server-side; evitare JWT per il client web same-origin |
| Password | Argon2id tramite `argon2-cffi` | Dipendenza e verifica legacy già presenti; cambiare la generazione attuale scrypt dopo aver preservato compatibilità |
| CSRF | Flask-WTF `CSRFProtect` | Già presente sui POST; API mutative devono inviare token anche per PUT/PATCH/DELETE |
| Validazione | WTForms attuale; schemi/validatori riutilizzabili per API | Server resta autorità; risposte JSON uniformi da definire |
| Upload | Flask `request.files`, Pillow e storage locale di sviluppo | Non implementato; MIME reale, byte limit, nome casuale, EXIF, path confinato e cleanup transazionale |
| Configurazione | `python-dotenv`, `.env` locale, `.env.example` senza segreti | Già presente; l'utente inserirà localmente credenziali e CA Aiven |
| Rate limiting | Flask-Limiter con Redis condiviso in deployment | Presente ma default memoria è solo locale/singolo processo |
| Test | Pytest, Flask test client, mock DB unitari e MySQL isolato per integrazione | Test unitari presenti; nello runtime attuale `pytest` non è installato, quindi non è stato possibile rieseguirli in questa analisi |
| API per futuro client | REST JSON same-origin, route/service/repository separati | Non serve creare ora app mobile/desktop; documentare contratti API |

Non si propone SQLAlchemy: lo schema esistente è già SQL, le query sono poche e
MySQL Connector/Python è già in uso. Un ORM non è necessario per risolvere i
problemi identificati; la separazione repository/service è più utile in questa
fase.

## 5. Architettura proposta

Per le prossime feature, mantenere factory e blueprint già avviati e separare
progressivamente controller, servizi e query.

```text
Browser (HTML / CSS / JavaScript)
  ↓ fetch JSON
Flask (Blueprint su /api)
  ↓
Middleware: autenticazione, ruoli, CSRF, validazione
  ↓
Route
  ↓
Service (logica di business)
  ↓
Repository (SQL parametrizzato)
  ↓
MySQL 8
```

Il flusso pagina attuale usa ancora POST HTML. L'obiettivo architetturale del
prompt richiede di migrare progressivamente queste azioni a fetch JSON, lasciando
nei template solo struttura, accessibilità e token CSRF.

```text
Browser (form multipart)
  ↓
Endpoint upload Flask
  ↓
Validazione file (dimensione, MIME reale, nome, path)
  ↓
Storage locale in uploads/ (sviluppo) o storage esterno (produzione)
  ↓
Metadati nella tabella allegato
```

```text
Segnalazione pubblicata
  ↓
Coda di elaborazione (job o task separato)
  ↓
Moderazione IA / classificazione / EXIF / computer vision
  ↓
Risultati in analisi_ia
  ↓
Revisione del moderatore
```

## 6. Struttura di cartelle consigliata

Adattamento graduale alle directory esistenti, senza migrare o rinominare tutto
in un'unica modifica:

```text
project-root/
├── backend/
│   ├── app.py                 # create_app e configurazione
│   ├── auth.py                # blueprint auth attuale
│   ├── security.py            # sessioni, CSRF, login_required, role_required
│   ├── routes/                # blueprint API per utenti, report, categorie, ecc.
│   ├── services/              # casi d'uso e transazioni
│   ├── repositories/          # SQL parametrizzato
│   ├── validators/            # schemi per API e upload
│   └── tests/
├── frontend/
│   ├── templates/             # struttura HTML accessibile
│   └── static/
│       ├── css/
│       ├── js/                 # api.js e moduli per pagina
│       └── img/
├── database/
│   ├── schema/
│   ├── migrations/
│   └── seeds/
├── docs/
├── storage/uploads/            # escluso da Git
├── certificates/               # CA locale esclusa da Git
├── .env.example
├── .gitignore
└── README.md
```

## 7. Piano di implementazione

Le fasi seguenti richiedono conferma prima di modificare il codice applicativo.

| Fase | File / aree | Funzionalità | Dipendenze | Rischi | Criterio di completamento |
| --- | --- | --- | --- | --- | --- |
| 1. Contratto DB e migrazione | `database/migrations/`, docs | Confronto schema live esportato (fornito dall'utente, senza password) con baseline; migrazione incrementale versionata | MySQL 8 di test | DDL irreversibile o dati esistenti incompatibili | Migrazione provata su copia e rollback/backup documentato |
| 2. Ambiente e dipendenze | `backend/requirements.txt`, README | Versioni pin, istruzioni venv riproducibili | Python 3.11+ | Pin incompatibili col runtime | Installazione pulita e app avviabile |
| 3. Persistenza modulare | `backend/database.py`, nuovi repository e service | Pool, transazioni e query parametrizzate per domini | MySQL Connector/Python | Pool oltre limiti connessioni Aiven | Test isolati DB e parametri senza accesso live |
| 4. Autenticazione e ruoli | `backend/auth.py`, `security.py`, users | Argon2id per nuovi hash, compatibilità/rehash legacy, `role_required` | argon2-cffi, Flask-WTF | Bloccare account già esistenti o migrazione hash | Test login, ruoli, CSRF, blocco e account seed |
| 5. Quartieri e categorie | blueprint, service/repository, JS | API GET e gestione amministrativa; selezione in form | Schema e seed | Dati seed duplicati o nomi non coerenti | CRUD autorizzato e vincoli DB coperti |
| 6. Segnalazioni | `reports`, validators, templates/JS | API paginata/filtrata, quartiere, coordinate, categorie, stati iniziali | Fase 1 e 3 | Pubblicazione parziale | API coerenti e test di validazione/transazione |
| 7. Upload | nuovo modulo upload, `ALLEGATO`, CSS/JS | Foto/video, MIME reale, Pillow, EXIF, storage sicuro, allegato obbligatorio | Pillow e schema migrato | File malevoli, orphan file o path traversal | Rifiuto tipi invalidi, cleanup su rollback, pubblicazione senza allegato impossibile |
| 8. Sostegni e storico | API/service, repository, JS | Aggiunta/ritiro sostegno, ranking e transizioni auditabili | Schema | Concorrenza e stato incoerente | UNIQUE testato con richieste concorrenti e log atomico |
| 9. Commenti e moderazione | blueprint, ruoli, storico/log | Commenti, nascondi/rimuovi, blocco account, audit | Fase 4 e 8 | Privilegi insufficienti o azioni senza traccia | Test accesso ruolo e registrazione evento |
| 10. Frontend responsive | template e moduli ES | Pagine utenti, filtri, mappe e fetch JSON | API definite per dominio | Disallineamento contratti web/API | Flussi mobile/desktop con controlli accessibilità |
| 11. Validazione e test | `backend/tests/`, docs/API | Unit test, test client, integration test DB separato | MySQL di test facoltativo | Test che toccano Aiven per errore | Suite ripetibile e nessuna connessione reale nei test normali |
| 12. Documentazione e IA futura | README, docs, worker futuro | Endpoint, deployment, job asincroni e revisione umana IA | Fasi precedenti | IA usata come decisione automatica non revisionabile | Flusso IA isolato e revisione moderatore verificabile |

### Verifiche effettuate in questa analisi

- Requisiti: il file nominato nel prompt non esiste; letto quello disponibile
  `requisiti_la_nostra_citta_il_nostro_futuro.md`.
- Sorgenti, template, JS, CSS, test, schema, migrazione, seed, README,
  dipendenze e configurazione d'esempio ispezionati.
- Non è presente `.env`; non è stata tentata alcuna connessione al database.
- Il comando `python -m pytest -q` non è eseguibile in questo runtime perché
  `pytest` non è installato (`No module named pytest`). La suite va rieseguita
  dopo l'installazione delle dipendenze. L'esito di test riportato nel README
  deriva dalla verifica precedente e non è stato riconfermato ora.
- Nessuna modifica applicativa è stata fatta. Questo file è il solo artefatto
  di analisi previsto dal prompt.

## 8. Stato dopo l'implementazione autorizzata

La tabella sopra è una fotografia del repository prima dell'intervento e le
soluzioni proposte sono state implementate nel codice corrente. Ora il progetto
include auth Argon2id compatibile con hash precedenti, controlli di ruolo,
profilo e cancellazione logica, cataloghi quartiere/categoria, filtri bacheca,
form dedicato con allegato obbligatorio, commenti, sostegni, storico stato,
moderazione e audit tramite API e servizi/repository separati.

La migrazione per lo schema iniziale è documentata, ma non è stata eseguita né
verificata contro Aiven. Le credenziali DB non sono state richieste o lette.
La suite pytest non è stata eseguibile in questo ambiente: le dipendenze Flask,
MySQL e pytest non erano installate e l'accesso a PyPI è bloccato. Sono invece
stati eseguiti `python -m compileall -q backend`, `node --check` per i moduli JS
e `git diff --check`; tutti sono terminati correttamente.

## 9. Revisione del 12 ottobre: classifica e integrità degli allegati

Il file `analisi_requisiti_esercizio_1.md` resta assente dal repository; sono
stati confrontati il PDF dell'esercizio, il documento dei requisiti, gli script
SQL allegati (identici a quelli versionati) e il codice corrente. Lo stack
resta Flask, HTML/CSS/JavaScript vanilla e MySQL 8. La modalità demo è solo
per sviluppo e test; le credenziali MySQL non sono state configurate.

| Requisito | Esito della revisione | Intervento | Priorità residua |
| --- | --- | --- | --- |
| Classifica per sostegni | Vista SQL presente, bacheca senza ordinamento | `ordina=sostegni`, ordinamento SQL e demo, selettore UI | bassa |
| Sostegno unico attivo | UNIQUE sul DB, ma PUT ripetuto riscriveva la data e il log | Conflitto `409` per PUT ripetuto; riattivazione dopo ritiro | bassa |
| Allegato multimediale | Upload video ammesso, ma sempre renderizzato come immagine | MIME e descrizione nell'API, `<video>` con controlli | bassa |
| Allegato obbligatorio | Controllo applicativo, nessun vincolo DB alla pubblicazione | Inserimento in bozza, pubblicazione dopo upload e trigger MySQL | alta finché la migrazione 003 non è applicata |
| Privacy e accessibilità | EXIF rimosso dall'immagine; lettura vocale e mappa non presenti | Verifica UX/accessibilità e consenso alla posizione in una fase successiva | media |
| Moduli IA e SPID/CIE | Solo schema predisposto; integrazioni assenti | Richiedono servizi e flussi esterni dedicati | media |
| Test DB | Test unitari/demo e mock MySQL; nessun DB di test reale | Eseguire migrazioni e suite su MySQL 8 isolato | alta |

`003_enforce_attachment_publication.sql` è manuale e non idempotente: prima
occorre verificare gli allegati delle righe già pubbliche, fare un backup e
controllare che i quattro trigger non esistano. Non è stata aperta alcuna
connessione Aiven. Il database non è stato migrato in questa revisione.
