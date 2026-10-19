from flask import Blueprint, current_app, g, jsonify, request, send_file, session

from backend.forms import LoginForm, RegisterForm
from backend.repositories.catalog import valid_neighborhood
from backend.security import hash_password, limiter, password_hasher, safe_next, start_session, verify_password
from backend.services.avatars import avatar_path, save_avatar
from backend.users import (DuplicateEmail, create_user, delete_account, find_user_by_email,
                           find_user_by_id, update_password_hash, update_profile,
                           change_password_hash, set_avatar_reference)


auth_api = Blueprint("auth_api", __name__, url_prefix="/api/auth")


def json_form(form_class, payload):
    form = form_class(formdata=None, data=payload, meta={"csrf": False})
    return form if form.validate() else None


def clean_user(user):
    return {key: user.get(key) for key in
            ("id", "nome", "cognome", "email", "quartiere_id", "stato_account",
             "bio", "notifiche_email", "avatar_riferimento")}


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
    bio = payload.get("bio", g.user.get("bio") or "")
    notifications = payload.get("notifiche_email", bool(g.user.get("notifiche_email")))
    if not isinstance(nome, str) or not nome.strip() or len(nome.strip()) > 100:
        return jsonify(error="Nome obbligatorio, massimo 100 caratteri."), 400
    if not isinstance(cognome, str) or not cognome.strip() or len(cognome.strip()) > 100:
        return jsonify(error="Cognome obbligatorio, massimo 100 caratteri."), 400
    if quartiere_id not in (None, "") and (not str(quartiere_id).isdigit()
                                            or not valid_neighborhood(quartiere_id)):
        return jsonify(error="Quartiere non valido."), 400
    if not isinstance(bio, str) or len(bio.strip()) > 500:
        return jsonify(error="La biografia non può superare 500 caratteri."), 400
    if not isinstance(notifications, bool):
        return jsonify(error="La preferenza delle notifiche non è valida."), 400
    updated = update_profile(g.user["id"], {
        "nome": nome.strip(), "cognome": cognome.strip(),
        "quartiere_id": int(quartiere_id) if quartiere_id not in (None, "") else None,
        "bio": bio.strip(), "notifiche_email": notifications,
    })
    return jsonify(user=clean_user(updated))


@auth_api.post("/me/password")
@limiter.limit("5 per hour")
def change_password_api():
    if g.user is None:
        return jsonify(error="Accesso richiesto."), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Invia un oggetto JSON valido."), 400
    old, new, confirmation = (payload.get(key) for key in
                               ("password_attuale", "nuova_password", "conferma_password"))
    if not isinstance(old, str) or not verify_password(g.user["hash_password"], old):
        return jsonify(error="Password attuale non corretta."), 400
    if not isinstance(new, str) or not 12 <= len(new) <= 128 or new != confirmation or new == old:
        return jsonify(error="La nuova password deve essere diversa, di 12–128 caratteri, e confermata."), 400
    if not change_password_hash(g.user["id"], g.user["hash_password"], hash_password(new)):
        return jsonify(error="Password modificata da un'altra sessione. Riprova."), 409
    g.user["session_version"] = g.user.get("session_version", 0) + 1
    start_session(g.user)  # rinnova sessione e token CSRF dopo la modifica
    return jsonify(ok=True, redirect="/profilo")


@auth_api.post("/me/avatar")
@limiter.limit("10 per hour")
def upload_avatar_api():
    if g.user is None:
        return jsonify(error="Accesso richiesto."), 401
    try:
        reference = save_avatar(request.files.get("avatar"))
    except ValueError as error:
        return jsonify(error=str(error)), 400
    try:
        if not set_avatar_reference(g.user["id"], reference):
            avatar_path(reference).unlink(missing_ok=True)
            return jsonify(error="Account non disponibile."), 409
    except Exception:
        avatar_path(reference).unlink(missing_ok=True)
        raise
    old = avatar_path(g.user.get("avatar_riferimento"))
    if old:
        old.unlink(missing_ok=True)
    return jsonify(ok=True, avatar_url=f"/api/auth/avatar/{g.user['id']}")


@auth_api.get("/avatar/<int:user_id>")
def get_avatar_api(user_id):
    user = find_user_by_id(user_id)
    path = avatar_path(user.get("avatar_riferimento")) if user else None
    if not path or not path.is_file():
        return jsonify(error="Avatar non trovato."), 404
    return send_file(path, mimetype="image/webp", conditional=True, max_age=300)


@auth_api.delete("/me")
def delete_me_api():
    if g.user is None:
        return jsonify(error="Accesso richiesto."), 401
    delete_account(g.user["id"])
    session.clear()
    return jsonify(ok=True, redirect="/")
