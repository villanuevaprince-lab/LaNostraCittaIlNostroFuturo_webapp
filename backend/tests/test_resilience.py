"""Diagnosi dei 503 su /api/segnalazioni e header CSP (nessuna connessione reale)."""
import logging
from unittest.mock import Mock

import mysql.connector
import pytest
from mysql.connector.errors import PoolError

from backend import database


EXHAUSTED = "Failed getting connection; pool exhausted"


def test_exhausted_pool_waits_for_a_free_connection(monkeypatch):
    connection = object()
    pool = Mock()
    pool.get_connection.side_effect = [PoolError(EXHAUSTED), PoolError(EXHAUSTED), connection]
    monkeypatch.setattr(database.time, "sleep", lambda seconds: None)
    assert database._wait_for_connection(pool, 5) is connection
    assert pool.get_connection.call_count == 3


def test_pool_wait_is_bounded(monkeypatch):
    pool = Mock()
    pool.get_connection.side_effect = PoolError(EXHAUSTED)
    clock = iter([0.0, 0.5, 1.0, 1.5, 2.5])
    monkeypatch.setattr(database.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(database.time, "sleep", lambda seconds: None)
    with pytest.raises(PoolError):
        database._wait_for_connection(pool, 2)


def test_other_pool_errors_are_not_retried():
    pool = Mock()
    pool.get_connection.side_effect = PoolError("Pool name is too long")
    with pytest.raises(PoolError):
        database._wait_for_connection(pool, 5)
    assert pool.get_connection.call_count == 1


@pytest.mark.parametrize("errno", [1054, 1146])
def test_outdated_schema_is_logged_as_a_missing_migration(client, monkeypatch, caplog, errno):
    from backend import reports
    monkeypatch.setattr(reports, "list_report_records",
                        Mock(side_effect=mysql.connector.ProgrammingError("Unknown column 's.StatoVerifica'", errno=errno)))
    with caplog.at_level(logging.ERROR):
        response = client.get("/api/segnalazioni?ordina=recenti")
    assert response.status_code == 503 and "aggiornamento" in response.get_json()["error"]
    assert "migrazioni" in caplog.text and "StatoVerifica" not in response.get_data(as_text=True)


def test_exhausted_pool_after_waiting_is_reported_as_busy(client, monkeypatch, caplog):
    from backend import reports
    monkeypatch.setattr(reports, "list_report_records", Mock(side_effect=PoolError(EXHAUSTED)))
    with caplog.at_level(logging.ERROR):
        response = client.get("/api/segnalazioni?ordina=recenti")
    assert response.status_code == 503 and "occupato" in response.get_json()["error"]
    assert "DB_POOL_SIZE" in caplog.text


def test_generic_database_outage_keeps_the_previous_message(client, monkeypatch):
    from backend import reports
    monkeypatch.setattr(reports, "list_report_records", Mock(side_effect=mysql.connector.Error(errno=2013)))
    response = client.get("/api/segnalazioni")
    assert response.status_code == 503 and response.get_json()["error"] == "Database non disponibile. Riprova più tardi."


def test_csp_allows_maplibre_source_maps_and_google_fonts(client):
    policy = client.get("/login").headers["Content-Security-Policy"]
    directives = {part.split()[0]: part.split()[1:] for part in policy.split("; ")}
    assert directives["connect-src"] == ["'self'", "https://tiles.openfreemap.org", "https://unpkg.com"]
    assert "https://fonts.googleapis.com" in directives["style-src"]
    assert "https://fonts.gstatic.com" in directives["font-src"]
    assert directives["script-src"] == ["'self'", "https://unpkg.com"]  # nessun 'unsafe-inline' aggiunto
