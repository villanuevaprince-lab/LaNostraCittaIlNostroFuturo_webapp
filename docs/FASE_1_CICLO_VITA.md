# Fase 1 — Ciclo di vita dei contenuti

## Analisi e scelte

Il progetto è Flask + HTML/CSS/JS, MySQL Aiven e MapLibre. Gli upload sono già condivisi nel database con ALLEGATO_CONTENUTO. La precedente tabella SEGNALAZIONE conteneva entrambi i tipi con un unico elenco di stati.

Si conserva SEGNALAZIONE come contenuto comune (ID, autore, luogo, categorie, commenti, sostegni), con due entità specializzate:

- DETTAGLIO_SEGNALAZIONE: descrizione e data di risoluzione.
- PROPOSTA: soglia di sostegni, inizialmente 100 e configurabile nel form.

Le FK composte e i CHECK distinguono il tipo dei dettagli. Il CHECK sul contenuto vincola gli stati per tipo. Non si duplicano commenti, utenti o coordinate in nuove tabelle. Le scritture applicative creano il dettaglio nella stessa transazione del contenuto.

## File

| File | Responsabilità |
| --- | --- |
| `backend/lifecycle.py` | Stati, etichette, transizioni e vincoli per tipo |
| `backend/repositories/lifecycle.py` | Merge con lock, trasferimento interazioni, foto di intervento |
| `backend/repositories/reports.py` | Creazione specializzata, lettura, stato e protezione dalle scritture su duplicati |
| `backend/reports.py` | API protette, redirect dei duplicati, validazione input |
| `frontend/static/js/lifecycle.js` | Badge con etichette ottenute dal backend |
| `frontend/static/js/detail.js` | Prima/Dopo e caricamento della foto finale |
| `database/migrations/006_civic_lifecycle.sql` | Migrazione del modello e dei dati correnti |

## Stati

Segnalazione: Inviata (default), Presa in carico, In lavorazione, Risolta, Respinta / Archiviata.

Proposta: In valutazione (default), Approvata, Respinta / Archiviata. Raggiungere la soglia rende visibile l'obiettivo raggiunto; l'approvazione resta una decisione del moderatore, senza automatismi.

Le riaperture restano possibili per tutti gli stati del rispettivo tipo. I cambiamenti mantengono STORICO_STATO e EVENTO_LOG.

Conversione dei dati precedenti:

| Tipo | Vecchio stato | Nuovo stato |
| --- | --- | --- |
| Segnalazione | nuova, aperta, in_valutazione | inviata |
| Segnalazione | chiusa | archiviata |
| Segnalazione | altri stati operativi | invariati |
| Proposta | risolta | approvata |
| Proposta | chiusa | archiviata |
| Proposta | altri | in_valutazione |

Lo storico mantiene i codici precedenti nel dizionario SQL: non viene cancellata la cronologia.

## Attivazione con PowerShell

1. Fare un backup di Aiven e provare prima su una copia del database. Arrestare il server locale; in Vercel tenere il traffico sospeso durante la migrazione e il successivo deploy. Il vecchio codice invia stati ora sostituiti.
2. Scaricare il branch della funzionalità dalla radice del progetto:

```powershell
git fetch origin
git switch feature/civic-lifecycle
git pull --ff-only origin feature/civic-lifecycle
```

3. Usare l'ambiente virtuale e il `.env` esistente (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, SECRET_KEY, DB_SSL_CA oppure DB_SSL_CA_PATH). Non servono variabili `$env` manuali o mysql.exe:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m backend.apply_lifecycle_migration
```

Prerequisito: migrazioni 002–005 già applicate. Il comando modifica soltanto il database indicato nel `.env`; non viene eseguito automaticamente al boot. MySQL applica commit impliciti al DDL: in caso di errore parziale NON ripetere alla cieca, ripristinare la copia e correggere l'errore. L'assenza di credenziali impedisce di eseguire questa verifica da parte dell'assistente.

4. Avviare il server aggiornato:

```powershell
python -m backend.app
```

Aprire `http://localhost:3000`. Per Vercel distribuire il branch soltanto dopo avere completato la migrazione nel database usato dal deployment. Poi riaprire il traffico.

## Uso

- Form nuovo contenuto: scegliere Segnalazione o Proposta. Solo per le proposte compare la soglia.
- Bacheca: filtrare per tipo; i badge hanno etichetta testuale oltre al colore.
- Moderazione: Cambia stato conserva anche la possibilità di riaprire; Eliminati conserva i contenuti rimossi. Duplicati uniti elenca quelli accorpati.
- Merge: sul duplicato cliccare Unisci duplicato, inserire ID principale e motivazione. Sono ammessi solo contenuti pubblici dello stesso tipo. I sostegni attivi sono uniti per utente, quelli sul duplicato vengono ritirati mantenendo i log; i commenti vengono trasferiti mantenendo gli ID. Le foto restano sul contenuto originale per non perdere la loro provenienza. La pagina e le API di discussione/sostegno del duplicato indirizzano al principale. Catene e cicli sono rifiutati; un contenuto già principale di altri duplicati non può essere accorpato ad un altro. L'unione non ha un comando di annullamento.
- Prima/Dopo: come moderatore aprire la scheda della segnalazione, compilare Documenta l'intervento con una foto e descrizione. Impostare poi Risolta dalla moderazione. La scheda Risolta mostra il confronto; per contenuti storici senza immagini appare Foto non disponibile. Si possono aggiungere più foto finali, senza sovrascrivere gli originali.

## API aggiunte

- `POST /api/moderazione/segnalazioni/<id>/duplicato`: JSON `{ "duplicate_of_id": 123, "motivazione": "Stesso disservizio" }`.
- `POST /api/moderazione/segnalazioni/<id>/risoluzione`: multipart con `risoluzione` e `allegato` (JPEG/PNG/WebP).
- `GET /api/segnalazioni?tipo=proposta`: filtro aggiuntivo.

Tutte le mutazioni richiedono sessione, ruolo moderatore ove indicato e token CSRF. La validazione file usa il servizio esistente che rimuove i metadati delle immagini.

## Verifica

```powershell
python -m pytest backend/tests -q
```

I test usano repository simulati e verificano rotte, lock, rollback, SQL parametrizzato e autorizzazioni. Non rappresentano un test di integrazione su Aiven né una misura di capacità sotto carico. Prima del deploy verificare sulla copia Aiven: nuove pubblicazioni di entrambi i tipi, riapertura, foto finale e merge di due contenuti sostenuti dallo stesso utente (deve contare una volta).
