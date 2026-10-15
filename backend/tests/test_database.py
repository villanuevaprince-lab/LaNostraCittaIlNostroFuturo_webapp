"""Verifica SQL, transazioni e gestione dei guasti senza aprire la rete."""
from datetime import datetime
from unittest.mock import MagicMock

import mysql.connector
import pytest

from backend import database, users
from backend.app import create_app
from backend.repositories import catalog
from backend.repositories.reports import create_report_record, list_report_records, set_support


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
    assert "Visibilita='pubblica'" in queries[-1]
    assert result["id"] == 42
    connection.commit.assert_called_once()


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


def test_active_support_is_not_recorded_twice(fake_mysql):
    connection, cursor = fake_mysql
    cursor.fetchone.side_effect = [{"IdSostegno": 7, "DataRitiro": None}, {"sostegni": 1}]
    assert set_support(12, 42, True) == {"sostenuta": True, "sostegni": 1}
    assert "FOR UPDATE" in cursor.execute.call_args_list[0].args[0]
    assert cursor.execute.call_args_list[0].args[1] == (42, 12)
    assert cursor.execute.call_count == 2  # lock + count; nessuna scrittura
    assert all("EVENTO_LOG" not in call.args[0] for call in cursor.execute.call_args_list)
    connection.commit.assert_called_once()


def test_missing_ca_fails_closed(app, monkeypatch, tmp_path):
    monkeypatch.setenv("DB_HOST", "example.invalid")
    monkeypatch.setenv("DB_USER", "test")
    monkeypatch.setenv("DB_PASSWORD", "test-only")
    monkeypatch.setenv("DB_SSL_CA_PATH", str(tmp_path / "missing.pem"))
    with app.app_context(), pytest.raises(mysql.connector.InterfaceError, match="CA"):
        database.get_connection()


def test_health_checks_database_connection(fake_mysql, client):
    connection, cursor = fake_mysql
    assert client.get("/api/health").get_json() == {"status": "ok", "database": "aiven"}
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
