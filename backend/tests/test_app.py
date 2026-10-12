from io import BytesIO

from PIL import Image
import pytest

from conftest import csrf_token


def make_image():
    buffer = BytesIO()
    Image.new("RGB", (16, 16), "green").save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer


def test_health_and_catalogs(client):
    assert client.get("/api/health").get_json() == {"status": "ok", "database": "demo"}
    assert client.get("/api/quartieri").get_json()[0]["nome"] == "Centro Storico"
    assert client.get("/api/categorie").get_json()


def test_homepage_has_search_and_filters_not_creation_form(client):
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'href="/reports/new"' in html
    assert 'id="report-form"' not in html
    assert 'id="filter-category"' in html
    assert client.get("/static/js/home.js").status_code == 200
    assert client.get("/static/js/report.js").status_code == 200


@pytest.mark.parametrize("path", [
    "/index.html", "/report_new.html", "/templates/report_new.html",
    "/static/report_new.html", "/static/../templates/report_new.html",
])
def test_no_static_html_bypass(client, path):
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/reports/new", "/dashboard", "/profilo"])
def test_guest_is_sent_to_login(client, path):
    response = client.get(path)
    assert response.status_code == 303
    assert response.location == "/login?next=" + path


def test_dashboard_and_profile_after_login(client, logged_in):
    assert client.get("/dashboard").status_code == 200
    assert client.get("/profilo").status_code == 200
    assert "Marco Rossi" in client.get("/reports/new").get_data(as_text=True)


def test_report_requires_login_and_multipart_upload(client, logged_in, report_data):
    client.post("/logout", data={"csrf_token": csrf_token(client)})
    response = client.post("/api/segnalazioni", data=report_data,
                           headers={"X-CSRFToken": csrf_token(client)})
    assert response.status_code == 401
    assert client.get("/api/segnalazioni").status_code == 200


def test_report_requires_attachment(client, logged_in, report_data):
    response = client.post("/api/segnalazioni", data=report_data,
                           headers={"X-CSRFToken": csrf_token(client)})
    assert response.status_code == 400
    assert "allega" in response.get_json()["error"].lower()


def test_publish_requires_category_quarter_and_accessible_text(client, logged_in, report_data):
    for key, value in [("quartiere_id", ""), ("categorie", []),
                       ("descrizione_accessibile", "")]:
        payload = {**report_data, key: value, "allegato": (make_image(), "lampione.jpg")}
        response = client.post("/api/segnalazioni", data=payload,
                               headers={"X-CSRFToken": csrf_token(client)},
                               content_type="multipart/form-data")
        assert response.status_code == 400


def test_publish_report_with_valid_image_and_confirmation(client, logged_in, report_data):
    response = client.post("/api/segnalazioni",
        data={**report_data, "id_autore": "999", "stato": "risolta",
              "allegato": (make_image(), "../../lampione.jpg")},
        headers={"X-CSRFToken": csrf_token(client)}, content_type="multipart/form-data")
    assert response.status_code == 201
    result = response.get_json()
    assert result["redirect"] == "/" and result["report"]["stato"] == "aperta"
    assert "Segnalazione pubblicata correttamente." in client.get("/").get_data(as_text=True)
    rows = client.get("/api/segnalazioni?mie=1").get_json()
    assert rows[0]["autore"] == "Marco Rossi"
    assert rows[0]["quartiere_id"] == 1
    assert rows[0]["allegato_id"] == rows[0]["id"]
    attachment = client.get(f"/api/allegati/{rows[0]['allegato_id']}")
    assert attachment.status_code == 200
    assert attachment.mimetype == "image/jpeg"


def test_upload_checks_actual_file_content(client, logged_in, report_data):
    response = client.post("/api/segnalazioni",
        data={**report_data, "allegato": (BytesIO(b"not an image"), "photo.jpg")},
        headers={"X-CSRFToken": csrf_token(client)}, content_type="multipart/form-data")
    assert response.status_code == 400


@pytest.mark.parametrize("field,value", [
    ("titolo", "a" * 201), ("descrizione", "a" * 5001), ("indirizzo", "a" * 256),
    ("tipo", "inesistente"), ("latitude", "180"), ("longitude", "999"),
])
def test_server_validates_report_fields(client, logged_in, report_data, field, value):
    response = client.post("/api/segnalazioni",
        data={**report_data, field: value, "allegato": (make_image(), "photo.jpg")},
        headers={"X-CSRFToken": csrf_token(client)}, content_type="multipart/form-data")
    assert response.status_code == 400


def test_profile_update_and_account_deletion(client, logged_in):
    response = client.patch("/api/auth/me", json={"nome": "Marco Nuovo", "cognome": "Rossi", "quartiere_id": 2},
                            headers={"X-CSRFToken": csrf_token(client)})
    assert response.status_code == 200
    assert response.get_json()["user"]["nome"] == "Marco Nuovo"
    deleted = client.delete("/api/auth/me", headers={"X-CSRFToken": csrf_token(client)})
    assert deleted.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_comments_and_support(client, logged_in):
    report_id = 1
    token = csrf_token(client)
    comment = client.post(f"/api/segnalazioni/{report_id}/commenti", json={"testo": "Confermo"},
                          headers={"X-CSRFToken": token})
    assert comment.status_code == 201
    assert client.put(f"/api/segnalazioni/{report_id}/sostegno", headers={"X-CSRFToken": token}).status_code == 200
    assert client.get(f"/api/segnalazioni/{report_id}/sostegno").get_json()["sostenuta"] is True
    assert client.delete(f"/api/segnalazioni/{report_id}/sostegno", headers={"X-CSRFToken": token}).status_code == 200
    assert client.get(f"/api/segnalazioni/{report_id}/sostegno").get_json()["sostenuta"] is False


def test_moderation_requires_role(app, client, logged_in):
    token = csrf_token(client)
    denied = client.patch("/api/segnalazioni/1/stato", json={"stato": "risolta"},
                          headers={"X-CSRFToken": token})
    assert denied.status_code == 403
    user = next(iter(app.extensions["demo_store"]["users"].values()))
    app.extensions["demo_store"]["moderators"].add(user["id"])
    allowed = client.patch("/api/segnalazioni/1/stato", json={"stato": "risolta"},
                           headers={"X-CSRFToken": csrf_token(client)})
    assert allowed.status_code == 200


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
