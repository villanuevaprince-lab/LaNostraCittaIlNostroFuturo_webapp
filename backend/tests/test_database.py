from datetime import datetime
from unittest.mock import MagicMock

import mysql.connector
import pytest

from backend import database, users


@pytest.fixture()
def fake_mysql(app, monkeypatch):
    app.config["APP_MODE"] = "database"
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.lastrowid = 42
    monkeypatch.setattr(database, "get_connection", lambda: connection)
    with app.app_context():
        yield connection, cursor


def test_user_insert_is_parameterized_and_committed(fake_mysql):
    connection, cursor = fake_mysql
    user = users.create_user("O'Neil", "Rossi", "Marco@EXAMPLE.COM", "scrypt:demo-hash")
    sql, params = cursor.execute.call_args.args
    assert "O'Neil" not in sql and "VALUES (%s, %s, %s, %s" in sql
    assert params == ("O'Neil", "Rossi", "marco@example.com", "scrypt:demo-hash")
    assert user["id"] == 42 and user["stato_account"] == "attivo"
    connection.commit.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


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


def test_report_insert_uses_trusted_author(fake_mysql, report_data):
    connection, cursor = fake_mysql
    result = database.create_report({**report_data, "id_autore": 999},
                                    {"id": 42, "nome": "M", "cognome": "R"})
    sql, params = cursor.execute.call_args.args
    assert params[0] == 42
    assert params[1:4] == ("segnalazione", report_data["titolo"], report_data["descrizione"])
    assert result["id"] == 42
    connection.commit.assert_called_once()


def test_report_db_failure_rolls_back(fake_mysql, report_data):
    connection, cursor = fake_mysql
    cursor.execute.side_effect = mysql.connector.Error(errno=2006)
    with pytest.raises(mysql.connector.Error):
        database.create_report(report_data, {"id": 1, "nome": "M", "cognome": "R"})
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()
    connection.close.assert_called_once()


def test_search_binds_input(fake_mysql):
    connection, cursor = fake_mysql
    cursor.fetchall.return_value = [{"data_creazione": datetime(2026, 9, 29)}]
    text = "' OR 1=1 --"
    reports = database.list_reports(text)
    sql, params = cursor.execute.call_args.args
    assert text not in sql and params == (text, *([f"%{text}%"] * 3))
    assert reports[0]["data_creazione"] == "2026-09-29T00:00:00"


def test_missing_ca_fails_closed(app, monkeypatch, tmp_path):
    monkeypatch.setenv("DB_HOST", "example.invalid")
    monkeypatch.setenv("DB_USER", "test")
    monkeypatch.setenv("DB_PASSWORD", "test-only")
    monkeypatch.setenv("DB_SSL_CA_PATH", str(tmp_path / "missing.pem"))
    with pytest.raises(mysql.connector.InterfaceError, match="CA"):
        database.get_connection()


def test_db_outage_does_not_leak_credentials(client, app, monkeypatch):
    app.config["APP_MODE"] = "database"
    def fail():
        raise mysql.connector.Error("password=SHOULD-NOT-APPEAR", errno=2006)
    monkeypatch.setattr(database, "get_connection", fail)
    response = client.get("/api/segnalazioni")
    assert response.status_code == 503
    assert "SHOULD-NOT-APPEAR" not in response.get_data(as_text=True)


def test_cursor_creation_failure_still_closes_connection(fake_mysql):
    connection, cursor = fake_mysql
    connection.cursor.side_effect = mysql.connector.Error(errno=2006)
    with pytest.raises(mysql.connector.Error):
        users.find_user_by_id(42)
    connection.close.assert_called_once()
