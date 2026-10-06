import os
from pathlib import Path

import mysql.connector
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from backend.database import create_report, database_enabled, list_reports


ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "frontend"


def create_app():
    app = Flask(
        __name__,
        static_folder=str(FRONTEND_DIR),
        static_url_path="",
    )
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    @app.get("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "database": "aiven" if database_enabled() else "demo",
            }
        )

    @app.get("/api/segnalazioni")
    def get_reports():
        search = request.args.get("q", "").strip()
        return jsonify(list_reports(search))

    @app.post("/api/segnalazioni")
    def post_report():
        data = request.get_json(silent=True) or {}
        errors = validate_report(data)

        if errors:
            return jsonify({"error": "Dati non validi", "fields": errors}), 400

        report = create_report(
            {
                "id_autore": int(data["id_autore"]),
                "tipo": data["tipo"].strip().lower(),
                "titolo": data["titolo"].strip(),
                "descrizione": data["descrizione"].strip(),
                "indirizzo": data.get("indirizzo", "").strip(),
            }
        )
        return jsonify(report), 201

    @app.errorhandler(mysql.connector.Error)
    def database_error(error):
        app.logger.error("Errore MySQL: %s", error)
        return (
            jsonify(
                {
                    "error": "Database non disponibile",
                    "detail": "Controlla le variabili Aiven nel file .env.",
                }
            ),
            503,
        )

    return app


def validate_report(data):
    errors = {}
    tipo = str(data.get("tipo", "")).strip().lower()
    titolo = str(data.get("titolo", "")).strip()
    descrizione = str(data.get("descrizione", "")).strip()

    if tipo not in {"segnalazione", "proposta"}:
        errors["tipo"] = "Scegli segnalazione o proposta."
    if not 3 <= len(titolo) <= 200:
        errors["titolo"] = "Il titolo deve contenere da 3 a 200 caratteri."
    if not 10 <= len(descrizione) <= 5000:
        errors["descrizione"] = "La descrizione deve contenere almeno 10 caratteri."

    try:
        if int(data.get("id_autore", 0)) <= 0:
            raise ValueError
    except (TypeError, ValueError):
        errors["id_autore"] = "Inserisci un ID utente valido."

    return errors


app = create_app()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "1") == "1",
    )

