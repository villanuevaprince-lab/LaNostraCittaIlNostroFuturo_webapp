"""Integrazione della coda di verifica con MySQL 8 reale (SKIP LOCKED, lock, persistenza).

Facoltativi: girano solo con VERIFICA_MYSQL_TEST=1, DB_HOST locale e un DB_NAME che finisce
con "_test" (mai su Aiven). Il database va creato prima con lo schema 001, i seed, le migrazioni
005-007 e la 010; vedi docs/configurazione.md, sezione «Test della coda su MySQL».
"""
import os
import threading
import time

import pytest

from backend.app import create_app
from backend.database import database_cursor
from backend.repositories import verification as repo
from backend.repositories.reports import create_report_record, list_map_items
from backend.services import verification_worker as worker
from backend.services.verifier import ModelUnavailable, TransientModelError
from verification_fakes import FakeVerifier, output


pytestmark = pytest.mark.skipif(
    os.getenv("VERIFICA_MYSQL_TEST") != "1" or os.getenv("DB_HOST") not in {"localhost", "127.0.0.1"}
    or not os.getenv("DB_NAME", "").endswith("_test"),
    reason="Test MySQL locale: imposta VERIFICA_MYSQL_TEST=1, DB_HOST locale e DB_NAME *_test",
)


@pytest.fixture(autouse=True)
def never_connect_to_aiven():
    """Sostituisce la fixture omonima di conftest: qui la connessione (locale) è voluta."""


@pytest.fixture()
def app(tmp_path):
    application = create_app({
        "TESTING": True, "SECRET_KEY": "only-for-local-tests-" + "x" * 32, "RATELIMIT_ENABLED": False,
        "SESSION_COOKIE_SECURE": False, "UPLOAD_FOLDER": str(tmp_path), "AI_ENABLED": True,
        "MAIL_BACKEND": "memory", "VERIFICA_BACKOFF_BASE": 0, "VERIFICA_MAX_TENTATIVI": 3,
        "VERIFICA_LEASE_SECONDI": 60,
    })
    with application.app_context():
        # Coda pulita: i job lasciati da altri test non devono interferire con l'ordine.
        with database_cursor(write=True) as cursor:
            cursor.execute("UPDATE VERIFICA_JOB SET Stato='completato' WHERE Stato <> 'completato'")
        yield application


def sql(query, params=(), one=False):
    with database_cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchone() if one else cursor.fetchall()


def new_user(label):
    with database_cursor(write=True) as cursor:
        cursor.execute("""INSERT INTO UTENTE (Nome, Cognome, Email, HashPassword)
            VALUES ('Test', %s, %s, 'x')""", (label, f"{label}-{time.time_ns()}@example.com"))
        return cursor.lastrowid


def new_report(author_id, title="Buca in via Roma"):
    upload = {"mime": "image/jpeg", "reference": f"ref-{time.time_ns()}.jpg", "original_name": "f.jpg", "size": 3,
              "sha256": "a" * 64, "accessible_description": "Foto", "content": b"abc"}
    data = {"tipo": "segnalazione", "titolo": title, "descrizione": "Buca profonda davanti alla scuola",
            "quartiere_id": 1, "categorie": [1], "indirizzo": "Via Roma", "latitude": "45.464200",
            "longitude": "9.190000", "verifica": True}
    return create_report_record(data, {"id": author_id}, upload)["id"]


def state(report_id):
    return sql("SELECT StatoVerifica, Visibilita, Reinvii FROM SEGNALAZIONE WHERE IdSegnalazione=%s", (report_id,), one=True)


def job_of(report_id):
    return sql("SELECT * FROM VERIFICA_JOB WHERE IdSegnalazione=%s ORDER BY IdJob DESC LIMIT 1", (report_id,), one=True)


def notifications(report_id):
    return sql("SELECT Tipo, Messaggio FROM NOTIFICA WHERE IdSegnalazione=%s ORDER BY IdNotifica", (report_id,))


def drain(verifier, worker_id="w"):
    outcomes = []
    while (outcome := worker.run_once(verifier, worker_id)) not in {"coda_vuota", "modello_non_disponibile"}:
        outcomes.append(outcome)
    return outcomes


def test_new_report_is_not_public_until_verified(app):
    report = new_report(new_user("pubblico"))
    assert state(report)["StatoVerifica"] == "in_valutazione" and state(report)["Visibilita"] == "bozza"
    assert report not in {item["id"] for item in list_map_items()["items"]}
    drain(FakeVerifier([output("pubblica", confidenza=0.95)]))
    assert state(report)["StatoVerifica"] == "pubblicata" and state(report)["Visibilita"] == "pubblica"
    assert report in {item["id"] for item in list_map_items()["items"]}
    assert notifications(report)[-1]["Tipo"] == "verifica_pubblicata"


def test_two_workers_never_process_the_same_job(app):
    author = new_user("concorrenza")
    reports = [new_report(author, f"Segnalazione {n}") for n in range(12)]
    seen, lock = [], threading.Lock()

    class SlowVerifier(FakeVerifier):
        def verify(self, item):
            with lock:
                seen.append(item.id)
            time.sleep(0.05)  # allarga la finestra in cui l'altro worker potrebbe prendere lo stesso job
            return output("pubblica", confidenza=0.95)

    def run(worker_id):
        with app.app_context():
            empty = 0
            while empty < 3:
                empty = empty + 1 if worker.run_once(SlowVerifier(), worker_id) == "coda_vuota" else 0

    threads = [threading.Thread(target=run, args=(f"worker-{n}",)) for n in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert sorted(seen) == sorted(reports)  # ogni contenuto verificato una e una sola volta
    rows = sql(f"""SELECT j.IdSegnalazione, j.Stato, j.Worker, COUNT(e.IdEsito) AS esiti FROM VERIFICA_JOB j
        LEFT JOIN VERIFICA_ESITO e ON e.IdJob=j.IdJob WHERE j.IdSegnalazione IN ({','.join(['%s'] * len(reports))})
        GROUP BY j.IdJob""", tuple(reports))
    assert all(row["Stato"] == "completato" and row["esiti"] == 1 for row in rows)
    assert {row["Worker"].split(":")[0] for row in rows} == {"worker-1", "worker-2"}  # il lavoro è stato diviso


def test_model_unavailable_then_back_processes_waiting_jobs_in_arrival_order(app):
    author = new_user("attesa")
    reports = [new_report(author, f"In attesa {n}") for n in range(3)]
    assert worker.run_once(FakeVerifier(available=False), "w") == "modello_non_disponibile"
    for report in reports:
        assert job_of(report)["Stato"] == "in_attesa_modello" and state(report)["StatoVerifica"] == "in_attesa_modello"
    fake = FakeVerifier([output("pubblica", confidenza=0.95)] * 3)
    drain(fake)
    assert [item.id for item in fake.calls] == reports
    for report in reports:
        assert state(report)["StatoVerifica"] == "pubblicata"
        assert notifications(report)[-1]["Messaggio"].startswith(repo.WAITED_PREFIX)


def test_model_lost_mid_job_returns_it_to_the_queue_without_spending_attempts(app):
    report = new_report(new_user("perso"))
    assert worker.run_once(FakeVerifier([ModelUnavailable("giù")]), "w") == "modello_non_disponibile"
    job = job_of(report)
    assert job["Stato"] == "in_attesa_modello" and job["Tentativi"] == 0 and job["Worker"] is None
    drain(FakeVerifier([output("pubblica", confidenza=0.95)]))
    assert state(report)["StatoVerifica"] == "pubblicata"


def test_orphaned_job_after_a_crash_is_recovered_and_the_late_result_discarded(app):
    report = new_report(new_user("crash"))
    dead_job = repo.claim_job("worker-morto", 60)
    assert dead_job["report_id"] == report and worker.run_once(FakeVerifier(), "w2") == "coda_vuota"  # lease attivo
    with database_cursor(write=True) as cursor:
        cursor.execute("UPDATE VERIFICA_JOB SET DataInizio = NOW() - INTERVAL 2 HOUR WHERE IdJob=%s", (dead_job["id"],))
    assert worker.run_once(FakeVerifier([output("pubblica", confidenza=0.95)]), "w2") == "pubblica"
    late = repo.complete_job(dead_job, "worker-morto", "m", output("respingi", [("scopo", 3, "x")], 0.99),
                             worker.decide(output("respingi", [("scopo", 3, "x")], 0.99), worker.thresholds()), 3)
    assert late is None and state(report)["StatoVerifica"] == "pubblicata"
    assert sql("SELECT COUNT(*) AS n FROM VERIFICA_ESITO WHERE IdSegnalazione=%s", (report,), one=True)["n"] == 1


def test_transient_errors_are_retried_then_sent_to_moderators(app):
    report = new_report(new_user("retry"))
    fake = FakeVerifier([TransientModelError("timeout del modello")] * 3)
    assert drain(fake) == ["errore_riprova", "errore_riprova", "errore_revisione"]
    job = job_of(report)
    assert job["Stato"] == "da_revisionare" and job["Tentativi"] == 3 and job["UltimoErrore"] == "timeout del modello"
    assert state(report)["StatoVerifica"] == "da_revisionare" and state(report)["Visibilita"] == "bozza"
    outcome = sql("SELECT Decisione, Errore FROM VERIFICA_ESITO WHERE IdSegnalazione=%s", (report,), one=True)
    assert outcome == {"Decisione": "revisione", "Errore": "timeout del modello"}
    assert notifications(report)[-1]["Tipo"] == "verifica_revisione"


def test_backoff_postpones_the_retry(app):
    app.config["VERIFICA_BACKOFF_BASE"] = 3600
    report = new_report(new_user("backoff"))
    assert worker.run_once(FakeVerifier([TransientModelError("HTTP 500")]), "w") == "errore_riprova"
    assert worker.run_once(FakeVerifier(), "w") == "coda_vuota"  # non prima del ProssimoTentativo
    delay = sql("SELECT TIMESTAMPDIFF(SECOND, NOW(), ProssimoTentativo) AS s FROM VERIFICA_JOB WHERE IdSegnalazione=%s",
                (report,), one=True)["s"]
    assert 3500 <= delay <= 3600


def test_rejection_resubmit_limit_appeal_and_moderator_override(app):
    author, moderator = new_user("autore"), new_user("moderatore")
    report = new_report(author)
    rejection = output("respingi", [("linguaggio", 3, "Insulto diretto al vicino")], 0.95)
    drain(FakeVerifier([rejection]))
    assert state(report)["StatoVerifica"] == "respinta_automatica" and state(report)["Visibilita"] == "bozza"
    assert "tentativi rimasti: 3" in notifications(report)[-1]["Messaggio"]
    for attempt in range(1, 4):
        repo.resubmit(report, author, f"Titolo corretto {attempt}", "Descrizione corretta e civile", 3)
        assert state(report)["StatoVerifica"] == "in_valutazione"
        drain(FakeVerifier([rejection]))
    assert state(report)["Reinvii"] == 3
    with pytest.raises(repo.VerificationActionError) as error:
        repo.resubmit(report, author, "Ancora", "Descrizione corretta e civile", 3)
    assert error.value.status == 429
    repo.appeal(report, author, "Sto citando una scritta sul muro della scuola")
    assert state(report)["StatoVerifica"] == "in_ricorso"
    result = repo.moderator_decide(report, moderator, "approva", "La scritta è citata per segnalarla")
    assert result["ribaltamento"] is True and state(report)["StatoVerifica"] == "pubblicata"
    assert state(report)["Visibilita"] == "pubblica"
    history = sql("""SELECT Origine, Azione, Ribaltamento, IdUtente FROM DECISIONE_VERIFICA
        WHERE IdSegnalazione=%s ORDER BY IdDecisione""", (report,))
    assert [h["Azione"] for h in history] == ["invio", "respingi", "reinvio", "respingi", "reinvio", "respingi",
                                              "reinvio", "respingi", "ricorso", "approva"]
    assert history[-1]["Ribaltamento"] == 1 and history[-1]["IdUtente"] == moderator
    last = notifications(report)[-1]
    assert last["Tipo"] == "verifica_moderatore" and last["Messaggio"].startswith("Esito del ricorso:")
    assert sql("SELECT COUNT(*) AS n FROM VERIFICA_JOB WHERE IdSegnalazione=%s", (report,), one=True)["n"] == 4


def test_moderator_decision_while_job_is_running_wins(app):
    report, moderator = new_report(new_user("corsa")), new_user("mod")
    job = repo.claim_job("lento", 60)
    repo.moderator_decide(report, moderator, "respingi", "Pubblicità di un negozio")
    late = repo.complete_job(job, "lento", "m", output("pubblica", confidenza=0.99),
                             worker.decide(output("pubblica", confidenza=0.99), worker.thresholds()), 3)
    assert late is None and state(report)["StatoVerifica"] == "respinta_moderatore"
    assert job_of(report)["Stato"] == "completato"


def test_moderator_dashboard_queries(app):
    report = new_report(new_user("vista"))
    drain(FakeVerifier([output("revisione", [("scopo", 2, "Forse pubblicità")], 0.6, note="Verificare il link")]))
    page = repo.list_items("priorita", None, 50)
    item = next(i for i in page["items"] if i["id"] == report)
    assert item["decisione_modello"] == "revisione" and item["gravita_massima"] == 2 and item["confidenza"] == 0.6
    detail = repo.item_detail(report)
    assert detail["esiti"][0]["note_moderatore"] == "Verificare il link"
    assert detail["esiti"][0]["violazioni"][0]["categoria"] == "scopo"
    assert [h["azione"] for h in detail["storico"]] == ["invio", "revisione"]
    assert repo.counts_by_state()["da_revisionare"] >= 1
