"""Pool MySQL Aiven, transazioni e verifica TLS; nessuna migrazione automatica."""

import os
import hashlib
import tempfile
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool
from flask import current_app


ROOT_DIR = Path(__file__).resolve().parents[1]


def _get_ssl_ca_path():
    ca_content = os.getenv("DB_SSL_CA", "").strip()
    if ca_content:
        ca_content = ca_content.replace("\\n", "\n")
        ca_path = Path(tempfile.gettempdir()) / (
            f"nostra-citta-ca-{hashlib.sha256(ca_content.encode()).hexdigest()}.pem"
        )
        if not ca_path.exists():
            ca_path.write_text(ca_content + "\n", encoding="utf-8")
        return ca_path
    configured_path = os.getenv("DB_SSL_CA_PATH", "certificates/ca.pem")
    return ROOT_DIR / configured_path


def get_connection():
    required = ("DB_HOST", "DB_USER", "DB_PASSWORD")
    if any(not os.getenv(key) or os.getenv(key, "").startswith("replace-with") for key in required):
        raise mysql.connector.InterfaceError("Configurazione MySQL incompleta.")
    ca_path = _get_ssl_ca_path()
    if not ca_path.is_file():
        # Non degradare silenziosamente a una connessione senza verifica TLS.
        raise mysql.connector.InterfaceError("Certificato CA MySQL mancante: imposta DB_SSL_CA.")
    try:
        port = int(os.getenv("DB_PORT", "3306"))
        pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
    except ValueError as error:
        raise mysql.connector.InterfaceError("Porta o dimensione pool MySQL non valida.") from error
    if not 1 <= pool_size <= 32:
        raise mysql.connector.InterfaceError("Dimensione pool MySQL fuori limite.")
    app = current_app._get_current_object()
    pool = app.extensions.get("mysql_pool")
    if pool is None:
        lock = app.extensions.setdefault("mysql_pool_lock", Lock())
        with lock:
            pool = app.extensions.get("mysql_pool")
            if pool is None:
                pool = MySQLConnectionPool(
                    pool_name=f"nostra_{id(app):x}", pool_size=pool_size, pool_reset_session=True,
                    host=os.environ["DB_HOST"], port=port,
                    user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
                    database=os.getenv("DB_NAME", "nostra_citta"), connection_timeout=10,
                    ssl_ca=str(ca_path), ssl_verify_cert=True, ssl_verify_identity=True,
                )
                app.extensions["mysql_pool"] = pool
    return pool.get_connection()


@contextmanager
def database_cursor(write=False):
    """Parametri SQL separati dal testo, commit solo al successo e chiusura garantita."""
    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        yield cursor
        if write:
            connection.commit()
    except Exception:
        if write:
            connection.rollback()
        raise
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            connection.close()
