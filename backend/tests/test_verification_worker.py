"""Worker: transizioni con modello assente, errori, successo. Repository simulato in memoria."""
from unittest.mock import Mock

import pytest

from backend.repositories import verification as queue
from backend.services import verification_worker as worker
from backend.services.verifier import ModelUnavailable, TransientModelError
from verification_fakes import FakeVerifier, output


JOB = {"id": 11, "report_id": 5, "version": 1, "attempts": 0, "waited": False}
REPORT = {"id": 5, "tipo": "segnalazione", "titolo": "Buca in via Roma", "descrizione": "Buca profonda e pericolosa",
          "indirizzo": "Via Roma", "stato": "in_valutazione", "version": 1}


@pytest.fixture()
def repo(app, monkeypatch):
    calls = {}

    def track(name, result=None):
        mock = Mock(return_value=result)
        monkeypatch.setattr(queue, name, mock)
        calls[name] = mock
        return mock
    track("mark_waiting_for_model", 2)
    track("claim_job", dict(JOB))
    track("load_item", (dict(REPORT), [{"id": 1, "mime": "image/jpeg"}, {"id": 2, "mime": "video/mp4"}]))
    track("cancel_stale_job")
    track("release_to_waiting", True)
    track("fail_job", {"esito": "retry", "tentativi": 1, "attesa": 30})
    track("complete_job", {"utente": 101, "titolo": "Buca", "tipo": "verifica_pubblicata", "messaggio": "ok"})
    track("author_email_target", None)
    monkeypatch.setattr(worker, "attachment_content", lambda attachment_id: (b"jpeg-bytes", "image/jpeg"))
    monkeypatch.setattr(worker, "list_categories", lambda: [{"id": 2, "nome": "Mobilità urbana"}])
    with app.app_context():
        yield calls


def test_unavailable_model_moves_jobs_to_waiting_and_claims_nothing(repo):
    assert worker.run_once(FakeVerifier(available=False), "w1") == "modello_non_disponibile"
    repo["mark_waiting_for_model"].assert_called_once()
    repo["claim_job"].assert_not_called()


def test_empty_queue(repo):
    repo["claim_job"].return_value = None
    assert worker.run_once(FakeVerifier(), "w1") == "coda_vuota"


def test_superseded_job_is_closed_without_calling_the_model(repo):
    repo["load_item"].return_value = None
    fake = FakeVerifier()
    assert worker.run_once(fake, "w1") == "job_superato"
    assert fake.calls == [] and repo["cancel_stale_job"].call_args.args[:2] == (JOB, "w1")


def test_success_applies_code_rules_and_passes_images_only(repo):
    fake = FakeVerifier([output("pubblica", confidenza=0.95)])
    assert worker.run_once(fake, "w1") == "pubblica"
    item = fake.calls[0]
    assert item.immagini == [b"jpeg-bytes"] and item.video_allegati == 1 and item.categorie_catalogo[0]["id"] == 2
    job, worker_id, model_name, out, decision, max_resubmits = repo["complete_job"].call_args.args
    assert worker_id == "w1" and model_name == "fake:test" and decision.esito == "pubblica" and max_resubmits == 3


def test_thresholds_come_from_configuration(app, repo):
    app.config.update(VERIFICA_SOGLIA_ALTA=0.99)
    fake = FakeVerifier([output("respingi", [("linguaggio", 3, "Insulto")], 0.95)])
    assert worker.run_once(fake, "w1") == "revisione"


def test_language_filter_is_applied_to_the_text(repo):
    repo["load_item"].return_value = ({**REPORT, "descrizione": "Il sindaco è uno str0nz0"}, [])
    assert worker.run_once(FakeVerifier([output("pubblica", confidenza=0.99)]), "w1") == "revisione"
    decision = repo["complete_job"].call_args.args[4]
    assert any(v.origine == "filtro_linguaggio" for v in decision.violazioni)


def test_model_disappearing_mid_job_releases_it_without_counting_an_attempt(repo):
    assert worker.run_once(FakeVerifier([ModelUnavailable("giù")]), "w1") == "modello_non_disponibile"
    repo["release_to_waiting"].assert_called_once_with(JOB, "w1")
    repo["fail_job"].assert_not_called()


def test_transient_error_is_retried_with_configured_backoff(app, repo):
    app.config.update(VERIFICA_MAX_TENTATIVI=4, VERIFICA_BACKOFF_BASE=7, VERIFICA_BACKOFF_MAX=100)
    assert worker.run_once(FakeVerifier([TransientModelError("timeout del modello")]), "w1") == "errore_riprova"
    args = repo["fail_job"].call_args.args
    assert args[2] == "timeout del modello" and args[4].esito == "revisione" and args[5:8] == (4, 7, 100)


def test_after_max_attempts_the_job_goes_to_moderators_and_email_is_sent(repo, monkeypatch):
    info = {"utente": 101, "titolo": "Buca", "tipo": "verifica_revisione", "messaggio": "In revisione"}
    repo["fail_job"].return_value = {"esito": "revisione", "tentativi": 5, "notifica": info}
    sent = Mock()
    monkeypatch.setattr(worker, "deliver_email", sent)
    assert worker.run_once(FakeVerifier([TransientModelError("risposta non conforme")]), "w1") == "errore_revisione"
    sent.assert_called_once_with(info)


def test_stale_completion_is_reported(repo):
    repo["complete_job"].return_value = None
    assert worker.run_once(FakeVerifier(), "w1") == "job_superato"


def test_email_only_for_users_who_opted_in(app, repo, monkeypatch):
    sent = Mock()
    monkeypatch.setattr(worker, "send_email", sent)
    info = {"utente": 101, "titolo": "Buca", "tipo": "verifica_respinta", "messaggio": "Respinto: insulti."}
    repo["author_email_target"].return_value = {"email": "a@example.com", "nome": "Ada", "notifiche_email": False, "stato": "attivo"}
    assert worker.deliver_email(info) is False
    repo["author_email_target"].return_value = {"email": "a@example.com", "nome": "Ada", "notifiche_email": True, "stato": "attivo"}
    assert worker.deliver_email(info) is True
    to, subject, body = sent.call_args.args
    assert to == "a@example.com" and "non è stato pubblicato" in subject and "Respinto: insulti." in body


def test_run_forever_survives_database_errors(app, monkeypatch):
    import mysql.connector
    outcomes = iter([mysql.connector.Error(errno=2013), "coda_vuota"])

    def fake_run_once(*args):
        value = next(outcomes)
        if isinstance(value, Exception):
            raise value
        return value
    monkeypatch.setattr(worker, "run_once", fake_run_once)
    monkeypatch.setattr(worker.time, "sleep", lambda seconds: None)
    rounds = iter([False, False, True])
    with app.app_context():
        worker.run_forever(0.01, stop=lambda: next(rounds))


def test_cli_command_is_registered(app):
    result = app.test_cli_runner().invoke(args=["verifica-worker", "--help"])
    assert result.exit_code == 0 and "--once" in result.output
