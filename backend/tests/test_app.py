import pytest

from backend.app import create_app


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("APP_MODE", "demo")
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_health(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "database": "demo"}


def test_frontend_is_served(client):
    page = client.get("/")
    stylesheet = client.get("/css/style.css")
    script = client.get("/js/app.js")

    assert page.status_code == 200
    assert "Miglioriamo insieme la nostra città" in page.get_data(as_text=True)
    assert stylesheet.status_code == 200
    assert script.status_code == 200


def test_search_reports(client):
    response = client.get("/api/segnalazioni?q=biciclette")

    assert response.status_code == 200
    reports = response.get_json()
    assert len(reports) == 1
    assert reports[0]["tipo"] == "proposta"


def test_create_report(client):
    response = client.post(
        "/api/segnalazioni",
        json={
            "id_autore": 1,
            "tipo": "segnalazione",
            "titolo": "Lampione spento",
            "descrizione": "Il lampione non funziona da alcuni giorni.",
            "indirizzo": "Via Roma, Milano",
        },
    )

    assert response.status_code == 201
    assert response.get_json()["titolo"] == "Lampione spento"


def test_rejects_invalid_report(client):
    response = client.post(
        "/api/segnalazioni",
        json={"id_autore": 0, "tipo": "altro", "titolo": "No", "descrizione": "Breve"},
    )

    assert response.status_code == 400
    assert set(response.get_json()["fields"]) == {
        "id_autore",
        "tipo",
        "titolo",
        "descrizione",
    }
