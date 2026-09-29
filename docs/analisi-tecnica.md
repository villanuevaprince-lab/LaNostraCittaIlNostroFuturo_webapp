# Analisi tecnica - La Nostra Città, Il Nostro Futuro

Data dell'analisi: 29 settembre 2026

Repository analizzato: `villanuevaprince-lab/LaNostraCittaIlNostroFuturo_webapp`

Branch: `main`
Database dichiarato: MySQL 8.0+ ospitato su Aiven

## Premessa e fonti

Questa analisi confronta lo stato reale del repository con:

- la consegna del progetto d'esame;
- il documento dei requisiti fornito separatamente;
- lo schema MySQL e i dati dimostrativi forniti in chat;
- l'informazione che il database esiste già su Aiven.

Il file richiesto `analisi_requisiti_esercizio_1.md` non è presente nel repository. Per questa fase sono quindi state usate le fonti esterne sopra elencate. Il database Aiven non è stato collegato né modificato: struttura e dati reali non sono verificabili finché non saranno disponibili, tramite variabili d'ambiente, host, porta, nome database, utente, password e certificato TLS richiesto da Aiven.

## 1. Stato attuale del repository

### Repository e Git

| Voce | Valore |
|---|---|
| Repository | `villanuevaprince-lab/LaNostraCittaIlNostroFuturo_webapp` |
| Visibilità | Pubblica |
| Branch corrente | `main` |
| Branch remoti | `origin/main` |
| Remote | `origin` -> repository GitHub indicato sopra |
| Working tree prima dell'analisi | Pulita |
| Ultimo commit | `b2acfd1` - `Initial commit` |
| Protezione di `main` | Non attiva |

### Struttura rilevata

```text
LaNostraCittaIlNostroFuturo_webapp/
└── README.md
```

Il `README.md` contiene soltanto il titolo del repository. Non sono presenti altre cartelle o file applicativi.

### Stack attuale

Non esiste ancora uno stack applicativo verificabile.

| Area | Stato attuale |
|---|---|
| Frontend | Assente |
| Backend | Assente |
| Linguaggi e framework | Non definiti |
| Build system | Assente |
| `package.json` e script npm | Assenti |
| Database nel repository | Assente; MySQL su Aiven dichiarato esternamente |
| Connessione database | Assente |
| Autenticazione | Assente |
| Gestione allegati | Assente |
| API REST | Assenti |
| Test | Assenti |
| Modalità di avvio | Non disponibile |

### Funzionalità implementate e mancanti

Non risultano funzionalità implementate. Mancano registrazione, autenticazione, ruoli, profili, quartieri, categorie, segnalazioni, allegati, commenti, sostegni, ricerca, filtri, classifica, moderazione, stati e storico, log, mappa, accessibilità, test e predisposizione IA.

### Problemi tecnici, di sicurezza e configurazione

- Non sono presenti `.gitignore`, `.env.example`, configurazione Node.js o istruzioni di avvio.
- Non esiste alcun codice da sottoporre a verifica per SQL injection, autorizzazioni, CORS, rate limiting o upload.
- Non sono presenti segreti nel repository analizzato.
- Il branch `main` non è protetto: durante lo sviluppo è consigliato lavorare su branch dedicati e integrare tramite pull request.
- La presenza del database remoto non basta per avviare il progetto: serve una configurazione Aiven esterna al codice e protetta da `.gitignore`.
- Il repository non contiene lo script SQL ufficiale, migrazioni o un meccanismo per verificare l'allineamento tra schema Aiven e applicazione.

## 2. Conformità ai requisiti

| ID | Requisito | Stato | File coinvolti | Problema | Soluzione | Priorità |
|---|---|---|---|---|---|---|
| R01 | Descrizione generale e obiettivi | Parzialmente presente | `README.md` | È presente solo il nome del progetto | Ampliare il README con obiettivi, stack e avvio | Media |
| R02 | Registrazione con dati identificativi | Assente | Nessuno | Nessun endpoint o form | API di registrazione, validazione e form accessibile | Critica |
| R03 | Autenticazione email/password | Assente | Nessuno | Nessuna gestione credenziali o sessione | Password Argon2id e sessione sicura via cookie | Critica |
| R04 | Profilo utente modificabile e cancellazione logica | Assente | Nessuno | Nessuna pagina o API profilo | Endpoint `me`, modifica dati e cancellazione logica | Alta |
| R05 | Ruolo moderatore/comitato | Assente | Nessuno | Nessun RBAC | Middleware di ruolo e permessi server-side | Critica |
| R06 | Quartiere dell'utente | Assente | Nessuno | Manca nel repository e nello schema SQL fornito | Tabelle `QUARTIERE` e relazione utente-quartiere | Alta |
| R07 | Creazione di segnalazioni e proposte | Assente | Nessuno | Nessuna API o interfaccia | CRUD controllato con transazione | Critica |
| R08 | Allegato foto/video obbligatorio | Assente | Nessuno | Lo schema fornito non garantisce almeno un allegato | Creazione in transazione e pubblicazione solo dopo upload valido | Critica |
| R09 | Categorie multiple | Assente | Nessuno | Mancano `CATEGORIA` e tabella ponte | Aggiungere categorie e `SEGNALAZIONE_CATEGORIA` | Alta |
| R10 | Ricerca e filtri | Assente | Nessuno | Nessuna homepage o query | Filtri parametrizzati per testo, tipo, stato, quartiere e categoria | Alta |
| R11 | Sostegno univoco | Assente nell'app; presente nello schema fornito | Nessuno | Nessun endpoint; il vincolo DB non è nel repository | API idempotente mantenendo `UNIQUE (IdUtente, IdSegnalazione)` | Alta |
| R12 | Classifica delle priorità | Assente | Nessuno | Nessuna query aggregata | Query per sostegni attivi, ordinamento e paginazione | Alta |
| R13 | Commenti | Assente nell'app; presente nello schema fornito | Nessuno | Nessuna API o moderazione | API commenti con autenticazione e visibilità | Media |
| R14 | Ciclo di vita della segnalazione | Assente nell'app; parziale nello schema fornito | Nessuno | Stato libero in `VARCHAR`, senza storico dedicato | Tabella stati, transizioni ammesse e storico atomico | Critica |
| R15 | Moderazione di segnalazioni e commenti | Assente | Nessuno | Nessun endpoint protetto | API moderatore, cancellazione logica e audit | Alta |
| R16 | Blocco e sospensione utenti | Assente nell'app; presente nello schema fornito | Nessuno | Nessun controllo del blocco a ogni richiesta | Middleware account e gestione revoca/scadenza | Critica |
| R17 | Tracciabilità e log | Assente nell'app; parziale nello schema fornito | Nessuno | Nessun servizio applicativo scrive i log | Audit service e transazioni insieme all'azione principale | Alta |
| R18 | Coordinate e mappa | Assente nell'app; coordinate nello schema fornito | Nessuno | Nessuna validazione né interfaccia mappa | Lat/lon validate, indici adeguati e Leaflet/OpenStreetMap | Alta |
| R19 | Estrazione EXIF | Assente | Nessuno | Nessuna pipeline di metadati | Job asincrono, consenso e rimozione metadati sensibili | Media |
| R20 | Moderazione automatica IA | Assente | Nessuno | Nessun punto d'integrazione | Coda e interfaccia provider separata dal flusso principale | Media |
| R21 | Classificazione tematica IA | Assente | Nessuno | Nessuna tabella risultati | Persistenza versionata in `ANALISI_IA` | Media |
| R22 | Coerenza immagine/testo IA | Assente | Nessuno | Nessuna pipeline vision | Elaborazione asincrona e revisione umana | Media |
| R23 | Accessibilità | Assente | Nessuno | Nessuna UI | HTML semantico, tastiera, focus, contrasto, alternative testuali e lettura vocale opzionale | Alta |
| R24 | Privacy e protezione dati | Assente | Nessuno | Nessuna informativa, minimizzazione o policy retention | Privacy by design, consenso, retention e autorizzazioni | Critica |
| R25 | Sicurezza applicativa | Assente | Nessuno | Nessun controllo implementato | Header sicuri, CSRF, rate limit, query parametrizzate e validazione | Critica |
| R26 | Prestazioni e paginazione | Assente | Nessuno | Nessuna query o limite | Paginazione, indici e limiti upload | Media |
| R27 | Affidabilità e gestione errori | Assente | Nessuno | Nessun error handler o transazione | Errori centralizzati, rollback e logging strutturato | Alta |
| R28 | Scalabilità e riuso backend | Assente | Nessuno | Nessuna separazione API/UI | API REST modulare e storage sostituibile | Media |
| R29 | SPID/CIE | Assente; dati demo nello schema fornito | Nessuno | Non è una semplice autenticazione locale e richiede provider autorizzati | Predisporre adapter e implementare solo con provider/ambienti ufficiali | Bassa |
| R30 | Interfaccia responsive e visuale | Assente | Nessuno | Nessun frontend | Design system semplice, mobile-first e accessibile | Alta |

## 3. Analisi MySQL

### Stato verificabile

Nel repository non esistono file `.sql`, migrazioni o modelli. L'analisi seguente riguarda esclusivamente lo script fornito in chat, non lo schema Aiven effettivamente in esecuzione.

### Tabelle presenti nello script fornito

- `UTENTE`
- `MODERATORE`
- `SEGNALAZIONE`
- `ALLEGATO`
- `COMMENTO`
- `SOSTEGNO`
- `VERIFICA_IDENTITA`
- `BLOCCO`
- `EVENTO_LOG`
- `VARIAZIONE_LOG`

### Tabelle richieste ma assenti o non equivalenti

| Requisito concettuale | Situazione nello script | Intervento proposto |
|---|---|---|
| `QUARTIERE` | Assente | Aggiungere anagrafica quartieri e FK da utente/segnalazione |
| `STATO_SEGNALAZIONE` | Stato salvato come `VARCHAR` | Aggiungere tabella di dominio e FK |
| `CATEGORIA` | Assente | Aggiungere catalogo categorie |
| `SEGNALAZIONE_CATEGORIA` | Assente | Aggiungere tabella ponte molti-a-molti |
| `STORICO_STATO` | Sostituito solo in parte dai log generici | Aggiungere storico specifico con stato precedente/successivo, autore e data |
| `ANALISI_IA` | Assente | Aggiungere risultati, modello/versione, punteggio, stato revisione e riferimenti |

`COMMENTO`, `MODERATORE`, `VERIFICA_IDENTITA`, `BLOCCO`, `EVENTO_LOG` e `VARIAZIONE_LOG` sono estensioni utili rispetto al modello minimo, ma non sostituiscono le entità mancanti.

### Chiavi, relazioni e cardinalità

- Le chiavi primarie numeriche `AUTO_INCREMENT` sono coerenti con MySQL.
- `MODERATORE.IdUtente` realizza correttamente una specializzazione 0..1 di `UTENTE`.
- Le relazioni autore-segnalazione, segnalazione-allegato, autore-commento e utente-sostegno sono espresse con FK.
- Il vincolo `UNIQUE (IdUtente, IdSegnalazione)` impedisce sostegni duplicati, inclusi quelli ritirati: la riattivazione dovrebbe aggiornare la stessa riga.
- La tabella `BLOCCO` distingue moderatore che applica e moderatore che revoca.
- `EVENTO_LOG` usa molte FK opzionali, cioè un'associazione polimorfica debole: il database non garantisce che ogni evento punti esattamente agli oggetti coerenti con `TipoAzione`.

### Vincoli e integrità

Aspetti corretti:

- `ENGINE=InnoDB`, `utf8mb4`, `AUTO_INCREMENT`, `DATETIME` e `DECIMAL` sono compatibili con MySQL 8.0+.
- Le email sono univoche.
- Le FK principali sono dichiarate.
- La cancellazione account è predisposta come cancellazione logica.

Problemi da correggere in una migrazione approvata:

- Stati, tipo segnalazione, visibilità, metodo/esito verifica e livelli permesso sono stringhe libere senza tabelle di dominio o `CHECK`.
- Mancano `CHECK` per latitudine tra -90 e 90, longitudine tra -180 e 180 e coerenza delle date di blocco/revoca.
- L'allegato obbligatorio non può essere garantito dalla sola FK: serve una transazione applicativa e uno stato bozza/pubblicata, oppure una procedura controllata.
- Non è verificato che `ALLEGATO.IdAutore` coincida con l'autore della segnalazione o con un soggetto autorizzato.
- Non sono specificate azioni `ON DELETE`/`ON UPDATE`; la strategia deve privilegiare cancellazione logica per contenuti tracciati.
- Mancano indici espliciti per filtri frequenti: stato, tipo, data, autore, quartiere, categorie, coordinate e sostegni attivi.
- `RiferimentoFile` è un percorso, ma mancano dimensione, hash, nome originale, MIME validato, stato scansione e metadati tecnici.
- `VERIFICA_IDENTITA.RiferimentoVerifica` deve evitare dati identificativi eccessivi e rispettare la minimizzazione.
- Mancano trigger, viste e procedure. Non sono obbligatori per ogni funzione, ma possono essere utili per viste di classifica e controlli di coerenza; la logica applicativa deve restare testabile.

### Normalizzazione

Lo schema fornito è in gran parte vicino alla terza forma normale per le entità presenti. Rimangono però domini ripetuti come stringhe e mancano le entità normalizzate previste dai requisiti. `EVENTO_LOG` e `VARIAZIONE_LOG` sono volutamente generici e richiedono regole applicative robuste.

### Compatibilità Aiven

La connessione dovrà usare `mysql2` con TLS. Le credenziali e il certificato CA devono essere letti da variabili d'ambiente e mai versionati. Prima di qualsiasi migrazione occorre:

1. esportare o salvare lo schema corrente;
2. confrontarlo con lo script fornito;
3. applicare migrazioni incrementali, non ricreare il database;
4. testare le migrazioni su un database separato;
5. concordare backup e rollback.

Non è stato rilevato codice PostgreSQL.

## 4. Stack consigliato

| Area | Scelta | Motivazione |
|---|---|---|
| Runtime | Node.js LTS | Coerente con la consegna, diffuso e adatto ad API REST |
| Backend | Express.js | Più semplice di NestJS e con ecosistema più ampio di Fastify per un progetto scolastico; la struttura a livelli evita un unico file monolitico |
| Frontend | HTML, CSS e JavaScript modulari | Sufficiente per il perimetro, facilmente comprensibile e accessibile; React/Vue aggiungerebbero complessità non necessaria |
| Database | MySQL 8.0+ su Aiven | Vincolo esplicito del progetto |
| Accesso dati | `mysql2/promise` | Query SQL trasparenti e parametrizzate; più coerente con uno schema già esistente rispetto a introdurre subito Prisma/Sequelize |
| Script SQL | Da mantenere | Resta la fonte verificabile per schema, migrazioni e seed fittizi |
| Validazione | Zod | Schemi riutilizzabili, messaggi coerenti e validazione server-side centrale |
| Autenticazione | Sessioni server-side e cookie `HttpOnly` | Frontend web sullo stesso dominio: riduce l'esposizione di token nel browser; store persistente MySQL in produzione |
| Password | Argon2id | Algoritmo moderno per hashing password; mai salvare password in chiaro |
| Autorizzazione | RBAC applicativo | Middleware per utente, moderatore e amministratore |
| Upload | Multer con adapter storage | Semplice in sviluppo; validazione MIME, estensione, dimensione e nome; object storage in produzione |
| Configurazione | `dotenv` solo in sviluppo + validazione env | `.env` locale ignorato; `.env.example` senza segreti; variabili della piattaforma in produzione |
| Sicurezza HTTP | Helmet, rate limiting, CSRF e CORS ristretto | Riduce rischi comuni; CSRF necessario con sessioni cookie |
| Logging | Pino | Log strutturati senza includere password, cookie o dati personali non necessari |
| Test | Vitest/Supertest | Test unitari e di integrazione delle API con sintassi semplice |

### Alternative valutate

- Fastify offre buone prestazioni, ma Express è più lineare per il livello e la documentazione disponibile.
- NestJS è molto strutturato, ma introduce TypeScript, decorator e astrazioni eccessive per questa prima versione.
- Prisma genera un modello comodo, ma può complicare l'adozione di uno schema Aiven preesistente e la gestione didattica di SQL, trigger e viste.
- Sequelize e Knex sono validi, ma `mysql2` mantiene visibili le query e riduce il numero di concetti da apprendere.
- JWT è utile per client multipli e app native, ma per una webapp same-origin le sessioni protette sono più semplici da revocare. In futuro l'autenticazione API potrà evolvere senza riscrivere i servizi di dominio.

## 5. Architettura proposta

### Flusso applicativo

```text
Browser
  -> Frontend web accessibile
  -> API REST Node.js / Express
  -> Autenticazione, autorizzazione e validazione
  -> Controller
  -> Service e transazioni
  -> Repository con query parametrizzate
  -> MySQL Aiven via TLS
```

I controller traducono HTTP in chiamate applicative. I service contengono regole aziendali e transazioni. I repository sono l'unico livello autorizzato a eseguire query. Questa separazione permette a una futura app mobile di riutilizzare la stessa API.

### Flusso allegati

```text
Browser
  -> Upload API autenticata
  -> Controllo dimensione, MIME, estensione e firma del file
  -> Nome casuale e scansione/normalizzazione
  -> Storage locale in sviluppo o object storage in produzione
  -> Metadati nella tabella ALLEGATO
```

La segnalazione nasce come bozza. Diventa pubblicabile solo dopo il salvataggio di almeno un allegato valido. Il database conserva un riferimento allo storage, non il file binario.

### Predisposizione IA futura

```text
Segnalazione inviata
  -> Coda di elaborazione
  -> Moderazione testo / classificazione / EXIF / computer vision
  -> Tabella ANALISI_IA
  -> Revisione del moderatore
  -> Pubblicazione o richiesta di correzione
```

La prima versione non deve dipendere da un provider IA. Verrà definita un'interfaccia di servizio e gli esiti saranno versionati con modello, data, punteggio, payload sintetico e decisione umana.

## 6. Struttura di progetto consigliata

```text
project-root/
├── client/
│   ├── assets/
│   ├── css/
│   ├── js/
│   │   ├── api/
│   │   ├── components/
│   │   ├── pages/
│   │   └── utils/
│   └── index.html
├── server/
│   ├── src/
│   │   ├── config/
│   │   ├── controllers/
│   │   ├── middlewares/
│   │   ├── repositories/
│   │   ├── routes/
│   │   ├── services/
│   │   ├── validators/
│   │   ├── utils/
│   │   ├── app.js
│   │   └── server.js
│   └── tests/
├── database/
│   ├── migrations/
│   ├── schema/
│   └── seeds/
├── docs/
│   └── analisi-tecnica.md
├── storage/
│   └── .gitkeep
├── .env.example
├── .gitignore
├── package.json
└── README.md
```

`storage/` conterrà soltanto file di sviluppo ed è ignorata da Git, salvo `.gitkeep`. Le cartelle verranno create quando contengono codice reale, evitando contenitori vuoti non necessari.

## 7. Piano di implementazione

| Fase | File coinvolti | Attività e dipendenze | Rischi | Criterio di completamento |
|---|---|---|---|---|
| 1. Analisi e sistemazione | `docs/analisi-tecnica.md`, `README.md`, `.gitignore` | Confermare schema Aiven e priorità | Modificare uno schema remoto non allineato | Analisi approvata e backup concordato |
| 2. Configurazione Node.js | `package.json`, `server/src/app.js`, `server/src/server.js` | Express, script dev/start/test, error handler | Versioni Node incoerenti | Server si avvia e health check risponde |
| 3. Collegamento MySQL | `server/src/config/*`, `.env.example` | Pool `mysql2`, TLS Aiven, verifica env | Segreti o CA versionati | Connessione verificata senza segreti nel repo |
| 4. Autenticazione | route/controller/service/repository auth | Registrazione, login, logout, Argon2id, session store, CSRF | Session fixation, enumeration | Test login/logout e cookie sicuri superati |
| 5. Ruoli | middleware auth/RBAC | Utente, moderatore, amministratore | Controlli solo frontend | Endpoint negano accessi non autorizzati |
| 6. Quartieri | migrazione, repository, route | Catalogo e associazioni | Dati di Milano incompleti | CRUD/lettura e FK verificate |
| 7. Categorie | migrazione, repository, route | Catalogo e relazione molti-a-molti | Duplicati | Vincoli unici e assegnazione testati |
| 8. Segnalazioni | moduli segnalazioni, pagine frontend | Bozza, creazione, modifica consentita, dettaglio | Transazioni incomplete | CRUD autorizzato e validato |
| 9. Allegati | upload middleware/service/storage | Limiti, firma file, MIME, nomi casuali, cleanup | File malevoli o orfani | Pubblicazione impossibile senza allegato valido |
| 10. Sostegni | route/service/repository | Aggiunta, ritiro, riattivazione | Race condition e duplicati | Vincolo DB e test concorrenti rispettati |
| 11. Stati e storico | migrazione e service | Transizioni, storico e audit nella stessa transazione | Stato e storico disallineati | Ogni transizione valida produce storico |
| 12. Dashboard e filtri | homepage, API query | Ricerca, filtri, classifica, paginazione, mappa | Query lente | Risultati corretti e indicizzati |
| 13. Validazione e sicurezza | middleware, configurazione | Zod, Helmet, rate limit, CSRF, CORS, sanitizzazione output | Falsi sensi di sicurezza | Test negativi e checklist OWASP essenziale |
| 14. Test | `server/tests`, test frontend essenziali | Unitari, integrazione, auth, permessi, upload | Dipendenza dal DB di produzione | Suite usa DB di test e passa in modo ripetibile |
| 15. Documentazione | `README.md`, `docs/*`, OpenAPI opzionale | Setup, env, Aiven, API, migrazioni | Istruzioni obsolete | Nuovo sviluppatore avvia il progetto seguendo README |
| 16. Predisposizione IA | service interface, coda, migrazione `ANALISI_IA` | Contratti e stati, nessun provider obbligatorio | Costi, privacy e blocchi sincroni | Pipeline simulata e revisione umana funzionanti |

## Decisioni da confermare prima del codice

1. Usare Express.js, JavaScript modulare e `mysql2/promise`.
2. Usare frontend HTML/CSS/JavaScript senza React o Vue.
3. Usare sessioni server-side con cookie `HttpOnly` e Argon2id.
4. Trattare il database Aiven esistente con migrazioni incrementali, senza ricrearlo.
5. Aggiungere allo schema le entità mancanti solo dopo confronto con lo schema reale.
6. Usare storage locale esclusivamente in sviluppo e progettare un adapter per object storage.
7. Implementare prima le funzioni core; lasciare SPID/CIE e moduli IA come integrazioni predisposte ma non simulate come servizi reali.

## Priorità riepilogative

### Critiche

- configurazione sicura Aiven e verifica dello schema reale;
- registrazione, autenticazione, autorizzazione e blocco account;
- segnalazioni con allegato obbligatorio;
- stati coerenti e storico;
- protezione dati e sicurezza applicativa.

### Alte

- quartieri e categorie;
- sostegni e classifica;
- moderazione;
- ricerca, filtri e mappa;
- accessibilità;
- gestione degli errori e test di integrazione.

### Medie o successive

- ottimizzazioni di scala;
- pipeline EXIF e IA;
- SPID/CIE tramite provider autorizzati.

## Esito della fase di analisi

Il repository è una base vuota e non presenta vincoli tecnici preesistenti. Lo schema SQL fornito è compatibile con MySQL 8.0+ nelle istruzioni usate, ma non copre ancora integralmente il modello richiesto e non è verificato rispetto al database Aiven reale. L'implementazione può iniziare dopo l'approvazione di questo documento e dopo aver definito una modalità sicura per fornire la configurazione Aiven.

In questa fase è stata analizzata e pianificata esclusivamente la webapp. Non sono state progettate o create app Android, iOS, desktop, PWA completa o pacchetti per store.
