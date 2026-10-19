"""Verifica SQL, transazioni e gestione dei guasti senza aprire la rete."""
from datetime import datetime
from unittest.mock import MagicMock

import mysql.connector
import pytest

from backend import database, users
from backend.app import create_app
from backend.repositories import catalog
from backend.repositories.reports import (
    attachment_content, change_report_state, create_report_record, get_report_record, list_moderation_reports,
    list_moderation_users, list_report_records,
    moderate_reports, permanently_ban_user, set_support, withdraw_report,
)


@pytest.fixture()
def fake_mysql(app, monkeypatch):
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.lastrowid = 42
    monkeypatch.setattr(database, "get_connection", lambda: connection)
    with app.app_context():
        yield connection, cursor


def report_payload():
    return {
        "tipo": "segnalazione", "titolo": "Lampione", "descrizione": "Lampione spento",
        "quartiere_id": 1, "categorie": [2], "latitude": None, "longitude": None,
        "indirizzo": "Via Roma",
    }


def upload_payload():
    return {
        "mime": "image/jpeg", "reference": "random.jpg", "original_name": "foto.jpg",
        "size": 42, "sha256": "a" * 64, "accessible_description": "Lampione spento",
        "content": b"a" * 42,
    }


def test_user_insert_is_parameterized_and_committed(fake_mysql):
    connection, cursor = fake_mysql
    user = users.create_user("O'Neil", "Rossi", "Marco@EXAMPLE.COM", "scrypt:sample-hash")
    sql, params = cursor.execute.call_args_list[0].args
    assert "O'Neil" not in sql and "VALUES (%s, %s, %s, %s" in sql
    assert params == ("O'Neil", "Rossi", "marco@example.com", "scrypt:sample-hash")
    assert user["id"] == 42 and user["stato_account"] == "attivo"
    connection.commit.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()
    assert cursor.execute.call_count == 2  # utente + evento di audit


def test_duplicate_email_rolls_back(fake_mysql):
    connection, cursor = fake_mysql
    cursor.execute.side_effect = mysql.connector.IntegrityError(errno=1062)
    with pytest.raises(users.DuplicateEmail):
        users.create_user("M", "R", "duplicate@example.com", "hash")
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()
    connection.close.assert_called_once()


def test_other_database_errors_are_not_reported_as_duplicate(fake_mysql):
    connection, cursor = fake_mysql
    cursor.execute.side_effect = mysql.connector.IntegrityError(errno=1452)
    with pytest.raises(mysql.connector.IntegrityError):
        users.create_user("M", "R", "new@example.com", "hash")
    connection.rollback.assert_called_once()


def test_lookup_binds_email_and_id(fake_mysql):
    connection, cursor = fake_mysql
    users.find_user_by_email("NAME@example.com")
    assert cursor.execute.call_args.args[1] == ("name@example.com",)
    users.find_user_by_id(42)
    assert cursor.execute.call_args.args[1] == (42,)
    connection.commit.assert_not_called()


def test_restarted_app_reads_database_instead_of_old_process_state(fake_mysql, monkeypatch):
    connection, cursor = fake_mysql
    cursor.fetchone.return_value = {"id": 42, "nome": "Marco"}
    other = create_app({"TESTING": True, "SECRET_KEY": "x" * 32,
                        "RATELIMIT_ENABLED": False})
    with other.app_context():
        assert users.find_user_by_id(42)["nome"] == "Marco"
    assert "FROM UTENTE" in cursor.execute.call_args.args[0]
    assert "demo_store" not in other.extensions


def test_catalogs_query_mysql(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchall.return_value = [{"id": 2, "nome": "Brera"}]
    assert catalog.list_neighborhoods()[0]["nome"] == "Brera"
    assert "FROM QUARTIERE WHERE Attivo = TRUE" in cursor.execute.call_args.args[0]
    cursor.fetchone.return_value = {"totale": 1}
    assert catalog.valid_categories([3]) is True
    assert cursor.execute.call_args.args[1] == (3,)


def test_publication_follows_attachment_insert_in_one_transaction(fake_mysql):
    connection, cursor = fake_mysql
    result = create_report_record(report_payload(), {"id": 9}, upload_payload())
    queries = [call.args[0] for call in cursor.execute.call_args_list]
    assert "'bozza'" in queries[0]
    assert cursor.execute.call_args_list[0].args[1][0] == 9
    assert "INSERT INTO ALLEGATO" in queries[1]
    assert "INSERT INTO ALLEGATO_CONTENUTO" in queries[2]
    attachment_index = next(index for index, sql in enumerate(queries) if "INSERT INTO ALLEGATO" in sql)
    publish_index = next(index for index, sql in enumerate(queries) if "SET Visibilita='pubblica'" in sql)
    assert publish_index > attachment_index
    assert result["visibilita"] == "pubblica"
    assert result["id"] == 42
    connection.commit.assert_called_once()


def test_shared_attachment_bytes_are_read_from_database(fake_mysql):
    import hashlib
    _, cursor = fake_mysql
    content = b"foto condivisa"
    metadata = {"mime": "image/jpeg", "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest()}
    cursor.fetchall.return_value = [dict(metadata, data=content[:4]), dict(metadata, data=content[4:])]
    assert attachment_content(4) == (content, "image/jpeg")
    assert "ORDER BY c.Numero" in cursor.execute.call_args.args[0]


def test_publication_db_failure_rolls_back(fake_mysql):
    connection, cursor = fake_mysql
    cursor.execute.side_effect = mysql.connector.Error(errno=2006)
    with pytest.raises(mysql.connector.Error):
        create_report_record(report_payload(), {"id": 9}, upload_payload())
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()


def test_search_is_parameterized(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchall.return_value = [{"data_creazione": datetime(2026, 9, 29)}]
    text = "' OR 1=1 --"
    rows = list_report_records(text, viewer_id=5, order="sostegni")
    sql, params = cursor.execute.call_args.args
    assert text not in sql
    assert params == (5, 5, text, *([f"%{text}%"] * 3))
    assert "ORDER BY sostegni DESC" in sql
    assert rows[0]["data_creazione"] == "2026-09-29T00:00:00"


def test_multiple_categories_are_filtered_and_returned_as_tags(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchall.return_value = [{"data_creazione": datetime(2026, 9, 29),
        "categorie_json": '[{"id":4,"nome":"Mobilità"},{"id":2,"nome":"Ambiente"}]'}]
    rows = list_report_records(category_ids=[2, 4])
    sql, params = cursor.execute.call_args.args
    assert "sc.IdCategoria IN (%s,%s)" in sql
    assert params[-2:] == (2, 4)
    assert [category["nome"] for category in rows[0]["categorie"]] == ["Ambiente", "Mobilità"]
    cursor.fetchone.return_value = {"categorie_json": '[{"id":2,"nome":"Ambiente"}]'}
    assert get_report_record(3)["categorie"] == [{"id": 2, "nome": "Ambiente"}]


def test_dashboard_removed_filter_separates_moderator_and_author(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchall.return_value = []
    list_report_records(author_id=7, viewer_id=7,
        visibility_filter="rimossa_moderazione", cursor_id=42, limit=26)
    sql, params = cursor.execute.call_args.args
    assert "NOT EXISTS (SELECT 1 FROM EVENTO_LOG r" in sql
    assert "s.IdSegnalazione < %s" in sql
    assert "ORDER BY s.IdSegnalazione DESC LIMIT %s" in sql
    assert params[-3:] == (7, 42, 26)
    list_report_records(author_id=7, viewer_id=7, visibility_filter="rimossa_autore", limit=26)
    assert "EXISTS (SELECT 1 FROM EVENTO_LOG r" in cursor.execute.call_args.args[0]


def test_user_search_is_parameterized_and_includes_block_type(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchall.return_value = [{"id": 7, "blocco_fine": datetime(2026, 11, 1),
        "email": "ada@example.com", "tipo_blocco": "temporaneo"}]
    page = list_moderation_users(search="a%_!", limit=25)
    sql, params = cursor.execute.call_args.args
    assert "a%_!" not in sql and "LIKE %s ESCAPE '!'" in sql
    assert "permanente" in sql and "u.Email" in sql
    assert params[3] == "a!%!_!!%"
    assert page["items"][0]["blocco_fine"] == "2026-11-01T00:00:00"


def test_moderation_queue_uses_state_and_stops_cursor_at_last_page(fake_mysql):
    _, cursor = fake_mysql
    rows = [
        {"id": 9, "data_creazione": datetime(2026, 9, 29)},
        {"id": 8, "data_creazione": datetime(2026, 9, 28)},
        {"id": 7, "data_creazione": datetime(2026, 9, 27)},
    ]
    cursor.fetchall.return_value = rows
    page = list_moderation_reports(20, "in_lavorazione", 2)
    sql, params = cursor.execute.call_args.args
    assert "s.Visibilita <> 'rimossa' AND s.Stato=%s" in sql
    assert params == ("in_lavorazione", 20, 20, 3)
    assert page["next_cursor"] == 8

    cursor.fetchall.return_value = []
    assert list_moderation_reports(8, "in_lavorazione", 2)["next_cursor"] is None


def test_moderation_all_view_excludes_hidden_and_removed(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchall.return_value = [{"id": 5, "data_creazione": datetime(2026, 9, 29)}]
    page = list_moderation_reports(None, "tutte", 5)
    sql, params = cursor.execute.call_args.args
    assert "s.Visibilita NOT IN ('rimossa', 'nascosta')" in sql
    assert params == (None, None, 6)
    assert page["next_cursor"] is None


def test_closed_report_can_reopen_and_records_history(fake_mysql):
    connection, cursor = fake_mysql
    cursor.fetchone.side_effect = [{"Stato": "chiusa"}, {"1": 1}]
    assert change_report_state(12, 9, "aperta", "Riaperta") is True
    history = next(call.args[1] for call in cursor.execute.call_args_list
                   if "INSERT INTO STORICO_STATO" in call.args[0])
    assert history == (12, "chiusa", "aperta", 9, "Riaperta")
    connection.commit.assert_called_once()


def test_permanent_ban_preserves_prior_block_and_audits(fake_mysql):
    connection, cursor = fake_mysql
    cursor.fetchone.side_effect = [
        {"StatoAccount": "bloccato"}, {"IdBlocco": 8, "DataFinePrevista": datetime(2026, 11, 1)},
    ]
    assert permanently_ban_user(7, 9, "Violazioni ripetute") is True
    sql = [call.args[0] for call in cursor.execute.call_args_list]
    assert any("DataRevoca=CURRENT_TIMESTAMP" in query for query in sql)
    assert any("INSERT INTO BLOCCO" in query and "NULL" in query for query in sql)
    assert any("'ban_permanente'" in query for query in sql)
    assert all("DELETE" not in query for query in sql)
    connection.commit.assert_called_once()


def test_permanent_ban_rejects_existing_permanent_block(fake_mysql):
    connection, cursor = fake_mysql
    cursor.fetchone.side_effect = [{"StatoAccount": "bloccato"},
        {"IdBlocco": 8, "DataFinePrevista": None}]
    assert permanently_ban_user(7, 9, "Doppio ban") is False
    assert not any("INSERT INTO BLOCCO" in call.args[0] for call in cursor.execute.call_args_list)
    connection.commit.assert_called_once()


def test_active_support_is_not_recorded_twice(fake_mysql):
    connection, cursor = fake_mysql
    cursor.fetchone.side_effect = [{"Visibilita": "pubblica"}, {"IdSostegno": 7, "DataRitiro": None}, {"sostegni": 1}]
    assert set_support(12, 42, True) == {"sostenuta": True, "sostegni": 1}
    assert "FOR UPDATE" in cursor.execute.call_args_list[0].args[0]
    assert cursor.execute.call_args_list[1].args[1] == (42, 12)
    assert cursor.execute.call_count == 3  # lock genitore + sostegno + count
    assert all("EVENTO_LOG" not in call.args[0] for call in cursor.execute.call_args_list)
    connection.commit.assert_called_once()


def test_bulk_moderation_uses_stable_lock_order_and_audit(fake_mysql):
    connection, cursor = fake_mysql
    cursor.fetchone.side_effect = [{"Visibilita": "bozza"}, {"Visibilita": "pubblica"}]
    result = moderate_reports([2, 1], 9, "pubblica")
    assert result == {"modificate": 1, "invariate": 1, "missing": []}
    locks = [call.args[1][0] for call in cursor.execute.call_args_list if "FOR UPDATE" in call.args[0]]
    assert locks == [1, 2]
    assert any("EVENTO_LOG" in call.args[0] for call in cursor.execute.call_args_list)
    connection.commit.assert_called_once()


def test_moderator_can_restore_removed_report(fake_mysql):
    connection, cursor = fake_mysql
    cursor.fetchone.side_effect = [{"Visibilita": "rimossa"}, None]
    result = moderate_reports([12], 9, "pubblica")
    assert result == {"modificate": 1, "invariate": 0, "missing": []}
    queries = [call.args[0] for call in cursor.execute.call_args_list]
    assert "ritiro_segnalazione" in queries[1]
    assert any("UPDATE SEGNALAZIONE SET Visibilita=%s" in sql for sql in queries)
    assert any("moderazione_segnalazione" in sql for sql in queries)
    connection.commit.assert_called_once()


def test_moderator_cannot_restore_author_withdrawal(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchone.side_effect = [{"Visibilita": "rimossa"}, {"1": 1}]
    assert moderate_reports([12], 9, "pubblica") == {"modificate": 0, "invariate": 1, "missing": []}
    assert not any("UPDATE SEGNALAZIONE" in call.args[0] for call in cursor.execute.call_args_list)


def test_withdraw_cannot_touch_other_authors_report(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchone.return_value = {"IdAutore": 10, "Visibilita": "pubblica"}
    assert withdraw_report(3, 11) is None
    assert all("UPDATE SEGNALAZIONE" not in call.args[0] for call in cursor.execute.call_args_list)


def test_missing_ca_fails_closed(app, monkeypatch, tmp_path):
    monkeypatch.setenv("DB_HOST", "example.invalid")
    monkeypatch.setenv("DB_USER", "test")
    monkeypatch.setenv("DB_PASSWORD", "test-only")
    monkeypatch.setenv("DB_SSL_CA_PATH", str(tmp_path / "missing.pem"))
    with app.app_context(), pytest.raises(mysql.connector.InterfaceError, match="CA"):
        database.get_connection()


def test_health_checks_database_connection(fake_mysql, client):
    connection, cursor = fake_mysql
    assert client.get("/api/health").get_json()["database"] == "aiven"
    assert cursor.execute.call_args.args == ("SELECT 1 AS pronto",)
    connection.close.assert_called_once()


def test_db_outage_does_not_leak_credentials(client, monkeypatch):
    def fail():
        raise mysql.connector.Error("password=SHOULD-NOT-APPEAR", errno=2006)
    monkeypatch.setattr(database, "get_connection", fail)
    response = client.get("/api/segnalazioni")
    assert response.status_code == 503
    assert "SHOULD-NOT-APPEAR" not in response.get_data(as_text=True)


def test_cursor_creation_failure_still_closes_connection(fake_mysql):
    connection, _ = fake_mysql
    connection.cursor.side_effect = mysql.connector.Error(errno=2006)
    with pytest.raises(mysql.connector.Error):
        users.find_user_by_id(42)
    connection.close.assert_called_once()
