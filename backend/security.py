"""Sessione firmata Flask e protezioni condivise tra pagine e API."""

from functools import wraps

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from flask import current_app, g, jsonify, redirect, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash

from backend.users import find_user_by_id


csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)


def safe_next(value):
    """Accettiamo solo pagine interne note: niente open redirect."""
    return value if value in {"/", "/home", "/dashboard", "/reports/new"} else "/"


def load_current_user():
    g.user = None
    user_id = session.get("user_id")
    if user_id is None or request.endpoint in {"static", "pages.health"}:
        return
    user = find_user_by_id(user_id)
    # Verifichiamo lo stato a ogni richiesta, non soltanto al login.
    if user and user["stato_account"] == "attivo" and not user["data_cancellazione"]:
        g.user = user
    else:
        session.clear()


def login_required(view):
    @wraps(view)
    def protected(*args, **kwargs):
        if g.user is None:
            if request.path.startswith("/api/"):
                return jsonify(error="Devi accedere prima di pubblicare."), 401
            return redirect(url_for("auth.login", next=request.path), code=303)
        return view(*args, **kwargs)

    return protected


def start_session(user):
    # Rimuove il precedente token CSRF e qualsiasi dato della sessione anonima.
    session.clear()
    session["user_id"] = user["id"]
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
