"""Worker della coda di verifica: `flask --app backend.app verifica-worker`.

Può girare in più istanze: la coda in MySQL (SKIP LOCKED) evita le doppie elaborazioni.
Nessun job va perso: sono righe su MySQL e un job rimasto 'in_elaborazione' per un worker
morto torna disponibile dopo VERIFICA_LEASE_SECONDI.
"""

import logging
import os
import socket
import time
import uuid

import mysql.connector
from flask import current_app

from backend.repositories import verification as queue
from backend.repositories.reports import attachment_content
from backend.repositories.catalog import list_categories
from backend.services.mailer import MailError, absolute_url, send_email
from backend.services.verification_rules import Thresholds, decide, error_decision, scan_language
from backend.services.verifier import ModelUnavailable, TransientModelError, VerificationItem, get_verifier


log = logging.getLogger("verifica")
EMAIL_SUBJECTS = {
    "verifica_pubblicata": "Il tuo contenuto è stato pubblicato",
    "verifica_respinta": "Il tuo contenuto non è stato pubblicato",
    "verifica_revisione": "Il tuo contenuto è in revisione",
    "verifica_moderatore": "Un moderatore ha esaminato il tuo contenuto",
}


def new_worker_id():
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def thresholds():
    config = current_app.config
    return Thresholds(alta=config["VERIFICA_SOGLIA_ALTA"], bassa=config["VERIFICA_SOGLIA_BASSA"])


def deliver_email(info):
    """Avviso email facoltativo, solo se l'utente l'ha chiesto nel profilo. Non blocca mai."""
    if not info:
        return False
    target = queue.author_email_target(info["utente"])
    if not target or not target["notifiche_email"] or target["stato"] == "cancellato":
        return False
    body = (f"Ciao {target['nome']},\n\n{info['messaggio']}\n\n"
            f"Trovi i tuoi contenuti nell'area personale: {absolute_url('/dashboard')}\n")
    try:
        send_email(target["email"], f"{EMAIL_SUBJECTS.get(info['tipo'], 'Aggiornamento')} — La Nostra Città", body)
        return True
    except MailError:
        return False


def _build_item(report, attachments):
    images, videos = [], 0
    for attachment in attachments:
        if attachment["mime"].startswith("video/"):
            videos += 1
            continue
        try:
            content = attachment_content(attachment["id"])
        except ValueError:  # allegato corrotto: il modello lo segnalerà come mancante
            content = None
        if content:
            images.append(content[0])
    return VerificationItem(id=report["id"], tipo=report["tipo"], titolo=report["titolo"],
                            descrizione=report["descrizione"], indirizzo=report["indirizzo"],
                            categorie_catalogo=list_categories(), immagini=images, video_allegati=videos)


def run_once(verifier=None, worker_id=None):
    """Elabora al massimo un job. Restituisce cosa è successo, per il ciclo e per i test."""
    verifier = verifier or get_verifier()
    worker_id = worker_id or new_worker_id()
    config = current_app.config
    if not verifier.available():
        moved = queue.mark_waiting_for_model()
        if moved:
            log.warning("Modello non disponibile: %s job in attesa del modello", moved)
        return "modello_non_disponibile"
    job = queue.claim_job(worker_id, config["VERIFICA_LEASE_SECONDI"])
    if not job:
        return "coda_vuota"
    loaded = queue.load_item(job)
    if loaded is None:
        queue.cancel_stale_job(job, worker_id, "Job superato da un reinvio o da una decisione umana")
        return "job_superato"
    item = _build_item(*loaded)
    model_name = getattr(verifier, "name", "verifier")
    try:
        output = verifier.verify(item)
    except ModelUnavailable as error:
        queue.release_to_waiting(job, worker_id)
        log.warning("Job %s: modello sparito durante la verifica (%s)", job["id"], error)
        return "modello_non_disponibile"
    except TransientModelError as error:
        result = queue.fail_job(job, worker_id, str(error), model_name, error_decision(str(error)),
                                config["VERIFICA_MAX_TENTATIVI"], config["VERIFICA_BACKOFF_BASE"],
                                config["VERIFICA_BACKOFF_MAX"], config["VERIFICA_MAX_REINVII"])
        if result and result["esito"] == "revisione":
            log.error("Job %s: %s tentativi falliti, passa ai moderatori (%s)", job["id"], result["tentativi"], error)
            deliver_email(result["notifica"])
            return "errore_revisione"
        log.warning("Job %s: errore transitorio, nuovo tentativo (%s)", job["id"], error)
        return "errore_riprova"
    decision = decide(output, thresholds(), scan_language(item.titolo, item.descrizione))
    info = queue.complete_job(job, worker_id, model_name, output, decision, config["VERIFICA_MAX_REINVII"])
    if info is None:
        return "job_superato"
    deliver_email(info)
    log.info("Job %s: esito %s", job["id"], decision.esito)
    return decision.esito


def run_forever(poll_interval, stop=None, verifier=None):
    """Ciclo del worker; con la coda vuota o il modello assente aspetta poll_interval secondi."""
    worker_id = new_worker_id()
    log.info("Worker di verifica avviato (%s)", worker_id)
    while not (stop and stop()):
        try:
            outcome = run_once(verifier, worker_id)
        except mysql.connector.Error as error:  # DB momentaneamente irraggiungibile: riprova
            log.error("Database non disponibile per il worker (codice %s)", getattr(error, "errno", "?"))
            outcome = "errore_database"
        if outcome in {"coda_vuota", "modello_non_disponibile", "errore_database"}:
            time.sleep(poll_interval)
