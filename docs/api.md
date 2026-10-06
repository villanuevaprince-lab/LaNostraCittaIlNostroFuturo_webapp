# API essenziale

## `GET /api/health`

Restituisce lo stato del server e indica se l'app usa i dati dimostrativi o Aiven.

## `GET /api/segnalazioni`

Restituisce le segnalazioni pubbliche. Il parametro facoltativo `q` filtra titolo,
descrizione e indirizzo.

Esempio:

```text
GET /api/segnalazioni?q=lampione
```
## `POST /api/segnalazioni`

Inserisce una segnalazione o una proposta.

```json
{
  "id_autore": 1,
  "tipo": "segnalazione",
  "titolo": "Lampione spento",
  "descrizione": "Il lampione non funziona da alcuni giorni.",
  "indirizzo": "Via Roma, Milano"
}
```
