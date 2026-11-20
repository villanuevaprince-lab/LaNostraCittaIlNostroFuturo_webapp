"""Reset della password e cambio email tramite link firmati (nessuna rete reale)."""
import re
from unittest.mock import Mock

import mysql.connector
import pytest

from backend.app import create_app
from conftest import csrf_token


def outbox(app):
    return app.extensions.setdefault("mail_outbox", [])


def link_in(message, prefix):
    match = re.search(rf"https://citta\.example\.org({re.escape(prefix)}[^\s]+)", message.get_content())
    assert match, message.get_content()
    return match.group(1)


def forgot(client, email):
    return client.post("/password/dimenticata", data={"csrf_token": csrf_token(client, "/password/dimenticata"),
                                                      "email": email})


@pytest.fixture()
def registered(client, submit, users_stub, registration):
    submit("/register", registration)
    submit("/logout")
    return users_stub[registration["email"]]


# --- richiesta di reset ----------------------------------------------------

def test_login_page_links_to_password_reset(client):
    assert 'href="/password/dimenticata"' in client.get("/login").get_data(as_text=True)


def test_reset_request_has_identical_response_for_known_and_unknown_email(app, client, registered, registration):
    known = forgot(client, registration["email"].upper() + " ")
    unknown = forgot(client, "nessuno@example.com")
    assert known.status_code == unknown.status_code == 200

    def visible(response):
        # Il token CSRF cambia a ogni pagina: lo togliamo prima del confronto.
        return re.sub(r'content="[^"]+"', "", response.get_data(as_text=True))
    assert visible(known) == visible(unknown)
    assert "Se l'indirizzo corrisponde a un account" in visible(known)
    messages = outbox(app)
    assert len(messages) == 1 and messages[0]["To"] == registration["email"]
    assert "/password/reimposta/" in messages[0].get_content() and "30 minuti" in messages[0].get_content()


def test_reset_request_validates_format_and_skips_deleted_accounts(app, client, registered, registration):
    assert forgot(client, "non-valida").status_code == 400
    registered["stato_account"] = "cancellato"
    assert forgot(client, registration["email"]).status_code == 200
    assert outbox(app) == []


def test_mail_failure_does_not_change_the_response(app, client, registered, registration, monkeypatch):
    from backend import account
    from backend.services.mailer import MailError
    monkeypatch.setattr(account, "send_email", Mock(side_effect=MailError("giù")))
    response = forgot(client, registration["email"])
    assert response.status_code == 200 and "Se l'indirizzo corrisponde" in response.get_data(as_text=True)


# --- pagina di reset -------------------------------------------------------

def reset_link(app, client, registration):
    forgot(client, registration["email"])
    return link_in(outbox(app)[-1], "/password/reimposta/")


def post_new_password(client, path, password="Nuova-Password-Sicura-1", confirm=None):
    return client.post(path, data={"csrf_token": csrf_token(client, path), "password": password,
                                   "password_confirm": confirm or password})


def test_successful_reset_changes_hash_and_closes_every_session(app, client, users_stub, registration):
    from backend.security import verify_password
    other = app.test_client()  # sessione già aperta su un altro dispositivo
    other.post("/register", data={"csrf_token": csrf_token(other), **registration})
    assert other.get("/profilo").status_code == 200

    path = reset_link(app, client, registration)
    page = client.get(path)
    assert page.status_code == 200 and page.headers["Referrer-Policy"] == "no-referrer"
    response = post_new_password(client, path)
    assert response.status_code == 303 and response.location == "/login"
    user = users_stub[registration["email"]]
    with app.app_context():
        assert verify_password(user["hash_password"], "Nuova-Password-Sicura-1")
        assert not verify_password(user["hash_password"], registration["password"])
    assert other.get("/profilo").status_code == 303  # la vecchia sessione non vale più
    assert outbox(app)[-1]["Subject"].startswith("La tua password è stata cambiata")


def test_reset_token_is_single_use(app, client, registered, registration, users_stub):
    path = reset_link(app, client, registration)
    assert post_new_password(client, path).status_code == 303
    reused = post_new_password(client, path, "Ancora-Altra-Password-2")
    assert reused.status_code == 400 and "già stato usato" in reused.get_data(as_text=True)
    assert client.get(path).status_code == 400


def test_expired_and_tampered_tokens_are_rejected(app, client, registered, registration):
    path = reset_link(app, client, registration)
    assert client.get(path + "x").status_code == 400
    app.config["PASSWORD_RESET_MAX_AGE"] = -1  # qualunque token è ormai scaduto
    response = client.get(path)
    assert response.status_code == 400 and "scaduto" in response.get_data(as_text=True)


def test_token_signed_with_another_purpose_is_rejected(app, client, registered):
    from itsdangerous import URLSafeTimedSerializer
    token = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="email-change").dumps({"u": registered["id"], "f": "x"})
    assert client.get(f"/password/reimposta/{token}").status_code == 400


def test_reset_password_rules(app, client, registered, registration):
    path = reset_link(app, client, registration)
    assert post_new_password(client, path, "corta").status_code == 400
    assert post_new_password(client, path, "Nuova-Password-Sicura-1", "Diversa-Password-Sicura-1").status_code == 400


def test_banned_user_can_reset_the_password(app, client, registered, registration):
    registered["stato_account"] = "bloccato"
    path = reset_link(app, client, registration)
    assert post_new_password(client, path).status_code == 303


def test_reset_request_is_rate_limited_per_email(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_MODE", raising=False)
    limited = create_app({"TESTING": True, "SECRET_KEY": "only-for-local-tests-" + "x" * 32,
                          "RATELIMIT_ENABLED": True, "RATELIMIT_STORAGE_URI": "memory://",
                          "SESSION_COOKIE_SECURE": False, "MAIL_BACKEND": "memory",
                          "UPLOAD_FOLDER": str(tmp_path)})
    from backend import account
    monkeypatch.setattr(account, "find_user_by_email", lambda email: None)
    client = limited.test_client()
    codes = [forgot(client, "vittima@example.com").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    assert forgot(client, "altra@example.com").status_code == 200  # il limite per email è separato


# --- cambio email ----------------------------------------------------------

def request_change(client, new_email, password):
    return client.post("/api/auth/me/email", json={"nuova_email": new_email, "password": password},
                       headers={"X-CSRFToken": csrf_token(client)})


def test_email_change_requires_login_and_current_password(app, client, logged_in, registration):
    assert request_change(client, "nuova@example.com", "sbagliata").status_code == 400
    assert request_change(client, "non-valida", registration["password"]).status_code == 400
    assert request_change(client, registration["email"].upper(), registration["password"]).status_code == 400
    assert outbox(app) == []
    client.post("/api/auth/logout", headers={"X-CSRFToken": csrf_token(client, "/profilo")})
    assert request_change(client, "nuova@example.com", "x").status_code == 401


def test_email_change_is_confirmed_through_the_new_address(app, client, logged_in, users_stub, registration):
    response = request_change(client, " Nuova@Example.com ", registration["password"])
    assert response.status_code == 200 and "link di conferma" in response.get_json()["message"]
    message = outbox(app)[-1]
    assert message["To"] == "nuova@example.com"
    path = link_in(message, "/email/conferma/")
    page = client.get(path)
    assert page.status_code == 200 and "nuova@example.com" in page.get_data(as_text=True)
    assert registration["email"] in users_stub  # una GET non cambia nulla
    confirmed = client.post(path, data={"csrf_token": csrf_token(client, path)})
    assert confirmed.status_code == 303 and confirmed.location == "/profilo"
    assert "nuova@example.com" in users_stub and registration["email"] not in users_stub
    assert outbox(app)[-1]["To"] == registration["email"]  # avviso al vecchio indirizzo
    again = client.post(path, data={"csrf_token": csrf_token(client, path)})
    assert again.status_code == 400  # token monouso


def test_email_already_in_use_gets_the_same_answer_and_no_mail(app, client, logged_in, users_stub, registration):
    users_stub["occupata@example.com"] = {**users_stub[registration["email"]], "id": 999,
                                          "email": "occupata@example.com"}
    response = request_change(client, "occupata@example.com", registration["password"])
    assert response.status_code == 200 and "link di conferma" in response.get_json()["message"]
    assert outbox(app) == []


def test_email_taken_between_request_and_confirmation(app, client, logged_in, users_stub, registration):
    request_change(client, "nuova@example.com", registration["password"])
    path = link_in(outbox(app)[-1], "/email/conferma/")
    users_stub["nuova@example.com"] = {**users_stub[registration["email"]], "id": 999, "email": "nuova@example.com"}
    response = client.post(path, data={"csrf_token": csrf_token(client, path)})
    assert response.status_code == 409 and "già usato" in response.get_data(as_text=True)


def test_expired_email_link_is_rejected(app, client, logged_in, registration):
    request_change(client, "nuova@example.com", registration["password"])
    path = link_in(outbox(app)[-1], "/email/conferma/")
    app.config["EMAIL_CHANGE_MAX_AGE"] = -1
    assert client.get(path).status_code == 400


def test_mail_server_failure_is_reported_on_email_change(client, logged_in, registration, monkeypatch):
    from backend import account
    from backend.services.mailer import MailError
    monkeypatch.setattr(account, "send_email", Mock(side_effect=MailError("giù")))
    assert request_change(client, "nuova@example.com", registration["password"]).status_code == 503


# --- registrazione: email reali normalizzate -------------------------------

def test_registration_stores_the_user_email_normalized(submit, users_stub, registration):
    submit("/register", {**registration, "email": "  Mario.Bianchi@Example.ORG "})
    assert "mario.bianchi@example.org" in users_stub


# --- repository e invio ----------------------------------------------------

def test_reset_query_is_conditional_and_bumps_session_version(fake_mysql):
    from backend.users import reset_password_hash
    _, cursor = fake_mysql
    cursor.rowcount = 1
    assert reset_password_hash(5, "old-hash", "new-hash") is True
    sql, params = cursor.execute.call_args_list[0].args
    assert "SessionVersion=SessionVersion+1" in sql and "HashPassword=%s AND" in sql
    assert params == ("new-hash", 5, "old-hash")
    cursor.rowcount = 0
    assert reset_password_hash(5, "old-hash", "new-hash") is False


def test_change_email_query_and_duplicate(fake_mysql):
    from backend.users import DuplicateEmail, change_email
    _, cursor = fake_mysql
    cursor.rowcount = 1
    assert change_email(5, "Old@Example.com", "New@Example.com") is True
    sql, params = cursor.execute.call_args_list[0].args
    assert "WHERE IdUtente=%s AND Email=%s" in sql and params == ("new@example.com", 5, "old@example.com")
    cursor.execute.side_effect = mysql.connector.IntegrityError(errno=1062)
    with pytest.raises(DuplicateEmail):
        change_email(5, "old@example.com", "new@example.com")


def test_file_backend_writes_eml_without_logging_the_body(app, tmp_path, caplog):
    from backend.services.mailer import send_email
    app.config.update(MAIL_BACKEND="file", MAIL_OUTBOX_DIR=str(tmp_path / "mail"))
    with app.app_context():
        send_email("persona@example.com", "Oggetto", "link segreto https://x/token")
    files = list((tmp_path / "mail").glob("*.eml"))
    assert len(files) == 1 and b"persona@example.com" in files[0].read_bytes()
    assert "token" not in caplog.text


def test_smtp_backend_uses_starttls_and_login(app, monkeypatch):
    from backend.services import mailer
    server = Mock()
    server.__enter__ = Mock(return_value=server)
    server.__exit__ = Mock(return_value=False)
    smtp = Mock(return_value=server)
    monkeypatch.setattr(mailer.smtplib, "SMTP", smtp)
    app.config.update(MAIL_BACKEND="smtp", MAIL_SERVER="smtp.example.org", MAIL_PORT=587,
                      MAIL_USERNAME="utente", MAIL_PASSWORD="segreta", MAIL_USE_TLS=True, MAIL_USE_SSL=False)
    with app.app_context():
        mailer.send_email("persona@example.com", "Oggetto", "Corpo")
    smtp.assert_called_once_with("smtp.example.org", 587, timeout=15)
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("utente", "segreta")
    server.send_message.assert_called_once()


def test_smtp_errors_become_mail_error(app, monkeypatch):
    from backend.services import mailer
    monkeypatch.setattr(mailer.smtplib, "SMTP", Mock(side_effect=ConnectionRefusedError()))
    app.config.update(MAIL_BACKEND="smtp", MAIL_SERVER="smtp.example.org")
    with app.app_context(), pytest.raises(mailer.MailError):
        mailer.send_email("persona@example.com", "Oggetto", "Corpo")
