"""Flussi HTTP senza connessioni reali; query e commit sono testati a parte."""
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

from PIL import Image
import pytest
from werkzeug.datastructures import MultiDict

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
    assert 'id="filter-categories"' in html and 'id="sort-reports"' in html
    assert 'id="category-filter-summary"' in html and 'class="category-dropdown"' in html
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
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert 'id="dashboard-filter"' in dashboard.get_data(as_text=True)
    assert 'value="rimossa_moderazione"' in dashboard.get_data(as_text=True)
    assert client.get("/profilo").status_code == 200
    html = client.get("/reports/new").get_data(as_text=True)
    assert "Marco Rossi" in html and 'id="category-options"' in html
    assert 'type="hidden" name="latitude"' in html and 'type="hidden" name="longitude"' in html
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


def test_dashboard_reports_are_filtered_and_paginated_on_server(client, logged_in, monkeypatch):
    from backend import reports
    query = Mock(return_value=[{"id": index} for index in range(50, 24, -1)])
    monkeypatch.setattr(reports, "list_report_records", query)
    page = client.get("/api/me/segnalazioni?vista=rimossa_moderazione&cursor=51")
    assert page.status_code == 200
    assert len(page.get_json()["items"]) == 25
    assert page.get_json()["next_cursor"] == 26
    assert query.call_args.kwargs == {"author_id": 101, "viewer_id": 101,
        "visibility_filter": "rimossa_moderazione", "cursor_id": 51, "limit": 26}
    assert client.get("/api/me/segnalazioni?vista=inesistente").status_code == 400
    assert client.get("/api/me/segnalazioni?cursor=-1").status_code == 400


def test_multi_category_filter_uses_bound_ids(client, monkeypatch):
    from backend import reports
    query = Mock(return_value=[])
    monkeypatch.setattr(reports, "list_report_records", query)
    assert client.get("/api/segnalazioni?categoria=3&categoria=7").status_code == 200
    assert query.call_args.args[2] == [3, 7]
    assert client.get("/api/segnalazioni?categoria=3&categoria=3").status_code == 400
    assert client.get("/api/segnalazioni?categoria=abc").status_code == 400


def test_guest_cannot_publish(client, report_data):
    response = client.post("/api/segnalazioni", data=report_data,
                           headers={"X-CSRFToken": csrf_token(client)})
    assert response.status_code == 401
    assert client.get("/api/me/segnalazioni").status_code == 401


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
        **report_data, "id_autore": "999",
        "allegato": (make_image(), "photo.jpg"),
    }, headers={"X-CSRFToken": csrf_token(client)}, content_type="multipart/form-data")
    assert response.status_code == 201 and response.get_json()["redirect"] == "/dashboard"
    data, author, upload = insert.call_args.args
    assert author["id"] == 101 and str(data["latitude"]) == "45.464200" and str(data["longitude"]) == "9.190000"
    assert upload["content"].startswith(b"\xff\xd8\xff")
    assert not list(Path(client.application.config["UPLOAD_FOLDER"]).glob("*.jpg"))
    assert "Contenuto pubblicato." in client.get("/").get_data(as_text=True)


def test_report_saves_multiple_distinct_categories(client, logged_in, report_data, monkeypatch):
    from backend.services import reports as service
    monkeypatch.setattr(service, "valid_neighborhood", lambda _: True)
    valid = Mock(return_value=True)
    monkeypatch.setattr(service, "valid_categories", valid)
    insert = Mock(return_value={"id": 42})
    monkeypatch.setattr(service, "create_report_record", insert)
    data = MultiDict((key, value) for key, value in report_data.items() if key != "categoria_id")
    data.add("categoria_ids", "2")
    data.add("categoria_ids", "4")
    data.add("allegato", (make_image(), "photo.jpg"))
    response = client.post("/api/segnalazioni", data=data,
        headers={"X-CSRFToken": csrf_token(client)}, content_type="multipart/form-data")
    assert response.status_code == 201
    assert insert.call_args.args[0]["categorie"] == [2, 4]
    valid.assert_called_once_with([2, 4])


def test_report_rejects_duplicate_categories(client, logged_in, report_data):
    data = MultiDict((key, value) for key, value in report_data.items() if key != "categoria_id")
    data.add("categoria_ids", "2")
    data.add("categoria_ids", "2")
    response = client.post("/api/segnalazioni", data=data,
        headers={"X-CSRFToken": csrf_token(client)}, content_type="multipart/form-data")
    assert response.status_code == 400
    assert "distinte" in response.get_json()["error"]


def test_attachment_is_served_from_shared_database(client, monkeypatch):
    from backend import reports
    monkeypatch.setattr(reports, "attachment_path", lambda *args: "photo.jpg")
    monkeypatch.setattr(reports, "attachment_content", lambda attachment_id: (b"image bytes", "image/jpeg"))
    response = client.get("/api/allegati/9")
    assert response.status_code == 200
    assert response.data == b"image bytes" and response.mimetype == "image/jpeg"


def test_report_rejects_out_of_city_coordinates(client, logged_in, report_data, monkeypatch):
    from backend.services import reports as service
    monkeypatch.setattr(service, "valid_neighborhood", lambda _: True)
    monkeypatch.setattr(service, "valid_categories", lambda _: True)
    response = client.post("/api/segnalazioni", data={**report_data, "latitude": "41.9028",
        "allegato": (make_image(), "photo.jpg")}, headers={"X-CSRFToken": csrf_token(client)},
        content_type="multipart/form-data")
    assert response.status_code == 400 and "Milano" in response.get_json()["error"]


def test_withdraw_requires_auth_and_ownership(client, logged_in, monkeypatch):
    from backend import reports
    token = csrf_token(client)
    withdraw = Mock(return_value=None)
    monkeypatch.setattr(reports, "withdraw_report", withdraw)
    assert client.delete("/api/segnalazioni/2", headers={"X-CSRFToken": token}).status_code == 404
    assert withdraw.call_args.args == (2, 101)
    withdraw.return_value = True
    assert client.delete("/api/segnalazioni/2", headers={"X-CSRFToken": token}).status_code == 200


def test_batch_moderation_checks_role_and_limit(client, logged_in, monkeypatch):
    from backend import reports, users
    monkeypatch.setattr(users, "has_role", lambda user_id, role="moderatore": False)
    token = csrf_token(client)
    path = "/api/moderazione/segnalazioni/azioni"
    assert client.post(path, json={"ids": [1], "azione": "approva"},
                       headers={"X-CSRFToken": token}).status_code == 403
    monkeypatch.setattr(users, "has_role", lambda user_id, role="moderatore": True)
    action = Mock(return_value={"modificate": 1, "invariate": 0, "missing": []})
    monkeypatch.setattr(reports, "moderate_reports", action)
    assert client.post(path, json={"ids": list(range(51)), "azione": "approva"},
                       headers={"X-CSRFToken": csrf_token(client)}).status_code == 400
    assert client.post(path, json={"ids": [1], "azione": "approva"},
                       headers={"X-CSRFToken": csrf_token(client)}).status_code == 200
    assert action.call_args.args == ([1], 101, "pubblica")


def test_deleted_moderation_view_is_role_protected(client, logged_in, monkeypatch):
    from backend import reports, users
    monkeypatch.setattr(users, "has_role", lambda user_id, role="moderatore": False)
    assert client.get("/api/moderazione/coda?visibilita=rimossa").status_code == 403
    monkeypatch.setattr(users, "has_role", lambda user_id, role="moderatore": True)
    queue = Mock(return_value={"items": [], "next_cursor": None})
    monkeypatch.setattr(reports, "list_moderation_reports", queue)
    assert client.get("/api/moderazione/coda?visibilita=rimossa").status_code == 200
    assert queue.call_args.args == (None, "rimossa", 25)


def test_moderation_view_can_filter_by_report_state(client, logged_in, monkeypatch):
    from backend import reports, users
    monkeypatch.setattr(users, "has_role", lambda user_id, role="moderatore": True)
    queue = Mock(return_value={"items": [], "next_cursor": None})
    monkeypatch.setattr(reports, "list_moderation_reports", queue)
    response = client.get("/api/moderazione/coda?vista=in_lavorazione")
    assert response.status_code == 200
    assert queue.call_args.args == (None, "in_lavorazione", 25)


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
    monkeypatch.setattr(users, "has_role", lambda user_id, role="moderatore": False)
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


def test_user_search_and_permanent_ban_require_moderator(client, logged_in, monkeypatch):
    from backend import reports, users
    monkeypatch.setattr(users, "has_role", lambda user_id, role="moderatore": False)
    token = csrf_token(client)
    path = "/api/moderazione/utenti/203/ban-permanente"
    payload = {"motivazione": "Violazioni ripetute"}
    assert client.post(path, json=payload, headers={"X-CSRFToken": token}).status_code == 403
    monkeypatch.setattr(users, "has_role", lambda user_id, role="moderatore": True)
    query = Mock(return_value={"items": [], "next_cursor": None})
    ban = Mock(return_value=True)
    monkeypatch.setattr(reports, "list_moderation_users", query)
    monkeypatch.setattr(reports, "permanently_ban_user", ban)
    assert client.get("/api/moderazione/utenti?q=rossi&cursor=44").status_code == 200
    query.assert_called_once_with(44, search="rossi")
    assert client.post(path, json={"motivazione": "   "}, headers={"X-CSRFToken": token}).status_code == 400
    assert client.post(path, json=payload, headers={"X-CSRFToken": token}).status_code == 200
    ban.assert_called_once_with(203, 101, "Violazioni ripetute")
    ban.return_value = False
    assert client.post(path, json=payload, headers={"X-CSRFToken": token}).status_code == 409


def test_state_catalog_exposes_allowed_transitions(client):
    states = {row["codice"]: row for row in client.get("/api/stati").get_json()}
    assert "risolta" in states["aperta"]["prossimi"]
    assert states["chiusa"]["prossimi"] == []


def test_security_headers(client):
    response = client.get("/")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "form-action 'self'" in response.headers["Content-Security-Policy"]
    assert "Access-Control-Allow-Origin" not in response.headers
