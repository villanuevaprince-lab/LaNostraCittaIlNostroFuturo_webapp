"""Rotte della verifica: reinvio, ricorso, dashboard moderatori, notifiche."""
from unittest.mock import Mock

import pytest

from backend.repositories import verification as repo
from conftest import csrf_token


@pytest.fixture()
def moderator(monkeypatch):
    from backend import users
    monkeypatch.setattr(users, "has_role", lambda user_id, role="moderatore": True)


def post(client, path, payload):
    return client.post(path, json=payload, headers={"X-CSRFToken": csrf_token(client)})


# --- autore ------------------------------------------------------------------

def test_resubmit_and_appeal_require_login(client):
    assert post(client, "/api/segnalazioni/5/reinvio", {}).status_code == 401
    assert post(client, "/api/segnalazioni/5/ricorso", {}).status_code == 401


def test_resubmit_validates_and_passes_the_configured_limit(app, client, logged_in, monkeypatch):
    resubmit = Mock(return_value={"stato_verifica": "in_valutazione", "reinvii": 1, "versione": 2})
    monkeypatch.setattr(repo, "resubmit", resubmit)
    assert post(client, "/api/segnalazioni/5/reinvio", {"titolo": "x", "descrizione": "troppo corta"}).status_code == 400
    app.config["VERIFICA_MAX_REINVII"] = 2
    response = post(client, "/api/segnalazioni/5/reinvio", {"titolo": " Buca corretta ", "descrizione": "Descrizione riscritta con calma"})
    assert response.status_code == 200 and response.get_json()["stato_verifica"] == "in_valutazione"
    assert resubmit.call_args.args == (5, 101, "Buca corretta", "Descrizione riscritta con calma", 2)


def test_resubmit_limit_is_reported(client, logged_in, monkeypatch):
    monkeypatch.setattr(repo, "resubmit", Mock(side_effect=repo.VerificationActionError("Reinvii esauriti", 429)))
    response = post(client, "/api/segnalazioni/5/reinvio", {"titolo": "Titolo", "descrizione": "Descrizione valida"})
    assert response.status_code == 429 and response.get_json()["error"] == "Reinvii esauriti"


def test_appeal_needs_a_reason(client, logged_in, monkeypatch):
    appeal = Mock(return_value={"stato_verifica": "in_ricorso"})
    monkeypatch.setattr(repo, "appeal", appeal)
    assert post(client, "/api/segnalazioni/5/ricorso", {"motivazione": "no"}).status_code == 400
    response = post(client, "/api/segnalazioni/5/ricorso", {"motivazione": "Cito un graffito, non insulto nessuno"})
    assert response.status_code == 200 and appeal.call_args.args[:2] == (5, 101)


def test_banned_author_cannot_resubmit_or_appeal(client, logged_in, users_stub, registration):
    users_stub[registration["email"]]["stato_account"] = "bloccato"
    token = csrf_token(client, "/profilo")
    for path in ("/api/segnalazioni/5/reinvio", "/api/segnalazioni/5/ricorso"):
        assert client.post(path, json={}, headers={"X-CSRFToken": token}).status_code == 403


def test_dashboard_exposes_the_resubmit_limit(app, client, logged_in, monkeypatch):
    from backend import reports
    monkeypatch.setattr(reports, "list_report_records", Mock(return_value=[]))
    app.config["VERIFICA_MAX_REINVII"] = 4
    assert client.get("/api/me/segnalazioni").get_json()["max_reinvii"] == 4


# --- moderatori --------------------------------------------------------------

def test_moderator_endpoints_are_role_protected(client, logged_in, monkeypatch):
    from backend import users
    monkeypatch.setattr(users, "has_role", lambda user_id, role="moderatore": False)
    assert client.get("/moderazione/verifiche").status_code == 403
    assert client.get("/api/moderazione/verifiche").status_code == 403
    assert post(client, "/api/moderazione/verifiche/5/decisione", {"azione": "approva", "motivazione": "ok"}).status_code == 403


def test_priority_queue_is_the_default_view(client, logged_in, moderator, monkeypatch):
    listing = Mock(return_value={"items": [], "next_cursor": None})
    monkeypatch.setattr(repo, "list_items", listing)
    assert client.get("/api/moderazione/verifiche").status_code == 200
    assert listing.call_args.args == ("priorita", None, 25)
    for view in ("pubblicata", "respinta_automatica", "respinta_moderatore", "in_valutazione",
                 "in_attesa_modello", "da_revisionare", "in_ricorso", "tutte"):
        assert client.get(f"/api/moderazione/verifiche?vista={view}").status_code == 200
    assert client.get("/api/moderazione/verifiche?vista=altro").status_code == 400
    assert client.get("/api/moderazione/verifiche?limit=99").status_code == 400


def test_page_counts_and_detail(client, logged_in, moderator, monkeypatch):
    monkeypatch.setattr(repo, "counts_by_state", Mock(return_value={"da_revisionare": 2}))
    monkeypatch.setattr(repo, "item_detail", Mock(side_effect=[None, {"id": 5, "esiti": []}]))
    page = client.get("/moderazione/verifiche").get_data(as_text=True)
    assert 'id="verification-filter"' in page and "verification-moderation.js" in page
    assert client.get("/api/moderazione/verifiche/conteggi").get_json() == {"da_revisionare": 2}
    assert client.get("/api/moderazione/verifiche/5").status_code == 404
    assert client.get("/api/moderazione/verifiche/5").get_json()["id"] == 5


def test_decision_requires_action_and_reason_and_sends_email(client, logged_in, moderator, monkeypatch):
    from backend import verification_api
    info = {"utente": 1, "titolo": "Buca", "tipo": "verifica_moderatore", "messaggio": "ok"}
    decide = Mock(return_value={"stato_verifica": "pubblicata", "ribaltamento": True, "notifica": info})
    monkeypatch.setattr(repo, "moderator_decide", decide)
    email = Mock()
    monkeypatch.setattr(verification_api, "deliver_email", email)
    path = "/api/moderazione/verifiche/5/decisione"
    assert post(client, path, {"azione": "cancella", "motivazione": "motivo"}).status_code == 400
    assert post(client, path, {"azione": "approva", "motivazione": ""}).status_code == 400
    response = post(client, path, {"azione": "approva", "motivazione": "Cita un graffito"})
    assert response.status_code == 200 and response.get_json() == {"ok": True, "stato_verifica": "pubblicata", "ribaltamento": True}
    assert decide.call_args.args == (5, 101, "approva", "Cita un graffito")
    email.assert_called_once_with(info)


def test_decision_conflict(client, logged_in, moderator, monkeypatch):
    monkeypatch.setattr(repo, "moderator_decide", Mock(side_effect=repo.VerificationActionError("Già in questo stato.")))
    assert post(client, "/api/moderazione/verifiche/5/decisione", {"azione": "approva", "motivazione": "motivo valido"}).status_code == 409


def test_old_moderation_queue_links_to_verification(client, logged_in, moderator):
    html = client.get("/moderazione").get_data(as_text=True)
    assert 'href="/moderazione/verifiche"' in html and 'value="bozza"' not in html


def test_old_batch_approval_skips_items_still_under_verification(fake_mysql):
    from backend.repositories.reports import moderate_reports
    _, cursor = fake_mysql
    cursor.fetchone.side_effect = [{"Visibilita": "bozza", "StatoVerifica": "da_revisionare"}]
    assert moderate_reports([5], 7, "pubblica") == {"modificate": 0, "invariate": 1, "missing": []}
    assert not any("UPDATE SEGNALAZIONE SET Visibilita" in call.args[0] for call in cursor.execute.call_args_list)


# --- creazione e notifiche ------------------------------------------------------

def test_queued_creation_does_not_publish_and_enqueues_in_the_same_transaction(fake_mysql):
    from backend.repositories.reports import create_report_record
    from test_database import report_payload, upload_payload
    connection, cursor = fake_mysql
    result = create_report_record({**report_payload(), "verifica": True}, {"id": 9}, upload_payload())
    sql = [call.args[0] for call in cursor.execute.call_args_list]
    assert result["visibilita"] == "bozza" and result["stato_verifica"] == "in_valutazione"
    assert not any("SET Visibilita='pubblica'" in q for q in sql)
    assert any("INSERT INTO VERIFICA_JOB" in q for q in sql) and any("INSERT INTO DECISIONE_VERIFICA" in q for q in sql)
    connection.commit.assert_called_once()


def test_inbox_returns_the_message(fake_mysql):
    from datetime import datetime
    from backend.repositories.notifications import inbox
    _, cursor = fake_mysql
    cursor.fetchall.return_value = [{"id": 1, "report_id": 5, "comment_id": None, "tipo": "verifica_respinta",
                                     "messaggio": "Respinto: insulti.", "letta": False, "data": datetime(2026, 11, 20)}]
    cursor.fetchone.return_value = {"n": 1}
    page = inbox(101)
    assert page["items"][0]["messaggio"] == "Respinto: insulti." and "Messaggio AS messaggio" in cursor.execute.call_args_list[0].args[0]
