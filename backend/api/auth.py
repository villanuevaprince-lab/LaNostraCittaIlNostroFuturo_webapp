from flask import Blueprint, current_app, g, jsonify, request, session

from backend.forms import LoginForm, RegisterForm
from backend.repositories.catalog import valid_neighborhood
from backend.security import hash_password, limiter, password_hasher, safe_next, start_session, verify_password
from backend.users import (DuplicateEmail, create_user, delete_account, find_user_by_email,
                           update_password_hash, update_profile)


auth_api = Blueprint("auth_api", __name__, url_prefix="/api/auth")


def json_form(form_class, payload):
    form = form_class(formdata=None, data=payload, meta={"csrf": False})
    return form if form.validate() else None


def clean_user(user):
    return {key: user.get(key) for key in
            ("id", "nome", "cognome", "email", "quartiere_id", "stato_account")}


@auth_api.post("/register")
@limiter.limit("5 per minute; 20 per hour")
def register_api():
    payload = request.get_json(silent=True) or request.form.to_dict()
    if not isinstance(payload, dict):
        return jsonify(error="Invia un oggetto JSON valido."), 400
    form = json_form(RegisterForm, payload)
    if form is None:
        candidate = RegisterForm(formdata=None, data=payload, meta={"csrf": False})
        candidate.validate()
        return jsonify(error="Controlla i campi inseriti.", fields=candidate.errors), 400
    try:
        user = create_user(form.nome.data, form.cognome.data, form.email.data,
                           hash_password(form.password.data))
    except DuplicateEmail:
        return jsonify(error="Email già registrata."), 409
    start_session(user)
    return jsonify(user=clean_user(user), redirect=safe_next(payload.get("next"))), 201


@auth_api.post("/login")
@limiter.limit("10 per minute; 100 per hour")
def login_api():
    payload = request.get_json(silent=True) or request.form.to_dict()
    if not isinstance(payload, dict):
        return jsonify(error="Invia un oggetto JSON valido."), 400
    form = json_form(LoginForm, payload)
    if form is None:
        candidate = LoginForm(formdata=None, data=payload, meta={"csrf": False})
        candidate.validate()
        return jsonify(error="Controlla i campi inseriti.", fields=candidate.errors), 400
    user = find_user_by_email(form.email.data)
    stored_hash = user["hash_password"] if user else current_app.extensions["dummy_password_hash"]
    valid = verify_password(stored_hash, form.password.data)
    if not (valid and user and user["stato_account"] == "attivo" and not user["data_cancellazione"]):
        return jsonify(error="Email o password non valide, oppure account non disponibile."), 401
    if not stored_hash.startswith("$argon2id$") or password_hasher.check_needs_rehash(stored_hash):
        update_password_hash(user["id"], hash_password(form.password.data))
    start_session(user)
    return jsonify(user=clean_user(user), redirect=safe_next(payload.get("next")))


@auth_api.post("/logout")
def logout_api():
    session.clear()
    return jsonify(ok=True, redirect="/")


@auth_api.get("/me")
def current_user_api():
    if g.user is None:
        return jsonify(error="Accesso richiesto."), 401
    return jsonify(user=clean_user(g.user))


@auth_api.patch("/me")
def update_me_api():
    if g.user is None:
        return jsonify(error="Accesso richiesto."), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Invia un oggetto JSON valido."), 400
    nome = payload.get("nome", g.user["nome"])
    cognome = payload.get("cognome", g.user["cognome"])
    quartiere_id = payload.get("quartiere_id", g.user.get("quartiere_id"))
    if not isinstance(nome, str) or not nome.strip() or len(nome.strip()) > 100:
        return jsonify(error="Nome obbligatorio, massimo 100 caratteri."), 400
    if not isinstance(cognome, str) or not cognome.strip() or len(cognome.strip()) > 100:
        return jsonify(error="Cognome obbligatorio, massimo 100 caratteri."), 400
    if quartiere_id not in (None, "") and (not str(quartiere_id).isdigit()
                                            or not valid_neighborhood(quartiere_id)):
        return jsonify(error="Quartiere non valido."), 400
    updated = update_profile(g.user["id"], {
        "nome": nome.strip(), "cognome": cognome.strip(),
        "quartiere_id": int(quartiere_id) if quartiere_id not in (None, "") else None,
    })
    return jsonify(user=clean_user(updated))


@auth_api.delete("/me")
def delete_me_api():
    if g.user is None:
        return jsonify(error="Accesso richiesto."), 401
    delete_account(g.user["id"])
    session.clear()
    return jsonify(ok=True, redirect="/")
