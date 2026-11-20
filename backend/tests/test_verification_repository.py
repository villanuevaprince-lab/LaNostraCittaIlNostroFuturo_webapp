"""SQL della coda e delle decisioni (cursore simulato): lock, guardie, backoff, contatori."""
from datetime import datetime

import pytest

from backend.repositories import verification as repo
from backend.services.verification_rules import Thresholds, decide, error_decision
from verification_fakes import output


JOB = {"id": 11, "report_id": 5, "version": 1, "attempts": 0, "waited": False}
REPORT = {"IdSegnalazione": 5, "IdAutore": 101, "Titolo": "Buca", "StatoVerifica": "in_valutazione",
          "VersioneInvio": 1, "Reinvii": 0}


def queries(cursor):
    return [(call.args[0], call.args[1] if len(call.args) > 1 else ()) for call in cursor.execute.call_args_list]


def test_claim_uses_skip_locked_in_arrival_order_and_reclaims_expired_leases(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchone.return_value = {"id": 11, "report_id": 5, "version": 1, "attempts": 0, "waited": 1}
    job = repo.claim_job("worker-a", 600)
    select, params = queries(cursor)[0]
    assert "FOR UPDATE SKIP LOCKED" in select and "ORDER BY IdJob LIMIT 1" in select
    assert "Stato='in_elaborazione' AND DataInizio < NOW() - INTERVAL %s SECOND" in select and params == (600,)
    update, params = queries(cursor)[1]
    assert "SET Stato='in_elaborazione', Worker=%s" in update and params == ("worker-a", 11)
    assert job["waited"] is True


def test_claim_with_empty_queue_updates_nothing(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchone.return_value = None
    assert repo.claim_job("w", 600) is None
    assert len(queries(cursor)) == 1


def test_waiting_moves_only_queued_jobs(fake_mysql):
    _, cursor = fake_mysql
    cursor.rowcount = 3
    assert repo.mark_waiting_for_model() == 3
    sql = [q for q, _ in queries(cursor)]
    assert "SET Stato='in_attesa_modello', AttesoModello=TRUE" in sql[0] and "WHERE Stato='in_coda'" in sql[0]
    assert "s.StatoVerifica='in_attesa_modello'" in sql[1]


def test_completion_by_a_worker_that_lost_the_job_is_discarded(fake_mysql):
    connection, cursor = fake_mysql
    cursor.fetchone.side_effect = [dict(REPORT), {"Stato": "in_elaborazione", "Worker": "worker-b", "Tentativi": 0}]
    decision = decide(output("pubblica"), Thresholds())
    assert repo.complete_job(JOB, "worker-a", "fake", output("pubblica"), decision, 3) is None
    assert not any("VERIFICA_ESITO" in q for q, _ in queries(cursor))
    connection.commit.assert_called_once()  # solo letture sotto lock, nessuna scrittura


@pytest.mark.parametrize("change", [{"VersioneInvio": 2}, {"StatoVerifica": "pubblicata"}])
def test_completion_after_resubmit_or_human_decision_is_discarded(fake_mysql, change):
    _, cursor = fake_mysql
    cursor.fetchone.side_effect = [{**REPORT, **change}, {"Stato": "in_elaborazione", "Worker": "worker-a", "Tentativi": 0}]
    decision = decide(output("pubblica"), Thresholds())
    assert repo.complete_job(JOB, "worker-a", "fake", output("pubblica"), decision, 3) is None


def test_completion_records_outcome_violations_publication_and_notification(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchone.side_effect = [dict(REPORT), {"Stato": "in_elaborazione", "Worker": "worker-a", "Tentativi": 0},
                                   {"n": 0}]
    out = output("pubblica", [("linguaggio", 1, "Refuso")], 0.9, note="tutto bene", categorie=[2])
    decision = decide(out, Thresholds())
    info = repo.complete_job({**JOB, "waited": True}, "worker-a", "ollama:qwen", out, decision, 3)
    calls = queries(cursor)
    sql = [q for q, _ in calls]
    assert sql[0].endswith("FOR UPDATE") and "FROM SEGNALAZIONE" in sql[0] and "FROM VERIFICA_JOB" in sql[1]  # ordine dei lock
    outcome = next(p for q, p in calls if "INSERT INTO VERIFICA_ESITO" in q)
    assert outcome[3:8] == ("ollama:qwen", "pubblica", "pubblica", 0.9, "Verifica superata: il contenuto è pubblico.")
    assert next(p for q, p in calls if "INSERT INTO VERIFICA_VIOLAZIONE" in q)[1:3] == ("linguaggio", 1)
    assert any("Origine, Confidenza" in q and "'ia'" in q for q in sql)  # categoria proposta dal modello
    update = next(p for q, p in calls if "UPDATE SEGNALAZIONE SET StatoVerifica" in q)
    assert update[0] == "pubblicata" and update[2] == "pubblicata"
    history = next(p for q, p in calls if "INSERT INTO DECISIONE_VERIFICA" in q)
    assert history[2:6] == ("modello", "pubblica", "in_valutazione", "pubblicata")
    notification = next(p for q, p in calls if "INSERT INTO NOTIFICA" in q)
    assert notification[3] == "verifica_pubblicata" and notification[4].startswith(repo.WAITED_PREFIX)
    assert any("SET Stato='completato'" in q for q in sql)
    assert info["tipo"] == "verifica_pubblicata"


def test_rejection_message_offers_resubmit_and_appeal(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchone.side_effect = [{**REPORT, "Reinvii": 1}, {"Stato": "in_elaborazione", "Worker": "w", "Tentativi": 0}]
    out = output("respingi", [("linguaggio", 3, "Insulti al vicino")], 0.95)
    info = repo.complete_job(JOB, "w", "m", out, decide(out, Thresholds()), 3)
    assert "Insulti al vicino" in info["messaggio"] and "tentativi rimasti: 2" in info["messaggio"]
    update = next(p for q, p in queries(cursor) if "UPDATE SEGNALAZIONE SET StatoVerifica" in q)
    assert update[0] == "respinta_automatica"


@pytest.mark.parametrize("previous_attempts,expected_delay", [(0, 30), (1, 60), (2, 120), (3, 240)])
def test_transient_errors_back_off_exponentially(fake_mysql, previous_attempts, expected_delay):
    _, cursor = fake_mysql
    cursor.fetchone.side_effect = [dict(REPORT), {"Stato": "in_elaborazione", "Worker": "w", "Tentativi": previous_attempts}]
    result = repo.fail_job(JOB, "w", "timeout", "m", error_decision("timeout"), 5, 30, 3600, 3)
    assert result == {"esito": "retry", "tentativi": previous_attempts + 1, "attesa": expected_delay}
    update = next(p for q, p in queries(cursor) if "ProssimoTentativo=NOW() + INTERVAL %s SECOND" in q)
    assert update == (previous_attempts + 1, "timeout", expected_delay, 11)


def test_backoff_is_capped(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchone.side_effect = [dict(REPORT), {"Stato": "in_elaborazione", "Worker": "w", "Tentativi": 8}]
    assert repo.fail_job(JOB, "w", "e", "m", error_decision("e"), 20, 30, 600, 3)["attesa"] == 600


def test_after_n_failures_the_job_goes_to_review_with_the_error_logged(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchone.side_effect = [dict(REPORT), {"Stato": "in_elaborazione", "Worker": "w", "Tentativi": 4}]
    result = repo.fail_job(JOB, "w", "HTTP 500 da Ollama", "m", error_decision("HTTP 500 da Ollama"), 5, 30, 3600, 3)
    assert result["esito"] == "revisione" and result["tentativi"] == 5
    calls = queries(cursor)
    assert next(p for q, p in calls if "SET Stato='da_revisionare'" in q) == (5, "HTTP 500 da Ollama", 11)
    outcome = next(p for q, p in calls if "INSERT INTO VERIFICA_ESITO" in q)
    assert outcome[5] == "revisione" and outcome[-1] == "HTTP 500 da Ollama"
    assert next(p for q, p in calls if "UPDATE SEGNALAZIONE SET StatoVerifica" in q)[0] == "da_revisionare"


def test_release_to_waiting_requires_ownership(fake_mysql):
    _, cursor = fake_mysql
    cursor.rowcount = 0
    assert repo.release_to_waiting(JOB, "w") is False
    sql, params = queries(cursor)[0]
    assert "AND Stato='in_elaborazione' AND Worker=%s" in sql and params == (11, "w")


# --- reinvio e ricorso ---------------------------------------------------------

OWN = {"IdSegnalazione": 5, "IdAutore": 101, "Titolo": "Buca", "StatoVerifica": "respinta_automatica",
       "VersioneInvio": 2, "Reinvii": 1, "Ricorsi": 0}


def test_resubmit_creates_a_new_version_and_job(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchone.return_value = dict(OWN)
    assert repo.resubmit(5, 101, "Nuovo titolo", "Nuova descrizione civica", 3) == {
        "stato_verifica": "in_valutazione", "reinvii": 2, "versione": 3}
    calls = queries(cursor)
    update = next(p for q, p in calls if "UPDATE SEGNALAZIONE SET Titolo" in q)
    assert update == ("Nuovo titolo", "Nuova descrizione civica", 3, 5)
    assert next(p for q, p in calls if "INSERT INTO VERIFICA_JOB" in q) == (5, 3)


@pytest.mark.parametrize("row,status", [
    ({**OWN, "Reinvii": 3}, 429), ({**OWN, "StatoVerifica": "da_revisionare"}, 409),
    ({**OWN, "IdAutore": 999}, 404), (None, 404),
])
def test_resubmit_limits(fake_mysql, row, status):
    _, cursor = fake_mysql
    cursor.fetchone.return_value = row
    with pytest.raises(repo.VerificationActionError) as error:
        repo.resubmit(5, 101, "Titolo", "Descrizione lunga", 3)
    assert error.value.status == status
    assert not any("INSERT INTO VERIFICA_JOB" in q for q, _ in queries(cursor))


def test_appeal_only_after_automatic_rejection(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchone.return_value = dict(OWN)
    assert repo.appeal(5, 101, "Il testo cita un graffito, non è un insulto")["stato_verifica"] == "in_ricorso"
    assert any("Ricorsi=Ricorsi+1" in q for q, _ in queries(cursor))
    cursor.fetchone.return_value = {**OWN, "StatoVerifica": "in_ricorso"}
    with pytest.raises(repo.VerificationActionError):
        repo.appeal(5, 101, "di nuovo, per favore")


# --- moderatore ---------------------------------------------------------------

MOD_ROW = {"IdSegnalazione": 5, "IdAutore": 101, "Titolo": "Buca", "StatoVerifica": "respinta_automatica",
           "VersioneInvio": 1, "Visibilita": "bozza", "Reinvii": 0}


def test_moderator_overturns_automatic_rejection(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchone.side_effect = [dict(MOD_ROW), {"Decisione": "respingi"}]
    result = repo.moderator_decide(5, 7, "approva", "Cita un graffito da rimuovere")
    assert result["stato_verifica"] == "pubblicata" and result["ribaltamento"] is True
    calls = queries(cursor)
    assert next(p for q, p in calls if "UPDATE SEGNALAZIONE SET StatoVerifica" in q) == (
        "pubblicata", "Cita un graffito da rimuovere", "pubblica", 5)
    history = next(p for q, p in calls if "INSERT INTO DECISIONE_VERIFICA" in q)
    assert history[2:8] == ("moderatore", "approva", "respinta_automatica", "pubblicata", 7, True)
    assert any("Chiuso dalla decisione di un moderatore" in q for q, _ in calls)
    notification = next(p for q, p in calls if "INSERT INTO NOTIFICA" in q)
    assert notification[3] == "verifica_moderatore" and "Cita un graffito" in notification[4]


def test_moderator_rejects_published_item_and_hides_it(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchone.side_effect = [{**MOD_ROW, "StatoVerifica": "pubblicata", "Visibilita": "pubblica"}, {"Decisione": "pubblica"}]
    result = repo.moderator_decide(5, 7, "respingi", "Contenuto pubblicitario")
    assert result == {"stato_verifica": "respinta_moderatore", "ribaltamento": True, "notifica": result["notifica"]}
    update = next(p for q, p in queries(cursor) if "UPDATE SEGNALAZIONE SET StatoVerifica" in q)
    assert update[2] == "bozza"


def test_appeal_decision_message_and_no_overturn_when_agreeing(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchone.side_effect = [{**MOD_ROW, "StatoVerifica": "in_ricorso"}, {"Decisione": "respingi"}]
    result = repo.moderator_decide(5, 7, "respingi", "Insulto confermato")
    assert result["ribaltamento"] is False and result["notifica"]["messaggio"].startswith("Esito del ricorso:")


@pytest.mark.parametrize("row,action", [
    ({**MOD_ROW, "StatoVerifica": "pubblicata"}, "approva"), ({**MOD_ROW, "Visibilita": "rimossa"}, "approva"),
])
def test_moderator_decision_conflicts(fake_mysql, row, action):
    _, cursor = fake_mysql
    cursor.fetchone.side_effect = [row, None]
    with pytest.raises(repo.VerificationActionError):
        repo.moderator_decide(5, 7, action, "motivo")


def test_detail_converts_dates_and_groups_violations(fake_mysql):
    _, cursor = fake_mysql
    now = datetime(2026, 11, 20, 10, 0)
    cursor.fetchone.return_value = {"id": 5, "titolo": "Buca", "data_creazione": now}
    cursor.fetchall.side_effect = [
        [], [{"id": 9, "versione": 1, "confidenza": 0.95, "data": now}],
        [{"esito": 9, "categoria": "scopo", "gravita": 2, "spiegazione": "x", "origine": "modello"}],
        [{"azione": "invio", "data": now}], [{"id": 1, "stato": "completato", "data_creazione": now}],
    ]
    detail = repo.item_detail(5)
    assert detail["data_creazione"] == "2026-11-20T10:00:00"
    assert detail["esiti"][0]["violazioni"][0]["categoria"] == "scopo"
    assert detail["storico"][0]["data"] == "2026-11-20T10:00:00"


def test_notification_without_message_keeps_the_old_query(fake_mysql):
    from backend.repositories.notifications import notify
    _, cursor = fake_mysql
    notify(cursor, 1, 2, 3, "nuovo_commento")
    assert "Messaggio" not in queries(cursor)[0][0]
    notify(cursor, 1, None, 3, "verifica_pubblicata", message="ok")
    assert queries(cursor)[1][1] == (1, 3, None, "verifica_pubblicata", "ok")
