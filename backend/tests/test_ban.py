"""Utenti bannati: accesso consentito, area personale in sola lettura, sblocco immediato."""
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from conftest import csrf_token


BAN = {"id": 8, "motivo": "Insulti ripetuti nei commenti", "data_inizio": datetime(2026, 11, 1, 9, 30),
       "data_fine": None}


@pytest.fixture()
def banned(users_stub, registration):
    def apply(ban=BAN):
        user = users_stub[registration["email"]]
        user["stato_account"], user["ban_info"] = "bloccato", dict(ban) if ban else None
        return user
    return apply


def login(client, registration):
    return client.post("/login", data={"csrf_token": csrf_token(client, "/login"),
                                       "email": registration["email"], "password": registration["password"]})


def test_banned_user_can_login_and_lands_on_the_account_area(client, users_stub, registration, submit, banned):
    submit("/register", registration)
    submit("/logout")
    banned()
    response = login(client, registration)
    assert response.status_code == 303 and response.location == "/profilo"
    page = client.get("/profilo").get_data(as_text=True)
    assert "Il tuo profilo è stato bannato" in page and "Insulti ripetuti nei commenti" in page
    assert "01/11/2026 alle 09:30" in page and "senza scadenza" in page


def test_api_login_reports_the_ban(client, users_stub, registration, submit, banned):
    submit("/register", registration)
    submit("/logout")
    banned()
    response = client.post("/api/auth/login", json={"email": registration["email"], "password": registration["password"]},
                           headers={"X-CSRFToken": csrf_token(client, "/login")})
    assert response.status_code == 200 and response.get_json()["redirect"] == "/profilo"
    me = client.get("/api/auth/me").get_json()["user"]
    assert me["ban"] == {"motivo": BAN["motivo"], "data_inizio": "2026-11-01T09:30", "data_fine": None}


def test_banner_appears_on_every_allowed_page_with_end_date(client, logged_in, banned):
    banned({**BAN, "data_fine": datetime.now() + timedelta(days=3), "motivo": None})
    for path in ("/profilo", "/dashboard"):
        page = client.get(path)
        html = page.get_data(as_text=True)
        assert page.status_code == 200 and "Il tuo profilo è stato bannato" in html
        assert "fino al" in html and "Motivo indicato" not in html
        assert 'href="/reports/new"' not in html and "notifications.js" not in html


@pytest.mark.parametrize("method,path,payload", [
    ("post", "/api/segnalazioni", None),
    ("post", "/api/segnalazioni/3/commenti", {"testo": "Ciao a tutti"}),
    ("put", "/api/segnalazioni/3/sostegno", None),
    ("delete", "/api/segnalazioni/3/sostegno", None),
    ("delete", "/api/segnalazioni/3", None),
    ("patch", "/api/auth/me", {"nome": "Altro"}),
    ("post", "/api/auth/me/password", {"password_attuale": "x"}),
    ("post", "/api/auth/me/avatar", None),
    ("delete", "/api/auth/me", None),
    ("post", "/api/auth/me/email", {"nuova_email": "nuova@example.com", "password": "x"}),
    ("delete", "/api/commenti/4", None),
    ("patch", "/api/notifiche/4", None),
    ("post", "/api/ia/suggerisci-categorie", {"titolo": "x"}),
])
def test_write_endpoints_return_403_while_banned(client, logged_in, banned, monkeypatch, method, path, payload):
    from backend import reports
    spy = Mock()
    for name in ("add_comment", "set_support", "withdraw_report"):
        monkeypatch.setattr(reports, name, spy)
    banned()
    response = getattr(client, method)(path, json=payload, headers={"X-CSRFToken": csrf_token(client, "/profilo")})
    assert response.status_code == 403 and response.get_json()["bannato"] is True
    spy.assert_not_called()


@pytest.mark.parametrize("path", ["/", "/reports/new", "/reports/3", "/notifiche", "/api/segnalazioni",
                                  "/api/notifiche", "/api/map-items"])
def test_other_pages_and_public_reads_are_forbidden_while_banned(client, logged_in, banned, path):
    banned()
    response = client.get(path)
    assert response.status_code == 403
    if not path.startswith("/api/"):
        assert "Il tuo profilo è stato bannato" in response.get_data(as_text=True)


def test_account_area_apis_stay_readable(client, logged_in, banned, monkeypatch):
    from backend import reports
    monkeypatch.setattr(reports, "list_report_records", Mock(return_value=[]))
    banned()
    assert client.get("/api/me/segnalazioni").status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_login_page_sends_a_logged_in_banned_user_to_the_profile(client, logged_in, banned):
    banned()
    response = client.get("/login")
    assert response.status_code == 303 and response.location == "/profilo"


def test_banned_user_can_still_logout(client, logged_in, banned):
    banned()
    response = client.post("/api/auth/logout", headers={"X-CSRFToken": csrf_token(client, "/profilo")})
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "user_id" not in session


def test_unban_restores_features_on_the_next_request(client, logged_in, users_stub, registration, banned):
    banned()
    token = csrf_token(client, "/profilo")
    assert client.post("/api/segnalazioni", headers={"X-CSRFToken": token}).status_code == 403
    users_stub[registration["email"]]["stato_account"] = "attivo"  # sblocco del moderatore
    users_stub[registration["email"]]["ban_info"] = None
    # Stessa sessione: ora la richiesta arriva alla validazione (400), non al blocco (403).
    assert client.post("/api/segnalazioni", headers={"X-CSRFToken": token}).status_code == 400
    assert "Il tuo profilo è stato bannato" not in client.get("/profilo").get_data(as_text=True)


def test_expired_temporary_ban_is_lifted_automatically(client, logged_in, users_stub, registration, banned):
    banned({**BAN, "data_fine": datetime.now() - timedelta(minutes=1)})
    page = client.get("/profilo").get_data(as_text=True)
    assert "Il tuo profilo è stato bannato" not in page
    assert users_stub[registration["email"]]["stato_account"] == "attivo"


def test_blocked_state_without_block_row_is_still_a_ban(client, logged_in, banned):
    banned(None)
    assert client.get("/").status_code == 403
    assert "Ban attivo, senza scadenza" in client.get("/profilo").get_data(as_text=True)


def test_banned_moderator_flag_is_dropped(client, logged_in, banned, monkeypatch):
    from backend import security
    monkeypatch.setattr(security, "has_role", lambda *args, **kwargs: True)
    banned()
    assert client.get("/moderazione").status_code == 403


def test_find_active_ban_and_expiry_queries(fake_mysql):
    from backend.users import expire_ban, find_active_ban
    _, cursor = fake_mysql
    cursor.fetchone.return_value = dict(BAN)
    assert find_active_ban(5)["motivo"] == BAN["motivo"]
    assert "DataRevoca IS NULL" in cursor.execute.call_args.args[0] and cursor.execute.call_args.args[1] == (5,)
    cursor.rowcount = 1
    assert expire_ban(5, 8) is True
    queries = [call.args[0] for call in cursor.execute.call_args_list]
    assert any("UPDATE UTENTE SET StatoAccount = 'attivo'" in sql for sql in queries)
    assert any("scadenza_blocco" in sql for sql in queries)
    cursor.rowcount = 0
    assert expire_ban(5, 8) is False
