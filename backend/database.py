import os
from datetime import datetime
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


DEMO_REPORTS = [
    {
        "id": 1,
        "tipo": "segnalazione",
        "titolo": "Buca sul marciapiede",
        "descrizione": "Una buca rende difficile il passaggio dei pedoni.",
        "stato": "aperta",
        "indirizzo": "Via Torino, Milano",
        "autore": "Marco Rossi",
        "data_creazione": "2026-09-10T08:45:00",
        "sostegni": 2,
    },
    {
        "id": 2,
        "tipo": "proposta",
        "titolo": "Nuove rastrelliere per biciclette",
        "descrizione": "Installare rastrelliere vicino agli ingressi delle scuole.",
        "stato": "in_valutazione",
        "indirizzo": "Milano",
        "autore": "Giulia Bianchi",
        "data_creazione": "2026-09-12T15:00:00",
        "sostegni": 5,
    },
]


def database_enabled():
    return os.getenv("APP_MODE", "demo").lower() == "database"


def get_connection():
    config = {
        "host": os.environ["DB_HOST"],
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
        "database": os.getenv("DB_NAME", "nostra_citta"),
        "connection_timeout": 10,
    }

    ca_path = os.getenv("DB_SSL_CA_PATH")
    if ca_path:
        resolved_ca = ROOT_DIR / ca_path
        if resolved_ca.exists():
            config.update(
                {
                    "ssl_ca": str(resolved_ca),
                    "ssl_verify_cert": True,
                    "ssl_verify_identity": True,
                }
            )

    return mysql.connector.connect(**config)


def list_reports(search=""):
    if not database_enabled():
        term = search.casefold()
        return [
            report
            for report in DEMO_REPORTS
            if not term
            or term in report["titolo"].casefold()
            or term in report["descrizione"].casefold()
            or term in report["indirizzo"].casefold()
        ]

    query = """
        SELECT
            s.IdSegnalazione AS id,
            s.Tipo AS tipo,
            s.Titolo AS titolo,
            s.Descrizione AS descrizione,
            s.Stato AS stato,
            COALESCE(s.Indirizzo, '') AS indirizzo,
            CONCAT(u.Nome, ' ', u.Cognome) AS autore,
            s.DataCreazione AS data_creazione,
            COUNT(DISTINCT CASE
                WHEN so.DataRitiro IS NULL THEN so.IdSostegno
            END) AS sostegni
        FROM SEGNALAZIONE s
        JOIN UTENTE u ON u.IdUtente = s.IdAutore
        LEFT JOIN SOSTEGNO so ON so.IdSegnalazione = s.IdSegnalazione
        WHERE s.Visibilita = 'pubblica'
          AND (
              %s = ''
              OR s.Titolo LIKE %s
              OR s.Descrizione LIKE %s
              OR COALESCE(s.Indirizzo, '') LIKE %s
          )
        GROUP BY
            s.IdSegnalazione, s.Tipo, s.Titolo, s.Descrizione,
            s.Stato, s.Indirizzo, u.Nome, u.Cognome, s.DataCreazione
        ORDER BY s.DataCreazione DESC
        LIMIT 100
    """
    like_term = f"%{search}%"

    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, (search, like_term, like_term, like_term))
        return cursor.fetchall()
    finally:
        connection.close()


def create_report(data):
    if not database_enabled():
        report = {
            "id": max((item["id"] for item in DEMO_REPORTS), default=0) + 1,
            "tipo": data["tipo"],
            "titolo": data["titolo"],
            "descrizione": data["descrizione"],
            "stato": "aperta" if data["tipo"] == "segnalazione" else "in_valutazione",
            "indirizzo": data.get("indirizzo", ""),
            "autore": f"Utente #{data['id_autore']}",
            "data_creazione": datetime.now().isoformat(timespec="seconds"),
            "sostegni": 0,
        }
        DEMO_REPORTS.insert(0, report)
        return report

    query = """
        INSERT INTO SEGNALAZIONE (
            IdAutore, Tipo, Titolo, Descrizione,
            Stato, Visibilita, Indirizzo
        )
        VALUES (%s, %s, %s, %s, %s, 'pubblica', %s)
    """
    stato = "aperta" if data["tipo"] == "segnalazione" else "in_valutazione"

    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            query,
            (
                data["id_autore"],
                data["tipo"],
                data["titolo"],
                data["descrizione"],
                stato,
                data.get("indirizzo") or None,
            ),
        )
        connection.commit()
        report_id = cursor.lastrowid
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return {
        "id": report_id,
        "tipo": data["tipo"],
        "titolo": data["titolo"],
        "descrizione": data["descrizione"],
        "stato": stato,
        "indirizzo": data.get("indirizzo", ""),
        "autore": f"Utente #{data['id_autore']}",
        "data_creazione": datetime.now().isoformat(timespec="seconds"),
        "sostegni": 0,
    }

