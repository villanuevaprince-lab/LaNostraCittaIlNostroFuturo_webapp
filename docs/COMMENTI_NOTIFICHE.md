# Commenti, notifiche e paginazione utenti

Queste modifiche completano il branch `feature/civic-lifecycle`, già proposto nella PR #3.

## Cosa cambia

- Gestione utenti: ID già caricati memorizzati, cursore che deve avanzare, blocco delle richieste contemporanee e arresto a fine elenco. La ricerca azzera cursore e ID; risposte di vecchie ricerche vengono ignorate.
- Commenti: Rispondi seleziona il commento padre, Annulla risposta ritorna al commento principale. La discussione è condivisa fra bacheca e dettaglio. Le risposte hanno un riferimento cliccabile al commento padre e un'indentazione limitata sui telefoni.
- Elimina il mio commento: autorizzazione verificata dal server usando l'autore e la sessione. Il testo viene svuotato e il nodo rimane come segnaposto per conservare le risposte degli altri. I moderatori mantengono l'azione di rimozione. Ogni modifica resta nel log.
- Notifiche interne persistenti: nuovi commenti ai propri contenuti, risposte ai propri commenti, nuovi sostegni e cambi di stato. Nessuna notifica delle proprie azioni a sé stessi. Se sei autore sia del contenuto sia del commento padre ricevi una sola notifica.
- Il collegamento Notifiche nella navigazione mostra il numero non letto, aggiornato ogni minuto mentre la pagina è visibile. La pagina personale usa paginazione a cursore e segna una notifica come letta quando la apri.

Non sono email né notifiche push di sistema; l'opzione profilo NotificheEmail continua a riguardare le email. Le nuove notifiche iniziano dalle azioni successive alla migrazione: non vengono ricostruite quelle precedenti.

## File principali

| File | Funzione |
| --- | --- |
| `frontend/static/js/moderation.js` | Paginazione utenti senza duplicati |
| `frontend/static/js/discussion.js` | Componente condiviso per discussioni e risposte |
| `backend/repositories/reports.py` | Thread, controllo del padre e notifiche transazionali |
| `backend/community.py` | API protette per eliminazione personale e inbox |
| `backend/repositories/notifications.py` | Query delle notifiche, sempre limitate al destinatario |
| `frontend/static/js/notifications.js` | Inbox, lettura e contatore |
| `database/migrations/007_comments_notifications.sql` | Parent dei commenti e tabella NOTIFICA |

## Installazione con PowerShell

Dalla radice del progetto, con il server arrestato:

```powershell
git fetch origin
git switch feature/civic-lifecycle
git pull --ff-only origin feature/civic-lifecycle
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Fare prima un backup. Le migrazioni leggono le credenziali dal `.env` del progetto, senza mysql.exe. Provare su una copia Aiven prima della produzione.

Se NON hai ancora applicato la migrazione 006 della Fase 1:

```powershell
python -m backend.apply_lifecycle_migration
```

Se 006 è già stata applicata, saltare il comando precedente. Applicare quindi 007 una sola volta:

```powershell
python -m backend.apply_community_migration
python -m backend.app
```

Prerequisiti: migrazioni 002–005 già presenti e poi 006. MySQL esegue commit impliciti sul DDL: se l'esecuzione si interrompe, verificare lo schema/ripristinare la copia invece di ripetere il comando alla cieca. Distribuire il codice Vercel dopo la migrazione, mantenendo il traffico sospeso durante il passaggio.

## Verifiche manuali su una copia del database

1. Caricare altri utenti più volte: nessun ID ripetuto; a fine elenco il bottone scompare. Cambiare ricerca e verificare che l'elenco ricominci.
2. Con utente A pubblicare un commento al contenuto di B; con B rispondere, poi rispondere anche alla risposta.
3. Eliminare il commento di A da A: testo rimosso, risposte di B conservate. Da B non deve esserci l'azione per eliminare il commento di A.
4. Verificare le notifiche del destinatario, il contatore e la lettura all'apertura. Un account diverso non deve poter leggere o modificare notifiche di altri.
5. Come moderatore cambiare stato e verificare la notifica all'autore. Ripetere un sostegno già attivo: non deve generare notifiche duplicate.

## Test automatici

```powershell
python -m pytest backend/tests -q
```

Il test frontend di regressione usa Node e jsdom (dipendenza solo di sviluppo):

```powershell
npm install --prefix .test-tools jsdom --no-audit --no-fund
$env:NODE_PATH = (Resolve-Path .test-tools/node_modules).Path
node frontend/tests/moderation-pagination.cjs
```

I test non accedono ad Aiven. Il test DOM verifica pagine sovrapposte, risposte ripetute, click simultanei e reset della ricerca. Nessun benchmark di carico è stato eseguito.
