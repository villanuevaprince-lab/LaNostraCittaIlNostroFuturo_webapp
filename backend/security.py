"""Sessione firmata Flask e protezioni condivise tra pagine e API."""

from datetime import datetime
from functools import wraps

from argon2 import PasswordHasher
from argon2 import Type as Argon2Type
from argon2.exceptions import InvalidHashError, VerificationError
from flask import current_app, g, jsonify, redirect, render_template, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash

from backend.users import expire_ban, find_active_ban, find_user_by_id, has_role


csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)
password_hasher = PasswordHasher(type=Argon2Type.ID)


def safe_next(value):
    """Accettiamo solo pagine interne note: niente open redirect."""
    return value if value in {"/", "/home", "/dashboard", "/reports/new", "/profilo", "/moderazione"} else "/"


# Stati con cui si può accedere: un utente bannato entra, ma solo in sola lettura.
LOGIN_STATES = {"attivo", "bloccato"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# Pagine e API in lettura consentite durante il ban: solo l'area personale.
BANNED_READABLE = {
    "static", "pages.health", "pages.profile", "pages.dashboard",
    "auth_api.current_user_api", "auth_api.get_avatar_api", "reports.my_reports",
    "reports.get_states", "reports.get_attachment", "catalog_api.neighborhoods",
    "catalog_api.categories", "auth.login", "auth.register",
}
# Scritture consentite durante il ban: uscita e recupero della password.
BANNED_WRITABLE = {"auth.logout", "auth_api.logout_api", "account.forgot_password", "account.reset_password"}
BANNED_MESSAGE = "Il tuo profilo è stato bannato: finché il ban è attivo puoi solo consultare la tua area personale."


def can_login(user):
    return bool(user) and user["stato_account"] in LOGIN_STATES and not user["data_cancellazione"]


def active_ban(user):
    """Ban in corso per un utente bloccato; i blocchi temporanei scaduti vengono chiusi qui."""
    if user["stato_account"] != "bloccato":
        return None
    ban = find_active_ban(user["id"])
    if ban and ban["data_fine"] is not None and ban["data_fine"] <= datetime.now():
        expire_ban(user["id"], ban["id"])
        user["stato_account"] = "attivo"
        return None
    # Uno stato 'bloccato' senza riga BLOCCO (dati storici) resta comunque un ban.
    return ban or {"id": None, "motivo": None, "data_inizio": None, "data_fine": None}


def load_current_user():
    g.user = None
    user_id = session.get("user_id")
    if user_id is None or request.endpoint in {"static", "pages.health"}:
        return
    user = find_user_by_id(user_id)
    # Verifichiamo stato e ban a ogni richiesta, non soltanto al login: lo sblocco vale subito.
    if can_login(user) and session.get("session_version", 0) == user.get("session_version", 0):
        user["ban"] = active_ban(user)
        user["is_moderator"] = False if user["ban"] else has_role(user["id"])
        g.user = user
    else:
        session.clear()


def enforce_ban():
    """Applicato a tutta l'app dopo load_current_user: il ban si fa rispettare sul server."""
    user = g.get("user")
    if not user or not user.get("ban"):
        return None
    endpoint = request.endpoint or ""
    if endpoint in BANNED_WRITABLE or (request.method in SAFE_METHODS and endpoint in BANNED_READABLE):
        return None
    if request.path.startswith("/api/") or request.method not in SAFE_METHODS:
        return jsonify(error=BANNED_MESSAGE, bannato=True), 403
    return render_template("error.html", message=BANNED_MESSAGE, status=403), 403


def login_required(view):
    @wraps(view)
    def protected(*args, **kwargs):
        if g.user is None:
            if request.path.startswith("/api/"):
                return jsonify(error="Devi accedere prima di pubblicare."), 401
            return redirect(url_for("auth.login", next=request.path), code=303)
        return view(*args, **kwargs)

    return protected


def role_required(role="moderatore"):
    """Autorizza in base al ruolo presente nel DB, mai a un dato del client."""
    def decorator(view):
        @wraps(view)
        @login_required
        def protected(*args, **kwargs):
            from backend.users import has_role
            if not has_role(g.user["id"], role):
                if request.path.startswith("/api/"):
                    return jsonify(error="Permesso insufficiente."), 403
                return current_app.make_response(("Permesso insufficiente.", 403))
            return view(*args, **kwargs)
        return protected
    return decorator


def after_login_destination(user, destination):
    """Un utente bannato atterra sulla propria area personale, l'unica che può consultare."""
    return "/profilo" if user["stato_account"] == "bloccato" else destination


def start_session(user):
    # Rimuove il precedente token CSRF e qualsiasi dato della sessione anonima.
    session.clear()
    session["user_id"] = user["id"]
    session["session_version"] = user.get("session_version", 0)
    session.permanent = True


def verify_password(stored_hash, password):
    """Compatibile con scrypt/PBKDF2 e con gli hash Argon2 della vecchia app."""
    try:
        if stored_hash.startswith("$argon2"):
            return PasswordHasher().verify(stored_hash, password)
        if stored_hash.startswith(("scrypt:", "pbkdf2:")):
            return check_password_hash(stored_hash, password)
    except (ValueError, TypeError, InvalidHashError, VerificationError):
        pass
    # I valori HASH_DEMO_NON_VALIDO del seed non sono credenziali di accesso.
    check_password_hash(current_app.extensions["dummy_password_hash"], password)
    return False


def hash_password(password):
    """I nuovi account vengono salvati con Argon2id."""
    return password_hasher.hash(password)
