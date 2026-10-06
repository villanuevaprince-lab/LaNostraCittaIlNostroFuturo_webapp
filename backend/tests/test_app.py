import pytest

from conftest import csrf_token


def test_health(client):
    assert client.get("/api/health").get_json() == {"status": "ok", "database": "demo"}


def test_homepage_has_link_not_creation_form(client):
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'href="/reports/new"' in html
    assert 'id="report-form"' not in html
    assert 'name="id_autore"' not in html
    assert client.get("/static/css/style.css").status_code == 200
    assert client.get("/static/js/home.js").status_code == 200
    assert client.get("/static/js/forms.js").status_code == 200


@pytest.mark.parametrize("path", [
    "/index.html", "/report_new.html", "/templates/report_new.html",
    "/static/report_new.html", "/static/../templates/report_new.html",
])
def test_no_static_html_bypass(client, path):
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/reports/new", "/dashboard"])
def test_guest_is_sent_to_login(client, path):
    response = client.get(path)
    assert response.status_code == 303
    assert response.location == "/login?next=" + path


def test_guest_cannot_post_with_or_without_csrf(client, submit, report_data):
    before = len(client.get("/api/segnalazioni").get_json())
    assert client.post("/reports/new", data=report_data).status_code == 400
    assert submit("/reports/new", report_data).status_code == 303
    response = client.post("/api/segnalazioni", json=report_data,
                           headers={"X-CSRFToken": csrf_token(client)})
    assert response.status_code == 401
    assert len(client.get("/api/segnalazioni").get_json()) == before


def test_dedicated_page_has_current_author(client, logged_in):
    response = client.get("/reports/new")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'id="report-form"' in html
    assert "Marco Rossi" in html
    assert 'name="id_autore"' not in html
    assert client.get("/dashboard").location == "/"
    assert client.get("/home").location == "/"


def test_publish_redirect_confirmation_and_refresh(client, submit, logged_in, report_data):
    before = len(client.get("/api/segnalazioni").get_json())
    response = submit("/reports/new", {**report_data, "id_autore": "999", "stato": "risolta"})
    assert response.status_code == 303
    assert response.location == "/"
    home = client.get("/").get_data(as_text=True)
    assert "Segnalazione pubblicata correttamente." in home
    refreshed = client.get("/").get_data(as_text=True)
    assert "Segnalazione pubblicata correttamente." not in refreshed
    reports = client.get("/api/segnalazioni").get_json()
    assert len(reports) == before + 1
    assert reports[0]["autore"] == "Marco Rossi"
    assert reports[0]["stato"] == "aperta"


def test_search(client):
    reports = client.get("/api/segnalazioni?q=biciclette").get_json()
    assert len(reports) == 1 and reports[0]["tipo"] == "proposta"


def test_invalid_report_keeps_form_values(client, submit, logged_in, report_data):
    response = submit("/reports/new", {**report_data, "descrizione": "Breve"})
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "Lampione spento" in html
    assert "da 10 a 5000" in html
    assert len(client.get("/api/segnalazioni").get_json()) == 2


def test_report_input_is_escaped(client, submit, logged_in, report_data):
    response = submit("/reports/new", {**report_data, "titolo": "<script>alert(1)</script>",
                                       "descrizione": "Breve"})
    html = response.get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


@pytest.mark.parametrize("body", [None, [], "text", 1, {"titolo": 123},
                                  {"tipo": None}, {"indirizzo": []}, {}])
def test_api_rejects_non_object_and_bad_fields(client, logged_in, body):
    response = client.post("/api/segnalazioni", json=body,
                           headers={"X-CSRFToken": csrf_token(client)})
    assert response.status_code == 400
    assert response.is_json


def test_api_uses_session_author(client, logged_in, report_data):
    response = client.post("/api/segnalazioni",
                           json={**report_data, "id_autore": 999},
                           headers={"X-CSRFToken": csrf_token(client)})
    assert response.status_code == 201
    assert response.get_json()["autore"] == "Marco Rossi"


@pytest.mark.parametrize("field,value", [
    ("titolo", "a" * 201), ("descrizione", "a" * 5001), ("indirizzo", "a" * 256),
    ("tipo", "inesistente"),
])
def test_server_enforces_report_limits(client, submit, logged_in, report_data, field, value):
    assert submit("/reports/new", {**report_data, field: value}).status_code == 400


def test_security_headers(client):
    response = client.get("/")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "form-action 'self'" in response.headers["Content-Security-Policy"]
    assert "Access-Control-Allow-Origin" not in response.headers


def test_demo_stores_are_isolated(app, client, logged_in):
    from backend.app import create_app
    other = create_app({"TESTING": True, "APP_MODE": "demo", "SECRET_KEY": "x" * 32,
                        "RATELIMIT_ENABLED": False})
    assert len(app.extensions["demo_store"]["users"]) == 1
    assert other.extensions["demo_store"]["users"] == {}
