"""Flussi HTTP senza connessioni reali; query e commit sono testati a parte."""
from io import BytesIO
from unittest.mock import Mock

from PIL import Image
import pytest

from conftest import csrf_token


def make_image():
    buffer = BytesIO()
    Image.new("RGB", (16, 16), "green").save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer


def test_catalogs_are_read_from_repository(client, monkeypatch):
    from backend.services import catalog
    get_neighborhoods = Mock(return_value=[{"id": 11, "nome": "Adriano"}])
    get_categories = Mock(return_value=[{"id": 3, "nome": "Decoro urbano"}])
    monkeypatch.setattr(catalog, "list_neighborhoods", get_neighborhoods)
    monkeypatch.setattr(catalog, "list_categories", get_categories)
    assert client.get("/api/quartieri").get_json() == [{"id": 11, "nome": "Adriano"}]
    assert client.get("/api/categorie").get_json()[0]["nome"] == "Decoro urbano"
    assert get_neighborhoods.call_count == get_categories.call_count == 2


def test_homepage_has_filters_and_separate_creation_page(client):
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'href="/reports/new"' in html
    assert 'id="report-form"' not in html
    assert 'id="filter-category"' in html and 'id="sort-reports"' in html
    assert "Modalità demo" not in html


@pytest.mark.parametrize("path", [
    "/index.html", "/report_new.html", "/templates/report_new.html",
    "/static/report_new.html", "/static/../templates/report_new.html",
])
def test_no_static_html_bypass(client, path):
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/reports/new", "/dashboard", "/profilo"])
def test_guest_is_sent_to_login(client, path):
    response = client.get(path)
    assert response.status_code == 303 and response.location == "/login?next=" + path


def test_dashboard_and_form_after_login(client, logged_in):
    assert client.get("/dashboard").status_code == 200
    assert client.get("/profilo").status_code == 200
    html = client.get("/reports/new").get_data(as_text=True)
    assert "Marco Rossi" in html and 'name="categoria_id"' in html
    assert 'name="latitude"' not in html and 'name="longitude"' not in html
    assert 'name="descrizione_accessibile"' not in html


def test_report_list_queries_repository(client, monkeypatch, logged_in):
    from backend import reports
    rows = [{"id": 4, "titolo": "Lampione", "sostegni": 2}]
    query = Mock(return_value=rows)
    monkeypatch.setattr(reports, "list_report_records", query)
    assert client.get("/api/segnalazioni?ordina=no").status_code == 400
    assert client.get("/api/segnalazioni?ordina=sostegni&q=lampione&mie=1").get_json() == rows
    assert query.call_args.args[0] == "lampione"
    assert query.call_args.args[-2:] == (101, "sostegni")


def test_guest_cannot_publish(client, report_data):
    response = client.post("/api/segnalazioni", data=report_data,
                           headers={"X-CSRFToken": csrf_token(client)})
    assert response.status_code == 401


def test_report_requires_attachment(client, logged_in, report_data, monkeypatch):
    from backend.services import reports as service
    monkeypatch.setattr(service, "valid_neighborhood", lambda _: True)
    monkeypatch.setattr(service, "valid_categories", lambda _: True)
    response = client.post("/api/segnalazioni", data=report_data,
                           headers={"X-CSRFToken": csrf_token(client)})
    assert response.status_code == 400
    assert "allega" in response.get_json()["error"].lower()


def test_report_publication_passes_session_author(client, logged_in, report_data, monkeypatch):
    from backend.services import reports as service
    monkeypatch.setattr(service, "valid_neighborhood", lambda _: True)
    monkeypatch.setattr(service, "valid_categories", lambda _: True)
    insert = Mock(return_value={"id": 42, "stato": "aperta"})
    monkeypatch.setattr(service, "create_report_record", insert)
    response = client.post("/api/segnalazioni", data={
        **report_data, "id_autore": "999", "latitude": "999", "longitude": "999",
        "allegato": (make_image(), "photo.jpg"),
    }, headers={"X-CSRFToken": csrf_token(client)}, content_type="multipart/form-data")
    assert response.status_code == 201 and response.get_json()["redirect"] == "/"
    data, author, upload = insert.call_args.args
    assert author["id"] == 101 and data["latitude"] is None and data["longitude"] is None
    assert upload["path"].is_file()
    assert "Segnalazione pubblicata correttamente." in client.get("/").get_data(as_text=True)


def test_comments_and_support_use_repository(client, logged_in, monkeypatch):
    from backend import reports
    monkeypatch.setattr(reports, "get_report_record", lambda _: {"id": 1, "visibilita": "pubblica"})
    monkeypatch.setattr(reports, "report_comments", lambda _: [])
    insert_comment = Mock(return_value={"id": 9, "testo": "Confermo", "autore": "Marco Rossi"})
    support = Mock(return_value={"sostenuta": True, "sostegni": 1})
    monkeypatch.setattr(reports, "add_comment", insert_comment)
    monkeypatch.setattr(reports, "set_support", support)
    token = csrf_token(client)
    comment = client.post("/api/segnalazioni/1/commenti", json={"testo": "Confermo"},
                          headers={"X-CSRFToken": token})
    assert comment.status_code == 201 and insert_comment.call_args.args == (1, 101, "Confermo")
    for _ in range(2):
        response = client.put("/api/segnalazioni/1/sostegno", headers={"X-CSRFToken": token})
        assert response.status_code == 200 and response.get_json()["sostegni"] == 1
    assert support.call_count == 2 and support.call_args.args == (1, 101, True)


def test_moderation_requires_database_role(client, logged_in, monkeypatch):
    from backend import reports, users
    token = csrf_token(client)
    denied = client.patch("/api/segnalazioni/1/stato", json={"stato": "risolta"},
                          headers={"X-CSRFToken": token})
    assert denied.status_code == 403
    monkeypatch.setattr(users, "has_role", lambda user_id, role="moderatore": True)
    action = Mock(return_value=True)
    monkeypatch.setattr(reports, "change_report_state", action)
    response = client.patch("/api/segnalazioni/1/stato", json={"stato": "risolta"},
                            headers={"X-CSRFToken": csrf_token(client)})
    assert response.status_code == 200 and action.call_args.args[:3] == (1, 101, "risolta")


def test_security_headers(client):
    response = client.get("/")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "form-action 'self'" in response.headers["Content-Security-Policy"]
    assert "Access-Control-Allow-Origin" not in response.headers
