# API REST

Tutte le risposte di errore seguono il formato:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "I dati inviati non sono validi.",
    "details": {}
  }
}
```

Le richieste `POST`, `PUT`, `PATCH` e `DELETE` devono includere `X-CSRF-Token`. Il token si ottiene da `GET /api/auth/csrf`. L'autenticazione usa la sessione cookie.

## Sistema

| Metodo | Percorso | Accesso | Descrizione |
|---|---|---|---|
| GET | `/api/health` | Pubblico | Stato server e database |
| GET | `/api/metadata` | Pubblico | Quartieri, categorie e stati |
| GET | `/api/files/:fileName` | Pubblico | Allegato di una segnalazione pubblica |

## Autenticazione e profilo

| Metodo | Percorso | Accesso | Descrizione |
|---|---|---|---|
| GET | `/api/auth/csrf` | Pubblico | Inizializza sessione e token CSRF |
| POST | `/api/auth/register` | Pubblico + CSRF | Registra e autentica l'utente |
| POST | `/api/auth/login` | Pubblico + CSRF | Avvia una nuova sessione |
| POST | `/api/auth/logout` | Autenticato | Termina la sessione |
| GET | `/api/auth/me` | Pubblico | Restituisce l'utente corrente o `null` |
| PUT | `/api/auth/me` | Autenticato | Modifica nome, cognome e quartiere |
| DELETE | `/api/auth/me` | Autenticato | Cancella logicamente l'account |

## Segnalazioni

| Metodo | Percorso | Accesso | Descrizione |
|---|---|---|---|
| GET | `/api/reports` | Pubblico | Elenco paginato e filtrato |
| POST | `/api/reports` | Autenticato | Crea con `multipart/form-data` e campo `allegato` |
| GET | `/api/reports/:id` | Pubblico | Dettaglio, allegati, commenti e storico |
| POST | `/api/reports/:id/comments` | Autenticato | Pubblica un commento |
| PUT | `/api/reports/:id/support` | Autenticato | Aggiunge o riattiva il sostegno |
| DELETE | `/api/reports/:id/support` | Autenticato | Ritira il sostegno |
| PATCH | `/api/reports/:id/state` | Moderatore | Cambia stato e registra lo storico |
| DELETE | `/api/reports/:id` | Autore o moderatore | Rimozione logica |

Filtri accettati da `GET /api/reports`: `q`, `tipo`, `stato`, `idQuartiere`, `idCategoria`, `ordine`, `pagina`, `limite`.

Il campo `categorie` della creazione è un array JSON con uno-cinque ID. Foto e video supportati: JPG, PNG, WebP, MP4 e WebM.

## Moderazione

| Metodo | Percorso | Accesso | Descrizione |
|---|---|---|---|
| GET | `/api/moderation/users` | Moderatore | Elenca e ricerca utenti |
| POST | `/api/moderation/users/:id/block` | Moderatore | Blocca un account |
| POST | `/api/moderation/users/:id/unblock` | Moderatore | Revoca il blocco più recente |
| DELETE | `/api/moderation/comments/:id` | Moderatore | Rimuove logicamente un commento |
| GET | `/api/moderation/events` | Moderatore | Ultimi 50 eventi di audit |
