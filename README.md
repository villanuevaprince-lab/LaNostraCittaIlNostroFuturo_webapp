# La Nostra Città, Il Nostro Futuro

Webapp civica per raccogliere segnalazioni, proposte e priorità dei quartieri di Milano. Il progetto usa un frontend accessibile in HTML/CSS/JavaScript e un'API REST Node.js/Express collegata a MySQL 8.0+.

## Funzionalità

- registrazione, accesso e sessioni protette da cookie `HttpOnly`;
- profilo personale e cancellazione logica dell'account;
- ruoli utente, moderatore e amministratore;
- feed con ricerca, filtri e ordinamento per sostegni;
- segnalazioni e proposte con foto/video obbligatorio;
- categorie, quartieri, coordinate e mappa OpenStreetMap;
- commenti, sostegni univoci e classifica delle priorità;
- ciclo di vita con storico degli stati;
- moderazione di contenuti e blocco/revoca degli account;
- log delle azioni principali;
- contrasto elevato, testo ingrandito e lettura vocale;
- schema predisposto per analisi IA future.

## Requisiti

- Node.js 20 o successivo;
- npm;
- MySQL 8.0+ oppure un servizio Aiven for MySQL;
- certificato CA di Aiven quando la verifica TLS è attiva.

## Configurazione

1. Installa le dipendenze:

   ```bash
   npm install
   ```

2. Crea il file locale `.env` partendo da `.env.example`:

   ```bash
   cp .env.example .env
   ```

3. Inserisci in `.env` i valori mostrati nella pagina **Overview** del servizio Aiven. Non commettere mai `.env`, password o certificati.

4. Scarica il certificato CA di Aiven e salvalo come `certificates/ca.pem`, oppure modifica `DB_SSL_CA_PATH`.

5. Genera un segreto di sessione robusto, per esempio:

   ```bash
   node -e "console.log(require('crypto').randomBytes(48).toString('hex'))"
   ```

## Preparazione del database

Prima di eseguire script sul database Aiven crea un backup.

### Database nuovo

Esegui nell'ordine:

```text
database/schema/001_full_schema.sql
database/seeds/001_reference_data.sql
```

### Database già creato con lo schema iniziale del progetto

Esegui una sola volta:

```text
database/migrations/002_extend_existing_schema.sql
database/seeds/001_reference_data.sql
```

La migrazione non viene avviata automaticamente dall'applicazione. In questo modo l'avvio del server non modifica lo schema remoto senza controllo.

## Avvio

Ambiente di sviluppo con riavvio automatico:

```bash
npm run dev
```

Avvio normale:

```bash
npm start
```

Apri `http://localhost:3000`. L'endpoint `GET /api/health` verifica anche la connessione MySQL.

## Test e controlli

```bash
npm test
npm run check
```

I test automatici non devono utilizzare il database di produzione. Per futuri test di integrazione configura un database MySQL separato.

## Rendere un utente moderatore

Dopo aver registrato normalmente l'account, un amministratore del database può associarlo alla tabella `MODERATORE`:

```sql
INSERT INTO MODERATORE (IdUtente, LivelloPermessi)
VALUES (ID_UTENTE, 'base');
```

I livelli ammessi sono `base` e `amministratore`. Sostituisci `ID_UTENTE` con l'identificativo reale; non aggiungere account dimostrativi in produzione.

## Sicurezza

- Tutti gli input sono validati anche dal server.
- Le query usano parametri preparati.
- Le password sono trasformate con Argon2id.
- Le richieste di modifica richiedono un token CSRF.
- Gli upload sono limitati, riconosciuti dalla firma binaria e rinominati casualmente.
- I contenuti vengono rimossi logicamente per conservare la tracciabilità.
- Le credenziali sono lette esclusivamente dalle variabili d'ambiente.

Per una pubblicazione reale vanno inoltre configurati HTTPS, reverse proxy, backup Aiven, object storage per gli allegati, scansione antimalware e monitoraggio.

## Struttura

```text
client/                  frontend statico e accessibile
server/src/              API, middleware, servizi e repository
server/tests/            test automatici
database/schema/         schema per installazioni nuove
database/migrations/     modifiche per database esistenti
database/seeds/          soli dati di riferimento
docs/                    analisi tecnica e documentazione API
storage/uploads/         file locali di sviluppo, ignorati da Git
```

## Documentazione

- [Analisi tecnica](docs/analisi-tecnica.md)
- [API REST](docs/api.md)
