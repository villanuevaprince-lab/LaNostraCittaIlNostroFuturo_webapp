from unittest.mock import patch
import time

import pytest
from argon2 import PasswordHasher
from werkzeug.security import check_password_hash

from backend.app import create_app
from conftest import csrf_token


def test_register_hashes_password_and_starts_session(app, client, submit, registration):
    response = submit("/register", {**registration, "email": " MARCO@EXAMPLE.COM "})
    assert response.status_code == 303
    user = next(iter(app.extensions["demo_store"]["users"].values()))
    assert user["email"] == "marco@example.com"
    assert user["hash_password"] != registration["password"]
    assert check_password_hash(user["hash_password"], registration["password"])
    with client.session_transaction() as session:
        assert session["user_id"] == user["id"]
        assert "password" not in session and "email" not in session
    cookie = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_duplicate_email_is_case_insensitive(app, submit, logged_in, registration):
    submit("/logout")
    response = submit("/register", {**registration, "email": "MARCO@example.com"})
    assert response.status_code == 409
    assert len(app.extensions["demo_store"]["users"]) == 1


@pytest.mark.parametrize("updates", [
    {"nome": " "}, {"cognome": " "}, {"email": "non-valida"},
    {"password": "short", "password_confirm": "short"},
    {"password_confirm": "NonCoincide-123"},
    {"password": "x" * 129, "password_confirm": "x" * 129},
])
def test_register_validation(submit, registration, updates):
    response = submit("/register", {**registration, **updates})
    assert response.status_code == 400
    assert registration["password"] not in response.get_data(as_text=True)


def test_login_logout_and_return_to_report(client, submit, logged_in, registration):
    submit("/logout")
    page = client.get("/reports/new")
    login_page = client.get(page.location).get_data(as_text=True)
    assert "/register?next=/reports/new" in login_page
    response = submit("/login", {
        "email": registration["email"], "password": registration["password"],
        "next": "/reports/new",
    })
    assert response.status_code == 303 and response.location == "/reports/new"
    assert client.get(response.location).status_code == 200
    assert client.get("/logout").status_code == 405
    assert submit("/logout").location == "/"
    assert client.get("/reports/new").status_code == 303


def test_signup_also_returns_to_report(submit, registration):
    response = submit("/register", {**registration, "next": "/reports/new"})
    assert response.location == "/reports/new"


def test_wrong_password_and_unknown_email_have_same_response(submit, logged_in, registration):
    submit("/logout")
    known = submit("/login", {"email": registration["email"], "password": "wrong"})
    unknown = submit("/login", {"email": "unknown@example.com", "password": "wrong"})
    message = "Email o password non valide, oppure account non disponibile."
    assert known.status_code == unknown.status_code == 401
    assert message in known.get_data(as_text=True)
    assert message in unknown.get_data(as_text=True)


@pytest.mark.parametrize("status", ["bloccato", "cancellato"])
def test_disabled_accounts_cannot_login(app, submit, logged_in, registration, status):
    submit("/logout")
    user = next(iter(app.extensions["demo_store"]["users"].values()))
    user["stato_account"] = status
    response = submit("/login", {"email": registration["email"], "password": registration["password"]})
    assert response.status_code == 401


def test_existing_session_rechecks_user_status(app, client, logged_in):
    user = next(iter(app.extensions["demo_store"]["users"].values()))
    user["stato_account"] = "bloccato"
    assert client.get("/reports/new").status_code == 303
    with client.session_transaction() as session:
        assert "user_id" not in session


def test_deleted_user_cannot_keep_session(app, client, logged_in):
    app.extensions["demo_store"]["users"].clear()
    assert client.get("/reports/new").status_code == 303


@pytest.mark.parametrize("target", [
    "https://example.org", "//example.org", "/\\example.org", "/login", "/logout", "/%2fevil",
])
def test_open_redirect_is_blocked(submit, registration, target):
    assert submit("/register", {**registration, "next": target}).location == "/"


@pytest.mark.parametrize("path", ["/register", "/login", "/logout", "/reports/new"])
def test_all_forms_require_csrf(client, path):
    assert client.post(path, data={}).status_code == 400


def test_invalid_and_prelogin_csrf_tokens_rejected(client, submit, registration, report_data):
    old_token = csrf_token(client)
    submit("/register", registration)
    for token in ["not-valid", old_token]:
        response = client.post("/reports/new", data={**report_data, "csrf_token": token})
        assert response.status_code == 400
    response = client.post("/api/segnalazioni", json=report_data)
    assert response.status_code == 400 and response.is_json


def test_cookie_tampering_is_rejected(client, logged_in):
    cookie = client.get_cookie("nostra_citta_session")
    client.set_cookie("nostra_citta_session", cookie.value + "tampered")
    assert client.get("/reports/new").status_code == 303


def test_expired_session_cannot_access_form(app, client, logged_in):
    cookie = client.get_cookie("nostra_citta_session")
    with patch("itsdangerous.timed.time.time", return_value=time.time() + 3 * 3600):
        client.set_cookie("nostra_citta_session", cookie.value)
        assert client.get("/reports/new").status_code == 303


def test_expired_csrf_is_rejected(app, client, report_data, logged_in):
    token = csrf_token(client)
    app.config["WTF_CSRF_TIME_LIMIT"] = -1
    response = client.post("/reports/new", data={**report_data, "csrf_token": token})
    assert response.status_code == 400


@pytest.mark.parametrize("stored_hash", ["HASH_DEMO_NON_VALIDO_1", "$argon2-invalid"])
def test_seed_placeholders_are_not_passwords(app, submit, logged_in, registration, stored_hash):
    submit("/logout")
    user = next(iter(app.extensions["demo_store"]["users"].values()))
    user["hash_password"] = stored_hash
    assert submit("/login", {"email": user["email"], "password": stored_hash}).status_code == 401


def test_existing_argon2_passwords_still_work(app, submit, logged_in, registration):
    submit("/logout")
    user = next(iter(app.extensions["demo_store"]["users"].values()))
    user["hash_password"] = PasswordHasher().hash(registration["password"])
    response = submit("/login", {"email": user["email"], "password": registration["password"]})
    assert response.status_code == 303


def test_login_rate_limit():
    app = create_app({"TESTING": True, "APP_MODE": "demo", "SECRET_KEY": "x" * 32,
                      "RATELIMIT_ENABLED": True, "SESSION_COOKIE_SECURE": False})
    client = app.test_client()
    token = csrf_token(client)
    for _ in range(10):
        response = client.post("/login", data={"csrf_token": token,
                              "email": "unknown@example.com", "password": "bad-password"})
        assert response.status_code == 401
    assert client.post("/login", data={"csrf_token": token}).status_code == 429


def test_secure_cookie_for_https(app, client, logged_in):
    app.config["SESSION_COOKIE_SECURE"] = True
    response = client.get("/", base_url="https://localhost")
    # La home consuma il messaggio flash e salva di nuovo la sessione.
    assert "Secure" in response.headers.get("Set-Cookie", "")


def test_database_mode_requires_secret(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app({"APP_MODE": "database", "SECRET_KEY": None})
