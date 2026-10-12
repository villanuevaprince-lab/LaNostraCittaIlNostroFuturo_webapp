"""Connessione MySQL e repository segnalazioni; nessuna migrazione automatica."""

import os
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, RLock

import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool
from flask import current_app


ROOT_DIR = Path(__file__).resolve().parents[1]
DEMO_REPORTS = [
    {
        "id": 1, "tipo": "segnalazione", "titolo": "Buca sul marciapiede",
        "descrizione": "Una buca rende difficile il passaggio dei pedoni.",
        "stato": "aperta", "indirizzo": "Via Torino, Milano", "autore": "Marco Rossi",
        "data_creazione": "2026-09-10T08:45:00", "sostegni": 2,
    },
    {
        "id": 2, "tipo": "proposta", "titolo": "Nuove rastrelliere per biciclette",
        "descrizione": "Installare rastrelliere vicino agli ingressi delle scuole.",
        "stato": "in_valutazione", "indirizzo": "Milano", "autore": "Giulia Bianchi",
        "data_creazione": "2026-09-12T15:00:00", "sostegni": 5,
    },
]
DEMO_NEIGHBORHOODS = [
    {"id": 1, "nome": "Centro Storico", "municipio": 1},
    {"id": 2, "nome": "Città Studi - Lambrate - Venezia", "municipio": 3},
    {"id": 3, "nome": "Baggio - De Angeli - San Siro", "municipio": 7},
]
DEMO_CATEGORIES = [
    {"id": 1, "nome": "Ambiente", "descrizione": "Verde e tutela ambientale.", "colore": "#2E7D32"},
    {"id": 2, "nome": "Mobilità urbana", "descrizione": "Traffico e trasporti.", "colore": "#1565C0"},
    {"id": 3, "nome": "Decoro urbano", "descrizione": "Pulizia e manutenzione.", "colore": "#8D6E63"},
    {"id": 4, "nome": "Illuminazione", "descrizione": "Illuminazione pubblica.", "colore": "#F9A825"},
    {"id": 5, "nome": "Accessibilità", "descrizione": "Accessibilità e inclusione.", "colore": "#00838F"},
]


def init_demo_store(app):
    # Una copia per applicazione: test isolati e nessun dato demo condiviso fra app.
    app.extensions["demo_store"] = {
        "users": {}, "reports": deepcopy(DEMO_REPORTS),
        "quartieri": deepcopy(DEMO_NEIGHBORHOODS),
        "categorie": deepcopy(DEMO_CATEGORIES), "comments": {}, "supports": set(),
        "moderators": set(), "lock": RLock(),
    }


def demo_store():
    return current_app.extensions["demo_store"]


def database_enabled():
    return current_app.config["APP_MODE"] == "database"


def get_connection():
    required = ("DB_HOST", "DB_USER", "DB_PASSWORD")
    if any(not os.getenv(key) for key in required):
        raise mysql.connector.InterfaceError("Configurazione MySQL incompleta.")
    ca_path = ROOT_DIR / os.getenv("DB_SSL_CA_PATH", "certificates/ca.pem")
    if not ca_path.is_file():
        # Non degradare silenziosamente a una connessione senza verifica TLS.
        raise mysql.connector.InterfaceError("Certificato CA MySQL mancante.")
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


def list_reports(search=""):
    if not database_enabled():
        store = demo_store()
        with store["lock"]:
            term = search.casefold()
            return deepcopy([
                report for report in store["reports"]
                if not term or any(term in report[field].casefold()
                                   for field in ("titolo", "descrizione", "indirizzo"))
            ])

    query = """
        SELECT s.IdSegnalazione AS id, s.Tipo AS tipo, s.Titolo AS titolo,
            s.Descrizione AS descrizione, s.Stato AS stato,
            COALESCE(s.Indirizzo, '') AS indirizzo,
            CONCAT(u.Nome, ' ', u.Cognome) AS autore,
            s.DataCreazione AS data_creazione,
            (SELECT COUNT(*) FROM SOSTEGNO so
             WHERE so.IdSegnalazione = s.IdSegnalazione AND so.DataRitiro IS NULL) AS sostegni
        FROM SEGNALAZIONE s
        JOIN UTENTE u ON u.IdUtente = s.IdAutore
        WHERE s.Visibilita = 'pubblica'
          AND (%s = '' OR s.Titolo LIKE %s OR s.Descrizione LIKE %s
               OR COALESCE(s.Indirizzo, '') LIKE %s)
        ORDER BY s.DataCreazione DESC, s.IdSegnalazione DESC
        LIMIT 100
    """
    like_term = f"%{search}%"
    with database_cursor() as cursor:
        cursor.execute(query, (search, like_term, like_term, like_term))
        rows = cursor.fetchall()
    for row in rows:
        row["data_creazione"] = row["data_creazione"].isoformat(timespec="seconds")
    return rows


def create_report(data, author):
    """author è sempre l'utente caricato dal server a partire dalla sessione."""
    report = {
        **data, "autore": f"{author['nome']} {author['cognome']}",
        "stato": "aperta" if data["tipo"] == "segnalazione" else "in_valutazione",
        "data_creazione": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sostegni": 0,
    }
    if not database_enabled():
        store = demo_store()
        with store["lock"]:
            report["id"] = max((item["id"] for item in store["reports"]), default=0) + 1
            store["reports"].insert(0, report)
        return deepcopy(report)

    query = """
        INSERT INTO SEGNALAZIONE
            (IdAutore, Tipo, Titolo, Descrizione, Stato, Visibilita, Indirizzo)
        VALUES (%s, %s, %s, %s, %s, 'pubblica', %s)
    """
    with database_cursor(write=True) as cursor:
        cursor.execute(query, (
            author["id"], data["tipo"], data["titolo"], data["descrizione"],
            report["stato"], data.get("indirizzo") or None,
        ))
        report["id"] = cursor.lastrowid
    return report
