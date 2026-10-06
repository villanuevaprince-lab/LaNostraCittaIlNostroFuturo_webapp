# La Nostra Città, Il Nostro Futuro

Progetto scolastico con **backend Flask** e **frontend HTML, CSS e JavaScript**.
Le pagine HTML usano i template Jinja inclusi in Flask: non occorrono Node o un
framework frontend. API e pagine sono servite dallo stesso indirizzo.

## Funzioni disponibili

- Bacheca pubblica con ricerca di segnalazioni e proposte.
- Registrazione con nome, cognome, email univoca e password.
- Login, logout e sessione firmata tramite cookie.
- Creazione solo per utenti autenticati, nella pagina separata `/reports/new`.
- Ritorno alla homepage con messaggio dopo una pubblicazione riuscita.
- Modalità demo in memoria o collegamento al database MySQL esistente su Aiven.

## Pagine

| Rotta | Accesso | Funzione |
| --- | --- | --- |
| `/` | Pubblico | Homepage: sola consultazione, ricerca e link alla creazione |
| `/home` | Pubblico | Reindirizza a `/` |
| `/register` | Pubblico | GET form, POST registrazione e accesso automatico |
| `/login` | Pubblico | GET form, POST autenticazione |
| `/logout` | POST con CSRF | Uscita e ritorno alla home |
| `/reports/new` | Autenticato | GET form dedicato, POST pubblicazione |
| `/dashboard` | Autenticato | Alias della bacheca: reindirizza a `/` |

Chi apre `/reports/new` senza sessione passa per
`/login?next=/reports/new`. Anche il collegamento alla registrazione conserva
questa destinazione. Nessun form di creazione o modal è presente nella home.

## Moduli

| Percorso | Responsabilità |
| --- | --- |
| `backend/app.py` | Application factory, configurazione, estensioni ed errori |
| `backend/auth.py` | Registrazione, login e logout |
| `backend/security.py` | Sessioni, controllo accesso, CSRF e limitazione tentativi |
| `backend/forms.py` | Validazione sul server |
| `backend/users.py` | Query sulla tabella UTENTE |
| `backend/database.py` | Connessione Aiven e repository segnalazioni/demo |
| `backend/pages.py`, `backend/reports.py` | Bacheca, nuova segnalazione e API |
| `frontend/templates/` | Base comune, home, login, registrazione, nuova segnalazione, errori |
| `frontend/static/css/`, `frontend/static/js/` | Stili e miglioramenti JavaScript |
| `backend/tests/` | Test isolati e controlli SQL con connessioni simulate |

Solo `frontend/static/` è pubblica. I template non sono scaricabili come file
statici: non si può aggirare la protezione aprendo direttamente un file HTML.

## Avvio rapido (Python 3.10+)

Dalla radice del progetto:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python -m backend.app
```

Su Windows PowerShell, al posto di `source`:

```powershell
.venv\Scripts\Activate.ps1
```

Se PowerShell blocca gli script, puoi usare direttamente
`.venv\Scripts\python.exe` al posto di `python`, senza cambiare la policy di sistema.

Apri [http://localhost:5000](http://localhost:5000) e crea un account tramite
**Registrati**. In demo non esistono credenziali predefinite: gli account e i
contenuti aggiunti spariscono al riavvio. Usa un solo processo per la demo.

La chiave di sessione viene generata in memoria se non configurata in demo;
per un valore stabile genera una chiave e inseriscila nel file locale `.env`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Aiven: database già esistente

1. Copia `.env.example` in `.env`, senza commettere quest'ultimo.
2. Imposta `APP_MODE=database` e una `SECRET_KEY` casuale di almeno 32 caratteri.
3. Inserisci i parametri Aiven (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`).
4. Scarica il certificato CA e salva il file indicato da `DB_SSL_CA_PATH`.
5. Avvia Flask. La connessione verifica certificato e identità del server.

Queste funzionalità usano le colonne originali di `UTENTE`, `SEGNALAZIONE` e
`SOSTEGNO`. **Non occorre eseguire una nuova migrazione** e l'app non crea
automaticamente tabelle. Gli script in `database/` rimangono disponibili per
installazioni nuove; non vanno rilanciati sul database già popolato.

Gli utenti del seed con `HASH_DEMO_NON_VALIDO_*` non possono autenticarsi:
registrati con una nuova email. Gli hash Argon2 della precedente app Node sono
compatibili; i nuovi account usano scrypt tramite Werkzeug.

**Credenziali:** non inserire password reali in `.env.example`. Se una password
è già stata pubblicata su GitHub, cambiala su Aiven: sostituirla nell'ultimo commit
non la rimuove dalla cronologia.

## Test

```bash
python -m pytest -q
```

I test non contattano Aiven. Verificano form, sessioni, autorizzazioni, CSRF,
hash, duplicati, redirect, creazione e rollback MySQL con connessioni simulate.
La connessione al database reale va verificata separatamente con credenziali locali.

## Sicurezza e limiti

- Password salvate solo come hash; cookie firmato `HttpOnly`, `SameSite=Lax`,
  durata 2 ore, `Secure` configurabile per HTTPS.
- CSRF su tutti i POST, incluso logout; query SQL parametrizzate.
- L'autore è ricavato dalla sessione: nessun campo `id_autore` nel form.
- Account bloccati/cancellati esclusi dal login e ricontrollati a ogni richiesta.
- Destinazioni `next` limitate a pagine interne note; HTML con escaping automatico.
- Limite dei tentativi di login e registrazione. `memory://` è solo per sviluppo:
  in produzione usa uno storage condiviso, ad esempio Redis, installando
  `Flask-Limiter[redis]` e configurando `RATELIMIT_STORAGE_URI`.
- Per pubblicare: server WSGI, HTTPS, `SESSION_COOKIE_SECURE=true`, debug disattivato,
  chiave persistente condivisa fra i worker, gestione sicura dei segreti e backup.
  Non fidarti di header proxy senza configurare il reverse proxy effettivamente usato.

Non sono inclusi verifica email, recupero password, SPID/CIE, upload, moderazione,
modifica profilo o dashboard personale: restano estensioni separate.
La registrazione email/password non certifica l'identità reale di una persona.

Per struttura delle rotte, modello dati, flusso e snippet commentati:
[Architettura e autenticazione](docs/architettura.md).
Per l'API JSON: [API](docs/api.md).
