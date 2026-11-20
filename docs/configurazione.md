# Configurazione completa

Questa guida configura l'applicazione in modalità **solo produzione MySQL/Aiven**.
I comandi sono pensati per Windows PowerShell, ma le variabili e i passaggi SQL
sono uguali su Linux/macOS.

## 1. Scaricare il progetto e creare l'ambiente Python

Apri PowerShell nella cartella in cui vuoi installare il progetto:

```powershell
git clone https://github.com/villanuevaprince-lab/LaNostraCittaIlNostroFuturo_webapp.git
cd LaNostraCittaIlNostroFuturo_webapp
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
```

Se PowerShell blocca l'attivazione dell'ambiente, esegui una sola volta:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Avvia sempre dalla **radice del progetto**, non dalla cartella `backend`.
Il comando corretto sarà `python -m backend.app`.

## 2. Recuperare i dati di Aiven

In Aiven apri il servizio MySQL e copia i valori della pagina **Connection
information**:

- host/server;
- port;
- user;
- password;
- database/schema;
- certificato CA.

Scarica il certificato CA Aiven. Salva il suo contenuto nella variabile d'ambiente
`DB_SSL_CA` (su Vercel incollalo come variabile multilinea). Il fallback locale
`DB_SSL_CA_PATH` resta disponibile per compatibilita, ma non e necessario.

Il certificato CA e le credenziali sono privati: non devono essere caricati su GitHub.
Il programma rifiuta la connessione se il certificato manca o se la verifica TLS
non è possibile.

## 3. Creare il file `.env`

Da PowerShell:

```powershell
Copy-Item .env.example .env
notepad .env
```

Compila il file con valori reali. Esempio, usando segnaposto non validi:

```dotenv
SECRET_KEY=INSERISCI_UNA_STRINGA_CASUALE_DI_ALMENO_32_CARATTERI
SESSION_COOKIE_SECURE=false
RATELIMIT_STORAGE_URI=memory://
UPLOAD_FOLDER=storage/uploads
MAP_CONTACT_EMAIL=tuo-email@example.com

DB_HOST=il-tuo-host.aivencloud.com
DB_PORT=12345
DB_POOL_SIZE=5
DB_POOL_WAIT=5
DB_USER=avnadmin
DB_PASSWORD=la-password-di-aiven
DB_NAME=nostra_citta
DB_SSL_CA=-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----
```

Genera una chiave sicura senza scriverla nel repository:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Incolla il risultato al posto di `SECRET_KEY`. Non usare la stessa chiave in
ambienti diversi e non cambiarla a ogni avvio: invaliderebbe le sessioni.

Per HTTPS in produzione imposta `SESSION_COOKIE_SECURE=true`. Per lo sviluppo
locale in `http://localhost` lascia `false`.

`MAP_CONTACT_EMAIL` è consigliato per identificare l'applicazione al servizio
di geocodifica. Le richieste di ricerca sono effettuate solo dopo un'azione
esplicita dell'utente e sono limitate; per molti utenti configura un servizio
di geocoding/tile dedicato.

### Email: reset password e cambio indirizzo

Per inviare davvero le email configura un server SMTP (qualunque provider che offra
SMTP, ad esempio Resend, SendGrid, Mailgun o Brevo):

```dotenv
MAIL_SERVER=smtp.tuo-provider.example
MAIL_PORT=587
MAIL_USERNAME=utente-smtp
MAIL_PASSWORD=password-o-api-key-smtp
MAIL_USE_TLS=true
MAIL_USE_SSL=false
MAIL_FROM=La Nostra Città <noreply@tuodominio.example>
APP_BASE_URL=https://indirizzo-pubblico-dell-app.example
PASSWORD_RESET_MAX_AGE=1800
EMAIL_CHANGE_MAX_AGE=3600
```

In sviluppo, senza `MAIL_SERVER`, ogni email è salvata come file `.eml` in
`storage/mail_outbox/` (apribile con un client di posta); il log mostra solo il
percorso, non il link. `APP_BASE_URL` è obbligatorio in produzione: i link
inviati per email usano solo questo valore.

### IA locale con Ollama (facoltativa)

Installa Ollama sulla stessa macchina dell'app e scarica i modelli:

```powershell
ollama pull qwen2.5:7b
ollama pull qwen2.5vl:7b
```

Poi, nel `.env` (valori di default; descrizioni in `.env.example`):

```dotenv
AI_ENABLED=true
OLLAMA_URL=http://localhost:11434
VERIFICA_MODELLO=qwen2.5vl:7b
VERIFICA_TIMEOUT=120
VERIFICA_SOGLIA_ALTA=0.90
VERIFICA_SOGLIA_BASSA=0.70
VERIFICA_MAX_TENTATIVI=5
VERIFICA_BACKOFF_BASE=30
VERIFICA_BACKOFF_MAX=3600
VERIFICA_INTERVALLO=10
VERIFICA_LEASE_SECONDI=900
VERIFICA_MAX_REINVII=3
```

Avvia il worker accanto all'applicazione, dalla radice del progetto (puoi avviarne più
di uno: la coda usa `SKIP LOCKED`):

```powershell
flask --app backend.app verifica-worker
```

`--once` elabora un solo job (utile per prove). Le soglie sono validate all'avvio
(`0 <= bassa <= alta <= 1`). Se Ollama non risponde i contenuti restano in attesa
e vengono ripresi da soli. Il primo job dopo l'avvio può superare il timeout mentre il
modello si carica: conta come errore transitorio e viene ritentato.

### Test della coda su MySQL (facoltativi)

`backend/tests/test_verification_mysql.py` prova `SKIP LOCKED` con due worker,
modello assente, ripresa dopo un crash, retry, reinvii, ricorso e override su un
MySQL 8 **locale**. Girano solo con `VERIFICA_MYSQL_TEST=1`, `DB_HOST=localhost` e un
`DB_NAME` che finisce con `_test` (mai su Aiven). Crea il database con lo schema
001 (sostituendo il nome), i seed, le migrazioni 005–007 e la 010, poi:

```bash
VERIFICA_MYSQL_TEST=1 DB_NAME=nostra_citta_test python -m pytest backend/tests/test_verification_mysql.py
```

## 4. Verificare lo schema Aiven prima delle migrazioni

Fai un backup dal pannello Aiven o dal client MySQL. Poi verifica lo schema:

```sql
USE nostra_citta;
SHOW TABLES;
SHOW COLUMNS FROM UTENTE;
SHOW COLUMNS FROM SEGNALAZIONE;
SHOW INDEX FROM SEGNALAZIONE;
```

Se il database contiene solo le tabelle iniziali, applica nell'ordine:

1. `database/migrations/002_extend_existing_schema.sql`
2. `database/seeds/001_reference_data.sql`
3. controlla i dati e applica `database/migrations/003_enforce_attachment_publication.sql`
4. `database/migrations/004_civic_features.sql`
5. `database/migrations/005_shared_attachment_content.sql`
6. `database/migrations/008_ai_analysis.sql` (dopo 006 e 007; oppure `python -m backend.apply_ai_migration`)
7. `database/migrations/009_user_email_normalized.sql` con `python -m backend.apply_email_migration`:
   lo script si ferma se la normalizzazione (trim, minuscole) creerebbe email duplicate
   o se esistono indirizzi senza `@`, poi imposta la collation `utf8mb4_0900_ai_ci` e il
   vincolo `chk_utente_email_normalizzata`. Su un database creato dallo schema 001
   aggiornato risulta già applicata.
8. `database/migrations/010_ai_verification_pipeline.sql` con
   `python -m backend.apply_verification_migration` (dopo la 007, anche per un database
   nuovo creato dallo schema 001): aggiunge `StatoVerifica`, i contatori di reinvii e ricorsi,
   le tabelle `VERIFICA_JOB`, `VERIFICA_ESITO`, `VERIFICA_VIOLAZIONE`, `DECISIONE_VERIFICA`
   e `NOTIFICA.Messaggio`. I contenuti esistenti restano pubblicati; le vecchie bozze
   diventano «da revisionare». È necessaria per questa versione del codice.

Le migrazioni non sono completamente idempotenti: **non rilanciarle** se le
colonne, gli indici o i trigger sono già presenti. In particolare la 004 deve
aggiungere queste colonne a `UTENTE`:

```text
Bio, NotificheEmail, AvatarRiferimento, SessionVersion
```

e questo indice a `SEGNALAZIONE`:

```text
idx_segnalazione_coda (Visibilita, IdSegnalazione)
```

Per eseguire uno script con il client MySQL, dalla radice del progetto:

```powershell
mysql --host=IL_TUO_HOST --port=LA_TUA_PORTA --user=IL_TUO_USER `
  --password --ssl-ca=certificates/ca.pem nostra_citta `
  < database/migrations/004_civic_features.sql
```

Su Windows, se il carattere `<` non funziona nella shell utilizzata, apri lo
script in MySQL Workbench o nel pannello SQL di Aiven e avvialo lì.

Per la migrazione 005, usa direttamente Python dalla radice del progetto;
`create_app()` carica il `.env` locale e la connessione verifica la CA Aiven:

```powershell
python -m backend.apply_media_migration
```

Esegui la 005 prima di avviare il codice aggiornato. Per recuperare le foto
storiche, esegui sul computer che contiene ancora `storage/uploads/`:

```powershell
python -m backend.backfill_attachments --source "."
python -m backend.backfill_attachments --source "." --apply
```

Il primo comando mostra quanti allegati sono recuperabili e gli ID dei file
assenti. Il secondo li copia nel database condiviso. Per una cartella upload
personalizzata, passa quella cartella con `--source`. Non eliminare i file
originali prima di verificare le foto da un altro computer.

## 5. Creare il primo moderatore

Prima registra normalmente l'account dalla pagina `/register`. Recupera il suo
ID senza mai memorizzare password in chiaro:

```sql
USE nostra_citta;
SELECT IdUtente, Nome, Cognome, Email
FROM UTENTE
WHERE Email = 'moderatore@example.com';
```

Inseriscilo in `MODERATORE`:

```sql
INSERT INTO MODERATORE (IdUtente, LivelloPermessi)
VALUES (ID_UTENTE, 'amministratore');
```

Per un moderatore operativo usa `base`; per gestire tutti i permessi usa
`amministratore`. Non inserire hash manualmente nella tabella `MODERATORE`: la
password è già gestita in `UTENTE` durante la registrazione.

## 6. Avviare e controllare l'applicazione

Dalla radice, con `.venv` attivo:

```powershell
python -m backend.app
```

Apri:

```text
http://127.0.0.1:3000
```

Controlla la connessione reale ad Aiven:

```powershell
Invoke-RestMethod http://127.0.0.1:3000/api/health
```

La risposta attesa contiene:

```json
{"status":"ok","database":"aiven"}
```

Se il controllo restituisce `503`, l'app non sta usando dati temporanei: verifica
prima host, porta, credenziali, nome database, percorso CA e autorizzazione di
rete Aiven.

## 7. Flusso di prova consigliato

1. Apri `/register` e crea un account di prova.
2. Accedi e apri `/profilo`: salva bio, quartiere, preferenza notifiche e avatar.
3. Cambia password verificando quella attuale.
4. Apri `/reports/new`, cerca un indirizzo milanese, scegli il risultato e
   trascina il pin; verifica che indirizzo, latitudine e longitudine siano
   compilati prima dell'invio.
5. Controlla `/dashboard`: il contenuto deve risultare **Pubblicata**.
6. Accedi con il moderatore e apri `/moderazione`; rimuovi il contenuto,
   verifica la vista **Eliminati** e reinseriscilo. La dashboard dell'autore
   deve mostrare **Rimossa dai moderatori** prima del reinserimento.
7. Torna alla bacheca, apri la scheda dettaglio e verifica la mappa, i commenti
   e il sostegno.
8. Dalla dashboard dell'autore prova il ritiro logico della segnalazione.

## 8. Errori frequenti

### `503` su `/api/segnalazioni` (la mappa invece funziona)

Guarda il log del server, che indica la causa:

- `Schema del database non aggiornato (codice MySQL 1054)` o `1146`: il codice è più nuovo
  del database. Applica le migrazioni mancanti (sezione 4), in particolare la 010 con
  `python -m backend.apply_verification_migration`. La bacheca legge colonne aggiunte dalla 010,
  la mappa no: per questo si rompe solo la bacheca.
- `Connessioni MySQL esaurite anche dopo l'attesa`: troppe richieste insieme per il pool.
  Ogni pagina fa più chiamate in parallelo; l'app aspetta fino a `DB_POOL_WAIT` secondi una
  connessione libera. Se succede ancora, aumenta `DB_POOL_SIZE` entro il limite di connessioni
  del piano Aiven (ogni processo o istanza ha il proprio pool).
- `Errore MySQL (codice 2003/2013/…)`: database irraggiungibile o connessione caduta.

### Avvisi della console del browser sulla mappa

- `Expected value to be of type number, but found null instead`: arriva dallo stile Liberty di
  OpenFreeMap (altezza degli edifici 3D senza valore). `location.js` aggiunge un valore di
  ripiego appena lo stile è caricato; se ricompare con un nuovo stile, cerca altre proprietà
  numeriche lette con `["get", …]`.
- Una violazione CSP sulla source map di `maplibre-gl.js.map` compare solo con gli strumenti
  di sviluppo aperti; `connect-src` ora consente `https://unpkg.com`.


### `ModuleNotFoundError: No module named 'mysql'`

L'ambiente virtuale non è attivo oppure le dipendenze non sono state installate:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

### `ModuleNotFoundError: No module named 'backend'`

Il comando è stato eseguito dentro `backend`. Torna alla radice e usa:

```powershell
python -m backend.app
```

Non usare `python backend\app.py`.

### `Certificato CA MySQL mancante`

Controlla che il file esista davvero e che `.env` contenga:

```dotenv
DB_SSL_CA_PATH=certificates/ca.pem
```

### `Access denied` o timeout Aiven

Ricontrolla i valori copiati dalla pagina Connection information, la porta e le
regole di accesso del servizio Aiven. Non provare a disattivare TLS.

### Le nuove segnalazioni non compaiono nella home

Controlla `/dashboard` e `/api/health`. Se la dashboard mostra il contenuto
come pubblicato ma la home non lo mostra, verifica i filtri di ricerca e la
visibilità nel database. I nuovi contenuti passano a `pubblica` nella stessa
transazione che salva l'allegato.

### La mappa non trova un indirizzo

Controlla la connessione Internet, prova una via completa con “Milano” e verifica
che `MAP_CONTACT_EMAIL` sia valorizzato. Per uso intensivo non aumentare il
limite del servizio pubblico: usa un provider dedicato.

## 9. Test locali

I test non si collegano ad Aiven:

```powershell
python -m pytest -q backend/tests
```

Il risultato atteso della versione corrente è `78 passed`. I test simulano il
database e verificano autenticazione, autorizzazioni, moderazione, avatar,
geocoding, mappe e ritiro dei contenuti.

## 10. Regole di sicurezza

- non pubblicare `.env`, `certificates/ca.pem`, password o file caricati;
- non usare account Aiven amministrativi per l'applicazione in produzione;
- conserva backup e allegati su storage persistente;
- usa `SESSION_COOKIE_SECURE=true` dietro HTTPS;
- in produzione sostituisci `memory://` con uno storage rate-limit condiviso,
  ad esempio Redis;
- se una password è finita in Git, cambiala immediatamente su Aiven: modificare
  solo il file locale non elimina il valore dalla cronologia.
