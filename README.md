# La Nostra Città, Il Nostro Futuro

Applicazione web semplice per pubblicare e cercare segnalazioni e proposte cittadine.
Il progetto è diviso chiaramente in un backend Flask e un frontend realizzato con
HTML, CSS e JavaScript senza framework.

## Funzioni disponibili

- visualizzazione delle segnalazioni e delle proposte;
- ricerca per titolo, descrizione o indirizzo;
- inserimento di un nuovo contenuto;
- validazione dei dati sia nel browser sia nel backend;
- modalità demo utilizzabile senza configurazione;
- collegamento opzionale al database MySQL già presente su Aiven.

## Struttura

```text
backend/
├── app.py                 API Flask e server del frontend
├── database.py            accesso ad Aiven e dati demo
├── requirements.txt       dipendenze Python
└── tests/
    └── test_app.py        test API

frontend/
├── index.html
├── css/
│   └── style.css
└── js/
    └── app.js

database/                  schema, migrazioni e dati di riferimento
docs/api.md                descrizione delle API
```

## Avvio rapido in modalità demo

Richiede Python 3.10 o successivo.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python -m backend.app
```

Su Windows, l'attivazione dell'ambiente virtuale è:

```powershell
.venv\Scripts\activate
```

Apri [http://localhost:5000](http://localhost:5000).

## Collegamento al database Aiven

1. Copia `.env.example` in `.env`.
2. Imposta `APP_MODE=database`.
3. Inserisci host, porta, utente e password mostrati nella pagina del servizio Aiven.
4. Se usi la verifica TLS, salva il certificato in `certificates/ca.pem`.
5. Avvia nuovamente Flask.

L'app non crea e non modifica automaticamente lo schema. Per il database già
esistente rimangono disponibili gli script nella cartella `database/`.

## Test

```bash
pytest -q
```

I test utilizzano soltanto la modalità demo e non modificano il database Aiven.
