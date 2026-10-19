"""Test isolati: il codice applicativo usa soltanto MySQL; nessuna rete."""
import re

import mysql.connector
import pytest

from backend.app import create_app
from backend import database
from backend.users import DuplicateEmail


@pytest.fixture(autouse=True)
def never_connect_to_aiven(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("I test non devono mai connettersi ad Aiven.")
    monkeypatch.setattr(mysql.connector, "connect", forbidden)
    monkeypatch.setattr(database, "MySQLConnectionPool", forbidden)


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_MODE", raising=False)
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "only-for-local-tests-" + "x" * 32,
        "RATELIMIT_ENABLED": False,
        "SESSION_COOKIE_SECURE": False,
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
    })


@pytest.fixture()
def client(app):
    return app.test_client()


def csrf_token(client, path="/"):
    response = client.get(path)
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', response.get_data(as_text=True))
    assert match, response.get_data(as_text=True)
    return match.group(1)


@pytest.fixture()
def submit(client):
    def post(path, data=None):
        return client.post(path, data={"csrf_token": csrf_token(client), **(data or {})})
    return post


@pytest.fixture()
def registration():
    return {
        "nome": "Marco", "cognome": "Rossi", "email": "marco@example.com",
        "password": "UnaPassword-Test-123", "password_confirm": "UnaPassword-Test-123",
    }


@pytest.fixture()
def users_stub(monkeypatch):
    """Repository fittizio usato solo dai test delle rotte; non è una modalità dell'app."""
    from backend import auth, security
    from backend.api import auth as auth_api

    users = {}

    def create_user(nome, cognome, email, password_hash):
        key = email.strip().lower()
        if key in users:
            raise DuplicateEmail()
        user = {
            "id": len(users) + 101, "nome": nome, "cognome": cognome,
            "email": key, "hash_password": password_hash, "quartiere_id": None,
            "stato_account": "attivo", "data_cancellazione": None,
        }
        users[key] = user
        return dict(user)

    def find_by_email(email):
        return dict(users[email.lower()]) if email.lower() in users else None

    def find_by_id(user_id):
        return next((dict(user) for user in users.values() if user["id"] == user_id), None)

    def update_hash(user_id, password_hash):
        user = find_by_id(user_id)
        if user:
            users[user["email"]]["hash_password"] = password_hash

    for module in (auth, auth_api):
        monkeypatch.setattr(module, "create_user", create_user)
        monkeypatch.setattr(module, "find_user_by_email", find_by_email)
        monkeypatch.setattr(module, "update_password_hash", update_hash)
    monkeypatch.setattr(security, "find_user_by_id", find_by_id)
    monkeypatch.setattr(security, "has_role", lambda user_id, role="moderatore": False)
    return users


@pytest.fixture()
def logged_in(users_stub, submit, registration):
    response = submit("/register", registration)
    assert response.status_code == 303
    return response


@pytest.fixture()
def report_data():
    return {
        "tipo": "segnalazione", "titolo": "Lampione spento",
        "descrizione": "Il lampione non funziona da alcuni giorni.",
        "indirizzo": "Via Roma, Milano", "quartiere_id": "1", "categoria_id": "1",
        "latitude": "45.464200", "longitude": "9.190000",
    }
