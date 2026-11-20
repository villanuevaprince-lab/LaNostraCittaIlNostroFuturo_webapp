"""Application factory: configurazione ed estensioni, senza logica delle pagine."""

import os
import secrets
from datetime import timedelta
from pathlib import Path

import click
import mysql.connector
from mysql.connector.errors import PoolError
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash

from backend.database import ROOT_DIR
from backend.security import csrf, enforce_ban, limiter, load_current_user


# 1054 colonna inesistente, 1146 tabella inesistente: il codice è più nuovo dello schema.
SCHEMA_ERRORS = {1054, 1146}


def _env_float(name, default):
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


def _env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return int(default)


def _env_bool(name, default):
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _project_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT_DIR / path


def create_app(test_config=None):
    load_dotenv(ROOT_DIR / ".env")
    upload_folder = _project_path(os.getenv("UPLOAD_FOLDER", "storage/uploads"))
    app = Flask(
        __name__,
        template_folder=str(ROOT_DIR / "frontend" / "templates"),
        static_folder=str(ROOT_DIR / "frontend" / "static"),
        static_url_path="/static",
    )
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY") or os.getenv("SESSION_SECRET"),
        SESSION_COOKIE_NAME="nostra_citta_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
        SESSION_REFRESH_EACH_REQUEST=False,
        WTF_CSRF_TIME_LIMIT=3600,
        MAX_CONTENT_LENGTH=21 * 1024 * 1024,
        UPLOAD_FOLDER=str(upload_folder.resolve()),
        RATELIMIT_STORAGE_URI=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
        RATELIMIT_HEADERS_ENABLED=True,
        # IA locale con Ollama: i controlli girano sul server, mai nel browser.
        AI_ENABLED=os.getenv("AI_ENABLED", "true").lower() == "true",
        OLLAMA_URL=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        OLLAMA_TEXT_MODEL=os.getenv("OLLAMA_TEXT_MODEL", "qwen2.5:7b"),
        OLLAMA_VISION_MODEL=os.getenv("OLLAMA_VISION_MODEL", "qwen2.5vl:7b"),
        OLLAMA_TIMEOUT_TEXT=_env_float("OLLAMA_TIMEOUT_TEXT", 20),
        OLLAMA_TIMEOUT_VISION=_env_float("OLLAMA_TIMEOUT_VISION", 60),
        # Verifica AI prima della pubblicazione (coda + worker). Soglie: vedi services/verification_rules.py
        VERIFICA_MODELLO=os.getenv("VERIFICA_MODELLO") or os.getenv("OLLAMA_VISION_MODEL", "qwen2.5vl:7b"),
        VERIFICA_TIMEOUT=_env_float("VERIFICA_TIMEOUT", 120),
        VERIFICA_SOGLIA_ALTA=_env_float("VERIFICA_SOGLIA_ALTA", 0.90),
        VERIFICA_SOGLIA_BASSA=_env_float("VERIFICA_SOGLIA_BASSA", 0.70),
        VERIFICA_MAX_TENTATIVI=_env_int("VERIFICA_MAX_TENTATIVI", 5),
        VERIFICA_BACKOFF_BASE=_env_int("VERIFICA_BACKOFF_BASE", 30),
        VERIFICA_BACKOFF_MAX=_env_int("VERIFICA_BACKOFF_MAX", 3600),
        VERIFICA_INTERVALLO=_env_float("VERIFICA_INTERVALLO", 10),
        VERIFICA_LEASE_SECONDI=_env_int("VERIFICA_LEASE_SECONDI", 900),
        VERIFICA_MAX_REINVII=_env_int("VERIFICA_MAX_REINVII", 3),
        # Email: SMTP se MAIL_SERVER è impostato, altrimenti file .eml locali (sviluppo).
        MAIL_BACKEND=os.getenv("MAIL_BACKEND") or ("smtp" if os.getenv("MAIL_SERVER") else "file"),
        MAIL_SERVER=os.getenv("MAIL_SERVER", ""),
        MAIL_PORT=_env_int("MAIL_PORT", 587),
        MAIL_USERNAME=os.getenv("MAIL_USERNAME", ""),
        MAIL_PASSWORD=os.getenv("MAIL_PASSWORD", ""),
        MAIL_USE_TLS=_env_bool("MAIL_USE_TLS", "true"),
        MAIL_USE_SSL=_env_bool("MAIL_USE_SSL", "false"),
        MAIL_FROM=os.getenv("MAIL_FROM", "La Nostra Città <noreply@localhost>"),
        MAIL_OUTBOX_DIR=str(_project_path(os.getenv("MAIL_OUTBOX_DIR", "storage/mail_outbox"))),
        # Base dei link nelle email: mai dedotta dall'header Host (evita link avvelenati).
        APP_BASE_URL=os.getenv("APP_BASE_URL", "http://localhost:3000"),
        PASSWORD_RESET_MAX_AGE=_env_int("PASSWORD_RESET_MAX_AGE", 1800),
        EMAIL_CHANGE_MAX_AGE=_env_int("EMAIL_CHANGE_MAX_AGE", 3600),
    )
    if test_config:
        app.config.update(test_config)
    if os.getenv("APP_MODE", "database") != "database":
        raise RuntimeError("La modalità demo non è disponibile. Rimuovi APP_MODE=demo dal file .env.")

    secret = app.config["SECRET_KEY"]
    if not secret:
        raise RuntimeError("Imposta SECRET_KEY nel file .env (almeno 32 caratteri casuali).")
    elif len(secret) < 32 or secret.startswith("replace-with"):
        raise RuntimeError("SECRET_KEY deve contenere almeno 32 caratteri casuali.")

    # Un hash fittizio rende simile il costo del login anche per email inesistenti.
    app.extensions["dummy_password_hash"] = generate_password_hash(secrets.token_urlsafe(32))
    app.before_request(load_current_user)
    app.before_request(enforce_ban)
    csrf.init_app(app)
    limiter.init_app(app)

    from backend.auth import auth
    from backend.account import account
    from backend.verification_api import verification_api
    from backend.api.ai import ai_api
    from backend.api.auth import auth_api
    from backend.api.catalog import catalog_api
    from backend.api.geo import geo_api
    from backend.pages import pages
    from backend.reports import reports

    app.register_blueprint(auth)
    app.register_blueprint(auth_api)
    app.register_blueprint(account)
    app.register_blueprint(verification_api)
    app.register_blueprint(ai_api)
    app.register_blueprint(catalog_api)
    app.register_blueprint(geo_api)
    app.register_blueprint(pages)
    app.register_blueprint(reports)
    from backend.community import community
    app.register_blueprint(community)

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
        if error.errno in SCHEMA_ERRORS:
            # Codice nuovo su un database senza le migrazioni: va detto chiaramente a chi gestisce il server.
            app.logger.error("Schema del database non aggiornato (codice MySQL %s): applica le migrazioni "
                             "mancanti, ad esempio python -m backend.apply_verification_migration "
                             "(vedi docs/configurazione.md)", error.errno)
            return error_response("Il servizio è in aggiornamento e non è disponibile in questo momento. "
                                  "Riprova più tardi.", 503)
        if isinstance(error, PoolError):
            app.logger.error("Connessioni MySQL esaurite anche dopo l'attesa: aumenta DB_POOL_SIZE "
                             "(e i limiti del piano Aiven) oppure DB_POOL_WAIT")
            return error_response("Il servizio è molto occupato in questo momento. Riprova tra qualche secondo.", 503)
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

    from backend.services.verification_rules import Thresholds
    Thresholds(alta=app.config["VERIFICA_SOGLIA_ALTA"], bassa=app.config["VERIFICA_SOGLIA_BASSA"])  # valida all'avvio

    @app.cli.command("verifica-worker")
    @click.option("--once", is_flag=True, help="Elabora al massimo un job ed esce.")
    @click.option("--intervallo", type=float, default=None, help="Secondi di attesa con coda vuota o modello assente.")
    def verification_worker_command(once, intervallo):
        """Worker della coda di verifica AI (più istanze possono girare insieme)."""
        import logging
        from backend.services.verification_worker import run_forever, run_once
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        if once:
            click.echo(run_once())
        else:
            run_forever(intervallo or app.config["VERIFICA_INTERVALLO"])

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        # Le pagine con token nell'URL impostano già "no-referrer": non va sovrascritto.
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; "
            "script-src 'self' https://unpkg.com; style-src 'self' https://unpkg.com https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            # unpkg.com in connect-src: gli strumenti di sviluppo scaricano da lì la source map di MapLibre.
            "worker-src 'self' blob:; connect-src 'self' https://tiles.openfreemap.org https://unpkg.com; "
            "img-src 'self' data: https://tiles.openfreemap.org"
        )
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    return app


if __name__ == "__main__":
    create_app().run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "3000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
