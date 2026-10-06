# Autenticazione e nuova segnalazione

## Scelta architetturale

Il backend Flask è diviso in Blueprint: `auth` per l'accesso, `reports` per
segnalazioni e API, `pages` per la bacheca. I form hanno una validazione condivisa
in `backend/forms.py`; le query utenti sono in `backend/users.py`.

I template HTML Jinja restano nella cartella `frontend/templates`. Stili e
JavaScript sono in `frontend/static`. Flask serve solo quest'ultima come risorse
pubbliche: un file HTML non permette di aggirare il controllo sulla rotta.

## Rotte e protezioni

| Rotta | Metodo | Accesso / risultato |
| --- | --- | --- |
| / | GET | Home pubblica, nessun form per creare segnalazioni |
| /home | GET | Alias con redirect alla home |
| /register | GET, POST | Form, validazione, inserimento, accesso automatico |
| /login | GET, POST | Form, verifica hash e stato account, sessione |
| /logout | POST | CSRF obbligatorio, svuota sessione, redirect home |
| /reports/new | GET, POST | Sessione obbligatoria; form dedicato / creazione |
| /dashboard | GET | Protetta, reindirizza alla home comune |
| /api/segnalazioni | GET, POST | GET pubblico; POST autenticato con CSRF |

Non è stata aggiunta una dashboard duplicata: `/dashboard` è un alias protetto.

## Modello utente

Riutilizza la tabella `UTENTE` già esistente, senza migrazioni:

| Colonna | Tipo | Regola |
| --- | --- | --- |
| IdUtente | INT UNSIGNED | PK autoincrementale |
| Nome, Cognome | VARCHAR(100) | Obbligatori, spazi esterni rimossi |
| Email | VARCHAR(254) | Univoca, normalizzata in minuscolo |
| HashPassword | VARCHAR(255) | Solo hash scrypt con salt, mai password in chiaro |
| DataRegistrazione | DATETIME | Assegnata dal database |
| StatoAccount | VARCHAR(30) | Registrazione sempre attivo |
| DataCancellazione | DATETIME NULL | Un valore impedisce l'accesso |

Password nuove: 12–128 caratteri, conferma uguale; nessun obbligo arbitrario di
simboli o divieto di incollare. Gli hash scrypt e PBKDF2 Werkzeug e gli Argon2
della prima app sono verificabili. Gli hash fittizi del seed sono rifiutati.

## Sessione: cookie anziché JWT

Con frontend e backend sulla stessa origine, la sessione Flask evita di gestire
access token e refresh token nel JavaScript. Il cookie è **firmato, non cifrato**:
contiene l'ID utente, il token CSRF e dati tecnici/messaggi flash, non password,
hash o email. `SECRET_KEY` resta sul server e deve essere casuale e persistente.

Impostazioni: `HttpOnly`, `SameSite=Lax`, durata 2 ore, `Secure=true` su HTTPS.
CSRFProtect controlla tutti i POST, compresi login e logout; il solo SameSite
non sostituisce il token CSRF.

Ogni richiesta carica nuovamente l'utente dal database: blocco o cancellazione
impediscono di continuare a usare una sessione precedente. Login e registrazione
svuotano la sessione anonima prima di impostare l'ID, ruotando anche il token CSRF.
Nessun ruolo, autore o stato dell'account viene accettato dal form.

Il logout rimuove la sessione dal browser. Come per i cookie firmati stateless,
una copia rubata del cookie resta valida fino alla scadenza: per revoca globale
immediata dei dispositivi servirebbe uno store sessioni server-side. Questo
progetto non implementa gestione dispositivi o revoca selettiva.

## Flusso completo

1. Il visitatore apre la home e sceglie “Nuova segnalazione”.
2. `/reports/new` verifica l'accesso: se manca, invia a
   `/login?next=/reports/new`. Da lì può anche aprire la registrazione.
3. Dopo login o registrazione corretti, il server apre la destinazione interna
   richiesta. Senza `next`, apre la home.
4. La pagina dedicata mostra tipo, titolo, descrizione e indirizzo facoltativo;
   il nome dell'autore è mostrato in sola lettura.
5. Il POST controlla sessione, CSRF e campi. Gli errori tornano sullo stesso form,
   conservando i testi validi. Nei form di accesso le password non sono mai riproposte.
6. Solo dopo l'inserimento riuscito viene aggiunta la conferma e inviato un
   `303 See Other` alla home (Post/Redirect/Get).
7. La home mostra il messaggio una sola volta e ricarica l'elenco. Il refresh
   non ripete il POST. Non esiste un modal di creazione.

## Snippet commentati

I file nel repository sono l'implementazione completa. Questi estratti mostrano
i punti principali; non vanno incollati come applicazione indipendente.

### Registrazione

```python
# backend/auth.py
if form.validate_on_submit():
    user = create_user(
        form.nome.data, form.cognome.data, form.email.data,
        generate_password_hash(form.password.data, method="scrypt"),
    )
    start_session(user)          # ID ricavato dal DB, non dal browser
    flash("Registrazione completata.", "success")
    return redirect(destination, code=303)
```

La versione completa gestisce il vincolo UNIQUE sull'email, anche in caso di
inserimenti concorrenti, e limita i tentativi tramite Flask-Limiter.

### Login e sessione

```python
# Dopo validazione form, controllo hash e stato dell'account:
session.clear()                 # Elimina la precedente sessione anonima
session["user_id"] = user["id"]  # Mai memorizzare la password
session.permanent = True
return redirect(safe_next(request.form.get("next")), code=303)
```

La funzione `safe_next` accetta soltanto una piccola lista di rotte interne;
non si reindirizza mai direttamente verso un URL arbitrario inviato dal browser.

### Protezione e creazione

```python
@reports.route("/reports/new", methods=["GET", "POST"])
@login_required
def new_report():
    form = ReportForm()
    if form.validate_on_submit():
        create_report(form.report_data(), author=g.user)
        flash("Segnalazione pubblicata correttamente.", "success")
        return redirect("/", code=303)
    return render_template("report_new.html", form=form), (
        400 if request.method == "POST" else 200
    )
```

L'API POST applica lo stesso controllo e lo stesso form di validazione:
non è possibile pubblicare direttamente da fetch senza autenticazione e CSRF.

### Form HTML

```html
<form method="post" action="{{ url_for('auth.login') }}" data-submit-form>
  {{ form.hidden_tag() }} <!-- Include il token CSRF -->
  <input type="hidden" name="next" value="{{ next_url }}">
  {{ field(form.email, type='email', autocomplete='email', required=true) }}
  {{ field(form.password, autocomplete='current-password', required=true) }}
  <button type="submit" data-busy-label="Accesso in corso…">Accedi</button>
</form>
```

La macro `field` aggiunge label, errori e attributi ARIA. `forms.js` disabilita
temporaneamente il pulsante dopo un invio valido e porta il focus agli errori.
L'autenticazione e la pubblicazione non dipendono da JavaScript.

## Verifiche e limiti

I test usano cookie e token CSRF reali del client Flask, senza disattivare CSRF.
Sono coperti flussi riusciti ed errori, duplicati, account disabilitati, token
scaduti, cookie alterati, tentativi di falsificare l'autore e redirect esterni.
I test SQL verificano binding, commit, rollback e chiusura delle connessioni.
Non sono test live su Aiven: nessuna credenziale remota viene usata.

Per produzione servono HTTPS, server WSGI, rate limiter con storage condiviso,
gestione segreti e verifiche end-to-end nell'ambiente di deployment. Verifica
email, recupero password, SPID/CIE, allegati e moderazione non sono inclusi.

Riferimenti ufficiali:
- [Sicurezza Flask](https://flask.palletsprojects.com/en/stable/web-security/)
- [Hash password Werkzeug](https://werkzeug.palletsprojects.com/en/stable/utils/#module-werkzeug.security)
- [CSRF Flask-WTF](https://flask-wtf.readthedocs.io/en/latest/csrf/)
- [Flask-Limiter](https://flask-limiter.readthedocs.io/en/stable/)
