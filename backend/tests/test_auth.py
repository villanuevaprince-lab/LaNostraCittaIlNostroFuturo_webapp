"""Form e sessioni testati con repository simulato; l'app non ha uno store demo."""
from unittest.mock import patch
import time

import pytest
from argon2 import PasswordHasher

from backend.app import create_app
from backend.database import ROOT_DIR
from conftest import csrf_token


def test_register_hashes_password_and_starts_session(client, users_stub, submit, registration):
    response = submit("/register", {**registration, "email": " MARCO@EXAMPLE.COM "})
    assert response.status_code == 303
    user = users_stub["marco@example.com"]
    assert user["hash_password"].startswith("$argon2id$")
    assert PasswordHasher().verify(user["hash_password"], registration["password"])
    with client.session_transaction() as session:
        assert session["user_id"] == user["id"]
        assert "password" not in session and "email" not in session
    assert "HttpOnly" in response.headers["Set-Cookie"]
    assert "SameSite=Lax" in response.headers["Set-Cookie"]


def test_duplicate_email_is_case_insensitive(submit, logged_in, users_stub, registration):
    submit("/logout")
    response = submit("/register", {**registration, "email": "MARCO@example.com"})
    assert response.status_code == 409 and len(users_stub) == 1


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
    assert "/register?next=/reports/new" in client.get(page.location).get_data(as_text=True)
    response = submit("/login", {
        "email": registration["email"], "password": registration["password"],
        "next": "/reports/new",
    })
    assert response.status_code == 303 and response.location == "/reports/new"
    assert client.get(response.location).status_code == 200
    assert client.get("/logout").status_code == 405
    assert submit("/logout").location == "/"
    assert client.get("/reports/new").status_code == 303


def test_signup_also_returns_to_report(submit, users_stub, registration):
    assert submit("/register", {**registration, "next": "/reports/new"}).location == "/reports/new"


def test_wrong_password_and_unknown_email_have_same_response(submit, logged_in, registration):
    submit("/logout")
    known = submit("/login", {"email": registration["email"], "password": "wrong"})
    unknown = submit("/login", {"email": "unknown@example.com", "password": "wrong"})
    message = "Email o password non valide, oppure account non disponibile."
    assert known.status_code == unknown.status_code == 401
    assert message in known.get_data(as_text=True) and message in unknown.get_data(as_text=True)


@pytest.mark.parametrize("status", ["bloccato", "cancellato"])
def test_disabled_accounts_cannot_login(submit, logged_in, users_stub, registration, status):
    submit("/logout")
    users_stub[registration["email"]]["stato_account"] = status
    assert submit("/login", {"email": registration["email"],
                             "password": registration["password"]}).status_code == 401


def test_existing_session_rechecks_user_status(client, logged_in, users_stub, registration):
    users_stub[registration["email"]]["stato_account"] = "bloccato"
    assert client.get("/reports/new").status_code == 303
    with client.session_transaction() as session:
        assert "user_id" not in session


def test_deleted_user_cannot_keep_session(client, logged_in, users_stub):
    users_stub.clear()
    assert client.get("/reports/new").status_code == 303


@pytest.mark.parametrize("target", [
    "https://example.org", "//example.org", "/\\example.org", "/login", "/logout", "/%2fevil",
])
def test_open_redirect_is_blocked(submit, users_stub, registration, target):
    assert submit("/register", {**registration, "next": target}).location == "/"


@pytest.mark.parametrize("path", ["/register", "/login", "/logout", "/api/segnalazioni"])
def test_all_forms_require_csrf(client, path):
    assert client.post(path, data={}).status_code == 400


def test_invalid_and_prelogin_csrf_tokens_rejected(client, submit, users_stub, registration, report_data):
    old_token = csrf_token(client)
    submit("/register", registration)
    for token in ["not-valid", old_token]:
        assert client.post("/api/segnalazioni", data={**report_data,
                                                "csrf_token": token}).status_code == 400
    response = client.post("/api/segnalazioni", json=report_data)
    assert response.status_code == 400 and response.is_json


def test_cookie_tampering_is_rejected(client, logged_in):
    cookie = client.get_cookie("nostra_citta_session")
    client.set_cookie("nostra_citta_session", cookie.value + "tampered")
    assert client.get("/reports/new").status_code == 303


def test_expired_session_cannot_access_form(client, logged_in):
    cookie = client.get_cookie("nostra_citta_session")
    with patch("itsdangerous.timed.time.time", return_value=time.time() + 3 * 3600):
        client.set_cookie("nostra_citta_session", cookie.value)
        assert client.get("/reports/new").status_code == 303


def test_expired_csrf_is_rejected(app, client, report_data, logged_in):
    token = csrf_token(client)
    app.config["WTF_CSRF_TIME_LIMIT"] = -1
    assert client.post("/api/segnalazioni", data={**report_data, "csrf_token": token}).status_code == 400


@pytest.mark.parametrize("stored_hash", ["HASH_DEMO_NON_VALIDO_1", "$argon2-invalid"])
def test_seed_placeholders_are_not_passwords(submit, logged_in, users_stub, registration, stored_hash):
    submit("/logout")
    users_stub[registration["email"]]["hash_password"] = stored_hash
    assert submit("/login", {"email": registration["email"],
                             "password": stored_hash}).status_code == 401


def test_existing_argon2_passwords_still_work(submit, logged_in, users_stub, registration):
    submit("/logout")
    users_stub[registration["email"]]["hash_password"] = PasswordHasher().hash(registration["password"])
    assert submit("/login", {"email": registration["email"],
                             "password": registration["password"]}).status_code == 303


def test_login_rate_limit(monkeypatch, users_stub):
    monkeypatch.delenv("APP_MODE", raising=False)
    app = create_app({"TESTING": True, "SECRET_KEY": "x" * 32,
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
    assert "Secure" in response.headers.get("Set-Cookie", "")


def test_secret_is_required(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.delenv("APP_MODE", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app({"SECRET_KEY": None})


def test_demo_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("APP_MODE", "demo")
    with pytest.raises(RuntimeError, match="non è disponibile"):
        create_app({"SECRET_KEY": "x" * 32})


def test_relative_upload_path_is_stable_across_working_directories(monkeypatch, tmp_path):
    monkeypatch.delenv("APP_MODE", raising=False)
    monkeypatch.setenv("UPLOAD_FOLDER", "storage/uploads")
    monkeypatch.chdir(tmp_path)
    app = create_app({"TESTING": True, "SECRET_KEY": "x" * 32,
                      "RATELIMIT_ENABLED": False})
    assert app.config["UPLOAD_FOLDER"] == str((ROOT_DIR / "storage/uploads").resolve())
