"""Application factory: configurazione ed estensioni, senza logica delle pagine."""

import os
import secrets
from datetime import timedelta

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash

from backend.database import ROOT_DIR, init_demo_store
from backend.security import csrf, limiter, load_current_user


def create_app(test_config=None):
    load_dotenv(ROOT_DIR / ".env")
    app = Flask(
        __name__,
        template_folder=str(ROOT_DIR / "frontend" / "templates"),
        static_folder=str(ROOT_DIR / "frontend" / "static"),
        static_url_path="/static",
    )
    app.config.from_mapping(
        APP_MODE=os.getenv("APP_MODE", "demo"),
        SECRET_KEY=os.getenv("SECRET_KEY") or os.getenv("SESSION_SECRET"),
        SESSION_COOKIE_NAME="nostra_citta_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
        SESSION_REFRESH_EACH_REQUEST=False,
        WTF_CSRF_TIME_LIMIT=3600,
        MAX_CONTENT_LENGTH=64 * 1024,
        RATELIMIT_STORAGE_URI=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
        RATELIMIT_HEADERS_ENABLED=True,
    )
    if test_config:
        app.config.update(test_config)
    if app.config["APP_MODE"] not in {"demo", "database"}:
        raise RuntimeError("APP_MODE deve essere demo oppure database.")

    secret = app.config["SECRET_KEY"]
    if not secret:
        if app.config["APP_MODE"] == "database":
            raise RuntimeError("Imposta SECRET_KEY nel file .env (almeno 32 caratteri casuali).")
        # Solo demo: chiave effimera; al riavvio le sessioni non sono più valide.
        app.config["SECRET_KEY"] = secrets.token_hex(32)
    elif len(secret) < 32 or secret.startswith("replace-with"):
        raise RuntimeError("SECRET_KEY deve contenere almeno 32 caratteri casuali.")

    init_demo_store(app)
    # Un hash fittizio rende simile il costo del login anche per email inesistenti.
    app.extensions["dummy_password_hash"] = generate_password_hash(secrets.token_urlsafe(32))
    app.before_request(load_current_user)
    csrf.init_app(app)
    limiter.init_app(app)

    from backend.auth import auth
    from backend.pages import pages
    from backend.reports import reports

    app.register_blueprint(auth)
    app.register_blueprint(pages)
    app.register_blueprint(reports)

    def error_response(message, status):
        if request.path.startswith("/api/"):
            return jsonify(error=message), status
        return render_template("error.html", message=message, status=status), status

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return error_response("Il modulo è scaduto o non è valido. Ricarica la pagina e riprova.", 400)

    @app.errorhandler(mysql.connector.Error)
    def database_error(error):
        # Niente password, query o dati dell'utente nei messaggi di errore.
        app.logger.error("Errore MySQL (codice %s)", error.errno)
        return error_response("Database non disponibile. Riprova più tardi.", 503)

    @app.errorhandler(HTTPException)
    def http_error(error):
        messages = {
            400: "Richiesta non valida.",
            404: "Pagina non trovata.",
            405: "Metodo non consentito.",
            413: "Il contenuto inviato è troppo grande.",
            429: "Troppi tentativi. Attendi prima di riprovare.",
        }
        return error_response(messages.get(error.code, "Richiesta non riuscita."), error.code)

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        )
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    return app


if __name__ == "__main__":
    create_app().run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
