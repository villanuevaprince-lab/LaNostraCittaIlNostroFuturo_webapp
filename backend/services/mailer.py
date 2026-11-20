"""Invio email: SMTP in produzione, cartella locale in sviluppo, memoria nei test.

Backend scelto con MAIL_BACKEND:
- "smtp": server SMTP configurato con MAIL_SERVER/MAIL_PORT/MAIL_USERNAME/MAIL_PASSWORD,
  STARTTLS (MAIL_USE_TLS) oppure TLS implicito (MAIL_USE_SSL);
- "file": ogni messaggio diventa un file .eml in MAIL_OUTBOX_DIR (sviluppo, nessun server);
- "memory": i messaggi restano in app.extensions["mail_outbox"] (test).
"""

import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
import secrets

from flask import current_app


class MailError(RuntimeError):
    pass


def absolute_url(path):
    """Link per le email costruiti da APP_BASE_URL, mai dall'header Host della richiesta."""
    return current_app.config["APP_BASE_URL"].rstrip("/") + path


def _message(to, subject, body):
    config = current_app.config
    message = EmailMessage()
    message["From"] = config["MAIL_FROM"]
    message["To"] = to
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=config["MAIL_FROM"].rsplit("@", 1)[-1].strip("> ") or None)
    message.set_content(body)
    return message


def _send_smtp(message):
    config = current_app.config
    context = ssl.create_default_context()
    if config["MAIL_USE_SSL"]:
        server = smtplib.SMTP_SSL(config["MAIL_SERVER"], config["MAIL_PORT"], context=context, timeout=15)
    else:
        server = smtplib.SMTP(config["MAIL_SERVER"], config["MAIL_PORT"], timeout=15)
    with server:
        if config["MAIL_USE_TLS"] and not config["MAIL_USE_SSL"]:
            server.starttls(context=context)
        if config["MAIL_USERNAME"]:
            server.login(config["MAIL_USERNAME"], config["MAIL_PASSWORD"])
        server.send_message(message)


def _save_file(message):
    folder = Path(current_app.config["MAIL_OUTBOX_DIR"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(4)}.eml"
    path.write_bytes(bytes(message))
    # Solo il percorso nel log: il corpo contiene link con token da non spargere nei log.
    current_app.logger.warning("Nessun server SMTP configurato: email salvata in %s", path)


def send_email(to, subject, body):
    message = _message(to, subject, body)
    backend = current_app.config["MAIL_BACKEND"]
    try:
        if backend == "memory":
            current_app.extensions.setdefault("mail_outbox", []).append(message)
        elif backend == "smtp":
            _send_smtp(message)
        elif backend == "file":
            _save_file(message)
        else:
            raise MailError(f"MAIL_BACKEND non valido: {backend}")
    except (OSError, smtplib.SMTPException) as error:
        current_app.logger.error("Invio email non riuscito (%s)", type(error).__name__)
        raise MailError("Invio email non riuscito.") from error
