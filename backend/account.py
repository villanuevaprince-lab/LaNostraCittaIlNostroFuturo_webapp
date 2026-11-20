"""Recupero password e cambio email con link firmati inviati per email.

I token usano itsdangerous (URLSafeTimedSerializer, firmati con SECRET_KEY e con scadenza).
Sono monouso senza tabelle aggiuntive: il token di reset contiene un'impronta dell'hash
della password, che cambia appena la password viene reimpostata; quello di cambio email
contiene l'indirizzo attuale, che non corrisponde più dopo la conferma.
"""

import hashlib
import hmac
from functools import wraps

from flask import (Blueprint, current_app, flash, g, jsonify, make_response, redirect, render_template,
                   request, session, url_for)
from flask_wtf import FlaskForm
from itsdangerous import BadSignature, URLSafeTimedSerializer

from backend.forms import EmailChangeForm, ForgotPasswordForm, ResetPasswordForm, normalize_email
from backend.security import can_login, hash_password, limiter, login_required, verify_password
from backend.services.mailer import MailError, absolute_url, send_email
from backend.users import (DuplicateEmail, change_email, find_user_by_email, find_user_by_id,
                           reset_password_hash)


account = Blueprint("account", __name__)

RESET_SALT = "password-reset"
EMAIL_SALT = "email-change"
FORGOT_MESSAGE = ("Se l'indirizzo corrisponde a un account, riceverai a breve un'email con il link "
                  "per reimpostare la password. Controlla anche la cartella spam.")
EMAIL_CHANGE_MESSAGE = ("Se l'indirizzo è disponibile, ti abbiamo inviato un link di conferma. "
                        "L'email cambierà solo dopo la conferma.")


def _serializer(salt):
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=salt)


def _fingerprint(user):
    material = f"{user['hash_password']}|{user.get('session_version', 0)}"
    return hashlib.sha256(material.encode()).hexdigest()[:32]


def _load(token, salt, max_age):
    try:
        data = _serializer(salt).loads(token, max_age=max_age)
    except BadSignature:  # comprende anche SignatureExpired
        return None
    return data if isinstance(data, dict) else None


def _minutes(seconds):
    return max(1, int(seconds) // 60)


def no_referrer(view):
    """Le pagine con token nell'URL non lo passano mai ad altri siti tramite Referer."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
    return wrapped


def _notify(to, subject, body):
    try:
        send_email(to, subject, body)
    except MailError:
        pass  # avviso di cortesia: l'operazione principale è già riuscita


def _reset_email_key():
    return "reset-email:" + normalize_email(request.form.get("email", ""))


# --- Password dimenticata --------------------------------------------------

@account.route("/password/dimenticata", methods=["GET", "POST"])
@limiter.limit("5 per minute; 20 per hour", methods=["POST"])
@limiter.limit("3 per hour", key_func=_reset_email_key, methods=["POST"])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = find_user_by_email(form.email.data)
        if can_login(user):
            token = _serializer(RESET_SALT).dumps({"u": user["id"], "f": _fingerprint(user)})
            link = absolute_url(url_for("account.reset_password", token=token))
            minutes = _minutes(current_app.config["PASSWORD_RESET_MAX_AGE"])
            try:
                send_email(user["email"], "Reimposta la password — La Nostra Città",
                           f"Ciao {user['nome']},\n\nabbiamo ricevuto una richiesta di reimpostare la password "
                           f"del tuo account. Apri questo link entro {minutes} minuti:\n\n{link}\n\n"
                           "Il link funziona una sola volta. Se non hai chiesto tu il reset, ignora questa email: "
                           "la password resta invariata.\n")
            except MailError:
                pass  # stessa risposta in ogni caso: non riveliamo nulla sull'account
        # Stessa pagina e stesso codice per email registrate e non registrate.
        return render_template("forgot_password.html", form=ForgotPasswordForm(formdata=None), sent=True)
    status = 400 if request.method == "POST" else 200
    return render_template("forgot_password.html", form=form, sent=False), status


@account.route("/password/reimposta/<token>", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
@no_referrer
def reset_password(token):
    data = _load(token, RESET_SALT, current_app.config["PASSWORD_RESET_MAX_AGE"])
    user = find_user_by_id(data.get("u")) if data and isinstance(data.get("u"), int) else None
    if not (can_login(user) and hmac.compare_digest(_fingerprint(user), str(data.get("f", "")))):
        return render_template("reset_password.html", form=None, invalid=True), 400
    form = ResetPasswordForm()
    if form.validate_on_submit():
        if not reset_password_hash(user["id"], user["hash_password"], hash_password(form.password.data)):
            return render_template("reset_password.html", form=None, invalid=True), 400
        session.clear()  # anche la sessione corrente, se presente: si rientra con la nuova password
        _notify(user["email"], "La tua password è stata cambiata — La Nostra Città",
                f"Ciao {user['nome']},\n\nla password del tuo account è stata appena reimpostata e tutte le "
                "sessioni aperte sono state chiuse.\nSe non sei stato tu, reimposta subito la password e "
                "contatta il comitato.\n")
        flash("Password aggiornata. Accedi con la nuova password.", "success")
        return redirect(url_for("auth.login"), code=303)
    status = 400 if request.method == "POST" else 200
    return render_template("reset_password.html", form=form, invalid=False), status


# --- Cambio email ----------------------------------------------------------

@account.post("/api/auth/me/email")
@login_required
@limiter.limit("5 per hour")
def request_email_change():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Invia un oggetto JSON valido."), 400
    form = EmailChangeForm(formdata=None, data=payload, meta={"csrf": False})
    if not form.validate():
        return jsonify(error="Controlla i campi inseriti.", fields=form.errors), 400
    if not verify_password(g.user["hash_password"], form.password.data):
        return jsonify(error="Password attuale non corretta."), 400
    new_email = form.nuova_email.data
    if new_email == g.user["email"].lower():
        return jsonify(error="È già il tuo indirizzo attuale."), 400
    # Se l'indirizzo è già usato non inviamo nulla, ma la risposta resta identica.
    if find_user_by_email(new_email) is None:
        token = _serializer(EMAIL_SALT).dumps({"u": g.user["id"], "old": g.user["email"].lower(), "new": new_email})
        link = absolute_url(url_for("account.confirm_email", token=token))
        minutes = _minutes(current_app.config["EMAIL_CHANGE_MAX_AGE"])
        try:
            send_email(new_email, "Conferma il nuovo indirizzo email — La Nostra Città",
                       f"Ciao {g.user['nome']},\n\nper usare questo indirizzo nel tuo account apri il link "
                       f"entro {minutes} minuti e conferma:\n\n{link}\n\n"
                       "Se non hai chiesto tu il cambio, ignora questa email.\n")
        except MailError:
            return jsonify(error="Non è stato possibile inviare l'email di conferma. Riprova più tardi."), 503
    return jsonify(ok=True, message=EMAIL_CHANGE_MESSAGE)


@account.route("/email/conferma/<token>", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
@no_referrer
def confirm_email(token):
    data = _load(token, EMAIL_SALT, current_app.config["EMAIL_CHANGE_MAX_AGE"])
    user = find_user_by_id(data.get("u")) if data and isinstance(data.get("u"), int) else None
    valid = (user is not None and user["stato_account"] == "attivo" and not user["data_cancellazione"]
             and isinstance(data.get("new"), str) and user["email"].lower() == data.get("old"))
    if not valid:
        return render_template("confirm_email.html", form=None, invalid=True, new_email=None), 400
    # GET mostra solo un pulsante: i controlli automatici dei link nelle caselle email non confermano nulla.
    form = FlaskForm()
    if form.validate_on_submit():
        try:
            changed = change_email(user["id"], data["old"], data["new"])
        except DuplicateEmail:
            return render_template("confirm_email.html", form=None, invalid=True, new_email=None,
                                   message="Questo indirizzo è già usato da un altro account."), 409
        if not changed:
            return render_template("confirm_email.html", form=None, invalid=True, new_email=None), 400
        _notify(data["old"], "Il tuo indirizzo email è cambiato — La Nostra Città",
                f"Ciao {user['nome']},\n\nl'email del tuo account è stata cambiata in {data['new']}.\n"
                "Se non sei stato tu, contatta subito il comitato.\n")
        flash("Indirizzo email aggiornato. Usalo per i prossimi accessi.", "success")
        return redirect("/profilo" if g.user else url_for("auth.login"), code=303)
    return render_template("confirm_email.html", form=form, invalid=False, new_email=data["new"])
