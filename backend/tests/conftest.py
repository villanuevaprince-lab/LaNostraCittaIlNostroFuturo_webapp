import re

import mysql.connector
import pytest

from backend.app import create_app


@pytest.fixture(autouse=True)
def never_connect_to_aiven(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("I test non devono mai connettersi ad Aiven.")
    monkeypatch.setattr(mysql.connector, "connect", forbidden)


@pytest.fixture()
def app():
    return create_app({
        "TESTING": True, "APP_MODE": "demo",
        "SECRET_KEY": "only-for-local-tests-" + "x" * 32,
        "RATELIMIT_ENABLED": False,
        "SESSION_COOKIE_SECURE": False,
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
def logged_in(submit, registration):
    response = submit("/register", registration)
    assert response.status_code == 303
    return response


@pytest.fixture()
def report_data():
    return {
        "tipo": "segnalazione", "titolo": "Lampione spento",
        "descrizione": "Il lampione non funziona da alcuni giorni.",
        "indirizzo": "Via Roma, Milano",
    }
