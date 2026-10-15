"""Nuove API verificate senza connettersi ad Aiven né al geocoder esterno."""

from io import BytesIO
from unittest.mock import Mock

from PIL import Image

from conftest import csrf_token


def image_file():
    buffer = BytesIO()
    Image.new("RGB", (32, 32), "blue").save(buffer, "PNG")
    buffer.seek(0)
    return buffer


def test_password_change_verifies_current_and_rotates_session(client, logged_in, users_stub, monkeypatch):
    from backend.api import auth as auth_api
    user = users_stub["marco@example.com"]

    def change(user_id, old, new):
        assert user_id == user["id"] and old == user["hash_password"]
        user["hash_password"] = new
        user["session_version"] = 1
        return True

    monkeypatch.setattr(auth_api, "change_password_hash", change)
    token = csrf_token(client)
    url = "/api/auth/me/password"
    invalid = client.post(url, json={"password_attuale": "sbagliata",
        "nuova_password": "NuovaPassword-2026", "conferma_password": "NuovaPassword-2026"},
        headers={"X-CSRFToken": token})
    assert invalid.status_code == 400
    valid = client.post(url, json={"password_attuale": "UnaPassword-Test-123",
        "nuova_password": "NuovaPassword-2026", "conferma_password": "NuovaPassword-2026"},
        headers={"X-CSRFToken": token})
    assert valid.status_code == 200
    with client.session_transaction() as session:
        assert session["session_version"] == 1
    assert client.get("/api/auth/me").status_code == 200
    assert client.post(url, json={}, headers={"X-CSRFToken": token}).status_code == 400


def test_avatar_is_sanitized_and_saved(client, logged_in, users_stub, monkeypatch, app):
    from backend.api import auth as auth_api
    user = users_stub["marco@example.com"]
    def update(user_id, reference):
        assert user_id == user["id"]
        user["avatar_riferimento"] = reference
        return True
    monkeypatch.setattr(auth_api, "set_avatar_reference", update)
    monkeypatch.setattr(auth_api, "find_user_by_id", lambda user_id: user if user_id == user["id"] else None)
    response = client.post("/api/auth/me/avatar", data={"avatar": (image_file(), "test.png")},
        headers={"X-CSRFToken": csrf_token(client)}, content_type="multipart/form-data")
    assert response.status_code == 200
    from pathlib import Path
    path = Path(app.config["UPLOAD_FOLDER"]) / "avatars" / user["avatar_riferimento"]
    assert path.is_file()
    with Image.open(path) as image:
        assert image.format == "WEBP"
    assert client.get(f"/api/auth/avatar/{user['id']}").status_code == 200


def test_geocoder_is_bounded_and_requires_login(client, logged_in, monkeypatch):
    from backend.api import geo
    service = Mock(return_value=[{"lat": "45.4642", "lon": "9.19", "display_name": "Via Torino, Milano"},
                                 {"lat": "41.9028", "lon": "12.4964", "display_name": "Roma"}])
    monkeypatch.setattr(geo, "nominatim", service)
    response = client.get("/api/geo/search?q=Via+Torino")
    assert response.status_code == 200 and len(response.get_json()) == 1
    assert client.get("/api/geo/reverse?lat=41.9&lng=12.5").status_code == 400
    client.post("/logout", headers={"X-CSRFToken": csrf_token(client)})
    assert client.get("/api/geo/search?q=Milano").status_code == 401


def test_detail_access_follows_visibility(client, logged_in, monkeypatch):
    from backend import reports
    record = {"id": 3, "visibilita": "bozza", "autore_id": 999}
    monkeypatch.setattr(reports, "get_report_record", lambda _: dict(record))
    assert client.get("/reports/3").status_code == 404
    record["autore_id"] = 101
    assert client.get("/reports/3").status_code == 200


