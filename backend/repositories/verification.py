"""Coda di verifica AI su MySQL, esiti, storico delle decisioni, reinvii e ricorsi.

Concorrenza:
- i worker prendono i job con SELECT ... FOR UPDATE SKIP LOCKED: due istanze non leggono
  mai lo stesso job nello stesso momento;
- un job 'in_elaborazione' rimasto orfano (worker morto) torna disponibile dopo il lease;
- chi completa un job ricontrolla, sotto lock, di esserne ancora il proprietario e che il
  contenuto non sia stato reinviato o deciso da un moderatore: un risultato tardivo viene scartato;
- VERIFICA_ESITO ha UNIQUE(IdJob): al massimo un esito per job anche in caso di errori.
Ordine dei lock per evitare deadlock: prima SEGNALAZIONE, poi VERIFICA_JOB.
"""

from backend.database import database_cursor
from backend.repositories.notifications import notify


PENDING_STATES = ("in_valutazione", "in_attesa_modello")
OUTCOME_STATE = {"pubblica": "pubblicata", "respingi": "respinta_automatica", "revisione": "da_revisionare"}
NOTIFICATION_KIND = {"pubblicata": "verifica_pubblicata", "respinta_automatica": "verifica_respinta",
                     "da_revisionare": "verifica_revisione"}
VERIFICATION_STATES = ("in_valutazione", "in_attesa_modello", "pubblicata", "respinta_automatica",
                       "respinta_moderatore", "da_revisionare", "in_ricorso")
PRIORITY_STATES = ("da_revisionare", "in_ricorso")
WAITED_PREFIX = "Il servizio di verifica è tornato disponibile e il tuo contenuto è stato elaborato. "


def enqueue(cursor, report_id, version):
    cursor.execute("INSERT INTO VERIFICA_JOB (IdSegnalazione, VersioneInvio) VALUES (%s, %s)", (report_id, version))
    return cursor.lastrowid


def record_decision(cursor, report_id, version, origin, action, before, after,
                    user_id=None, overturn=False, reason=None):
    cursor.execute("""INSERT INTO DECISIONE_VERIFICA
        (IdSegnalazione, VersioneInvio, Origine, Azione, StatoPrecedente, StatoSuccessivo, IdUtente,
         Ribaltamento, Motivazione) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (report_id, version, origin, action, before, after, user_id, bool(overturn),
         (reason or None) and reason[:1000]))


def _notify(cursor, report, kind, message, actor=None):
    notify(cursor, report["IdAutore"], actor, report["IdSegnalazione"], kind, message=message)
    return {"utente": report["IdAutore"], "titolo": report["Titolo"], "tipo": kind, "messaggio": message}


# --- worker ------------------------------------------------------------------

def mark_waiting_for_model():
    """Il modello non risponde: i job in coda passano in attesa, nessuno viene perso."""
    with database_cursor(write=True) as cursor:
        cursor.execute("""UPDATE VERIFICA_JOB SET Stato='in_attesa_modello', AttesoModello=TRUE
            WHERE Stato='in_coda'""")
        moved = cursor.rowcount
    if moved:
        with database_cursor(write=True) as cursor:
            cursor.execute("""UPDATE SEGNALAZIONE s JOIN VERIFICA_JOB j
                ON j.IdSegnalazione=s.IdSegnalazione AND j.VersioneInvio=s.VersioneInvio
                SET s.StatoVerifica='in_attesa_modello'
                WHERE j.Stato='in_attesa_modello' AND s.StatoVerifica='in_valutazione'""")
    return moved


def claim_job(worker_id, lease_seconds):
    """Prende il job più vecchio disponibile senza attendere quelli bloccati da altri worker."""
    with database_cursor(write=True) as cursor:
        cursor.execute("""SELECT IdJob AS id, IdSegnalazione AS report_id, VersioneInvio AS version,
                Tentativi AS attempts, AttesoModello AS waited
            FROM VERIFICA_JOB
            WHERE (Stato IN ('in_coda', 'in_attesa_modello') AND ProssimoTentativo <= NOW())
               OR (Stato='in_elaborazione' AND DataInizio < NOW() - INTERVAL %s SECOND)
            ORDER BY IdJob LIMIT 1 FOR UPDATE SKIP LOCKED""", (int(lease_seconds),))
        job = cursor.fetchone()
        if not job:
            return None
        cursor.execute("""UPDATE VERIFICA_JOB SET Stato='in_elaborazione', Worker=%s, DataInizio=NOW()
            WHERE IdJob=%s""", (worker_id[:80], job["id"]))
    job["waited"] = bool(job["waited"])
    with database_cursor(write=True) as cursor:
        cursor.execute("""UPDATE SEGNALAZIONE SET StatoVerifica='in_valutazione'
            WHERE IdSegnalazione=%s AND VersioneInvio=%s AND StatoVerifica='in_attesa_modello'""",
            (job["report_id"], job["version"]))
    return job


def load_item(job):
    """Dati da verificare per la versione del job; None se il job non è più attuale."""
    with database_cursor() as cursor:
        cursor.execute("""SELECT IdSegnalazione AS id, Tipo AS tipo, Titolo AS titolo, Descrizione AS descrizione,
                COALESCE(Indirizzo, '') AS indirizzo, StatoVerifica AS stato, VersioneInvio AS version
            FROM SEGNALAZIONE WHERE IdSegnalazione=%s""", (job["report_id"],))
        report = cursor.fetchone()
        if not report or report["version"] != job["version"] or report["stato"] not in PENDING_STATES:
            return None
        cursor.execute("""SELECT IdAllegato AS id, TipoMedia AS mime FROM ALLEGATO
            WHERE IdSegnalazione=%s AND Ruolo='prima' ORDER BY IdAllegato""", (job["report_id"],))
        attachments = cursor.fetchall()
    return report, attachments


def cancel_stale_job(job, worker_id, reason):
    with database_cursor(write=True) as cursor:
        cursor.execute("""UPDATE VERIFICA_JOB SET Stato='completato', DataFine=NOW(), UltimoErrore=%s
            WHERE IdJob=%s AND Stato='in_elaborazione' AND Worker=%s""", (reason[:1000], job["id"], worker_id[:80]))


def release_to_waiting(job, worker_id):
    """Il modello è sparito durante l'elaborazione: si torna in attesa senza contare un tentativo."""
    with database_cursor(write=True) as cursor:
        cursor.execute("""UPDATE VERIFICA_JOB SET Stato='in_attesa_modello', AttesoModello=TRUE,
                Worker=NULL, DataInizio=NULL
            WHERE IdJob=%s AND Stato='in_elaborazione' AND Worker=%s""", (job["id"], worker_id[:80]))
        released = cursor.rowcount == 1
    if released:
        with database_cursor(write=True) as cursor:
            cursor.execute("""UPDATE SEGNALAZIONE SET StatoVerifica='in_attesa_modello'
                WHERE IdSegnalazione=%s AND VersioneInvio=%s AND StatoVerifica='in_valutazione'""",
                (job["report_id"], job["version"]))
    return released


def _lock_for_completion(cursor, job, worker_id):
    cursor.execute("""SELECT IdSegnalazione, IdAutore, Titolo, StatoVerifica, VersioneInvio, Reinvii
        FROM SEGNALAZIONE WHERE IdSegnalazione=%s FOR UPDATE""", (job["report_id"],))
    report = cursor.fetchone()
    cursor.execute("SELECT Stato, Worker, Tentativi FROM VERIFICA_JOB WHERE IdJob=%s FOR UPDATE", (job["id"],))
    current = cursor.fetchone()
    if (not report or not current or current["Stato"] != "in_elaborazione" or current["Worker"] != worker_id[:80]
            or report["VersioneInvio"] != job["version"] or report["StatoVerifica"] not in PENDING_STATES):
        return None, None
    return report, current


def _insert_outcome(cursor, job, model_name, decision, output=None, error=None):
    cursor.execute("""INSERT INTO VERIFICA_ESITO
        (IdJob, IdSegnalazione, VersioneInvio, Modello, EsitoSuggerito, Decisione, Confidenza,
         Motivazione, NoteModeratore, Errore) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (job["id"], job["report_id"], job["version"], model_name[:120],
         output.esito_suggerito if output else None, decision.esito,
         output.confidenza if output else None, decision.motivazione[:1000],
         output.note_moderatore if output else None, (error or None) and error[:1000]))
    outcome_id = cursor.lastrowid
    for violation in decision.violazioni:
        cursor.execute("""INSERT INTO VERIFICA_VIOLAZIONE (IdEsito, Categoria, Gravita, Spiegazione, Origine)
            VALUES (%s, %s, %s, %s, %s)""",
            (outcome_id, violation.categoria, violation.gravita, violation.spiegazione[:500], violation.origine))
    return outcome_id


def _user_message(state, decision, report, max_resubmits, waited):
    if state == "pubblicata":
        message = f"«{report['Titolo']}» ha superato la verifica ed è ora pubblico."
    elif state == "respinta_automatica":
        left = max(0, max_resubmits - report["Reinvii"])
        options = (f"Puoi modificarlo e reinviarlo (tentativi rimasti: {left}) oppure chiedere la revisione "
                   "di un moderatore." if left else "Puoi chiedere la revisione di un moderatore.")
        message = f"{decision.motivazione} {options}"
    else:
        message = decision.motivazione
    return (WAITED_PREFIX + message if waited else message)[:1000]


def _apply_model_outcome(cursor, job, report, decision, max_resubmits):
    state = OUTCOME_STATE[decision.esito]
    message = _user_message(state, decision, report, max_resubmits, job.get("waited"))
    cursor.execute("""UPDATE SEGNALAZIONE SET StatoVerifica=%s, MotivazioneVerifica=%s,
            Visibilita=IF(%s='pubblicata', 'pubblica', Visibilita)
        WHERE IdSegnalazione=%s""", (state, decision.motivazione[:1000], state, job["report_id"]))
    record_decision(cursor, job["report_id"], job["version"], "modello", decision.esito,
                    report["StatoVerifica"], state, reason=decision.motivazione)
    cursor.execute("""INSERT INTO EVENTO_LOG (IdEsecutore, TipoAzione, Esito, Dettagli, IdSegnalazione)
        VALUES (NULL, 'verifica_ai', 'successo', %s, %s)""", (f"Esito: {state}", job["report_id"]))
    return _notify(cursor, report, NOTIFICATION_KIND[state], message)


def complete_job(job, worker_id, model_name, output, decision, max_resubmits):
    """Registra l'esito del modello. None se il job non appartiene più a questo worker."""
    with database_cursor(write=True) as cursor:
        report, _ = _lock_for_completion(cursor, job, worker_id)
        if report is None:
            return None
        _insert_outcome(cursor, job, model_name, decision, output)
        if output.categorie_suggerite:
            cursor.execute("SELECT COUNT(*) AS n FROM SEGNALAZIONE_CATEGORIA WHERE IdSegnalazione=%s",
                           (job["report_id"],))
            if not cursor.fetchone()["n"]:
                for category_id in output.categorie_suggerite:
                    cursor.execute("""INSERT IGNORE INTO SEGNALAZIONE_CATEGORIA (IdSegnalazione, IdCategoria, Origine, Confidenza)
                        SELECT %s, IdCategoria, 'ia', %s FROM CATEGORIA WHERE IdCategoria=%s AND Attiva=TRUE""",
                        (job["report_id"], output.confidenza, category_id))
        info = _apply_model_outcome(cursor, job, report, decision, max_resubmits)
        cursor.execute("UPDATE VERIFICA_JOB SET Stato='completato', DataFine=NOW() WHERE IdJob=%s", (job["id"],))
    return info


def fail_job(job, worker_id, error, model_name, decision_on_give_up, max_attempts, backoff_base, backoff_max,
             max_resubmits):
    """Errore transitorio: retry con backoff esponenziale; dopo max_attempts decide un moderatore."""
    with database_cursor(write=True) as cursor:
        report, current = _lock_for_completion(cursor, job, worker_id)
        if report is None:
            return None
        attempts = current["Tentativi"] + 1
        if attempts < max_attempts:
            delay = min(int(backoff_max), int(backoff_base) * 2 ** (attempts - 1))
            cursor.execute("""UPDATE VERIFICA_JOB SET Stato='in_coda', Tentativi=%s, UltimoErrore=%s,
                    ProssimoTentativo=NOW() + INTERVAL %s SECOND, Worker=NULL, DataInizio=NULL
                WHERE IdJob=%s""", (attempts, error[:1000], delay, job["id"]))
            return {"esito": "retry", "tentativi": attempts, "attesa": delay}
        cursor.execute("""UPDATE VERIFICA_JOB SET Stato='da_revisionare', Tentativi=%s, UltimoErrore=%s,
                DataFine=NOW() WHERE IdJob=%s""", (attempts, error[:1000], job["id"]))
        _insert_outcome(cursor, job, model_name, decision_on_give_up, error=error)
        info = _apply_model_outcome(cursor, job, report, decision_on_give_up, max_resubmits)
    return {"esito": "revisione", "tentativi": attempts, "notifica": info}


# --- azioni dell'utente ------------------------------------------------------

class VerificationActionError(ValueError):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def _lock_own_report(cursor, report_id, author_id):
    cursor.execute("""SELECT IdSegnalazione, IdAutore, Titolo, StatoVerifica, VersioneInvio, Reinvii, Ricorsi
        FROM SEGNALAZIONE WHERE IdSegnalazione=%s FOR UPDATE""", (report_id,))
    report = cursor.fetchone()
    if not report or report["IdAutore"] != author_id:
        raise VerificationActionError("Contenuto non trovato.", 404)
    return report


def resubmit(report_id, author_id, title, description, max_resubmits):
    """Contenuto respinto automaticamente: nuovo testo, nuova versione, nuovo job."""
    with database_cursor(write=True) as cursor:
        report = _lock_own_report(cursor, report_id, author_id)
        if report["StatoVerifica"] != "respinta_automatica":
            raise VerificationActionError("Puoi reinviare solo un contenuto respinto automaticamente.")
        if report["Reinvii"] >= max_resubmits:
            raise VerificationActionError(f"Hai già usato tutti i {max_resubmits} reinvii disponibili. "
                                          "Puoi ancora chiedere la revisione di un moderatore.", 429)
        version = report["VersioneInvio"] + 1
        cursor.execute("""UPDATE SEGNALAZIONE SET Titolo=%s, Descrizione=%s, VersioneInvio=%s, Reinvii=Reinvii+1,
                StatoVerifica='in_valutazione', MotivazioneVerifica=NULL WHERE IdSegnalazione=%s""",
            (title, description, version, report_id))
        enqueue(cursor, report_id, version)
        record_decision(cursor, report_id, version, "utente", "reinvio", report["StatoVerifica"], "in_valutazione",
                        user_id=author_id, reason="Contenuto modificato e reinviato alla verifica")
        cursor.execute("""INSERT INTO EVENTO_LOG (IdEsecutore, TipoAzione, Esito, Dettagli, IdSegnalazione)
            VALUES (%s, 'reinvio_verifica', 'successo', %s, %s)""",
            (author_id, f"Reinvio {report['Reinvii'] + 1} di {max_resubmits}", report_id))
    return {"stato_verifica": "in_valutazione", "reinvii": report["Reinvii"] + 1, "versione": version}


def appeal(report_id, author_id, reason):
    """Richiesta di revisione umana di un rifiuto automatico: una per ogni rifiuto."""
    with database_cursor(write=True) as cursor:
        report = _lock_own_report(cursor, report_id, author_id)
        if report["StatoVerifica"] != "respinta_automatica":
            raise VerificationActionError("Il ricorso è possibile solo dopo un rifiuto automatico.")
        cursor.execute("""UPDATE SEGNALAZIONE SET StatoVerifica='in_ricorso', Ricorsi=Ricorsi+1
            WHERE IdSegnalazione=%s""", (report_id,))
        record_decision(cursor, report_id, report["VersioneInvio"], "utente", "ricorso",
                        report["StatoVerifica"], "in_ricorso", user_id=author_id, reason=reason)
        cursor.execute("""INSERT INTO EVENTO_LOG (IdEsecutore, TipoAzione, Esito, Dettagli, IdSegnalazione)
            VALUES (%s, 'ricorso_verifica', 'successo', 'Richiesta revisione umana', %s)""", (author_id, report_id))
    return {"stato_verifica": "in_ricorso"}


# --- decisioni del moderatore ------------------------------------------------

def moderator_decide(report_id, moderator_id, action, reason):
    """Approva o respinge; se contraddice il modello è un ribaltamento. Sempre con motivo."""
    if action not in ("approva", "respingi"):
        raise VerificationActionError("Azione non valida.", 400)
    with database_cursor(write=True) as cursor:
        cursor.execute("""SELECT IdSegnalazione, IdAutore, Titolo, StatoVerifica, VersioneInvio, Visibilita, Reinvii
            FROM SEGNALAZIONE WHERE IdSegnalazione=%s FOR UPDATE""", (report_id,))
        report = cursor.fetchone()
        if not report:
            raise VerificationActionError("Contenuto non trovato.", 404)
        target = "pubblicata" if action == "approva" else "respinta_moderatore"
        if report["StatoVerifica"] == target:
            raise VerificationActionError("Il contenuto è già in questo stato.")
        if report["Visibilita"] == "rimossa":
            raise VerificationActionError("Il contenuto è stato rimosso o ritirato: usa la coda di moderazione.")
        cursor.execute("""SELECT Decisione FROM VERIFICA_ESITO WHERE IdSegnalazione=%s AND VersioneInvio=%s
            ORDER BY IdEsito DESC LIMIT 1""", (report_id, report["VersioneInvio"]))
        model = cursor.fetchone()
        model_decision = model["Decisione"] if model else None
        overturn = (model_decision == "pubblica" and action == "respingi") or \
                   (model_decision == "respingi" and action == "approva")
        # Una decisione umana chiude l'eventuale verifica ancora in corso per questa versione.
        cursor.execute("""UPDATE VERIFICA_JOB SET Stato='completato', DataFine=NOW(),
                UltimoErrore='Chiuso dalla decisione di un moderatore'
            WHERE IdSegnalazione=%s AND VersioneInvio=%s
              AND Stato IN ('in_coda', 'in_attesa_modello', 'in_elaborazione')""",
            (report_id, report["VersioneInvio"]))
        visibility = "pubblica" if action == "approva" else ("bozza" if report["Visibilita"] == "pubblica"
                                                              else report["Visibilita"])
        cursor.execute("""UPDATE SEGNALAZIONE SET StatoVerifica=%s, MotivazioneVerifica=%s, Visibilita=%s
            WHERE IdSegnalazione=%s""", (target, reason[:1000], visibility, report_id))
        record_decision(cursor, report_id, report["VersioneInvio"], "moderatore", action, report["StatoVerifica"],
                        target, user_id=moderator_id, overturn=overturn, reason=reason)
        cursor.execute("""INSERT INTO EVENTO_LOG (IdEsecutore, TipoAzione, Esito, Dettagli, IdSegnalazione)
            VALUES (%s, 'decisione_verifica', 'successo', %s, %s)""",
            (moderator_id, f"{report['StatoVerifica']} → {target}" + (" (ribaltamento)" if overturn else ""), report_id))
        appeal_note = "Esito del ricorso: " if report["StatoVerifica"] == "in_ricorso" else ""
        verb = "è stato approvato ed è ora pubblico" if action == "approva" else "è stato respinto"
        message = f"{appeal_note}«{report['Titolo']}» {verb} da un moderatore. Motivo: {reason}"
        info = _notify(cursor, report, "verifica_moderatore", message[:1000], actor=moderator_id)
    return {"stato_verifica": target, "ribaltamento": overturn, "notifica": info}


# --- letture per moderatori e autori ------------------------------------------

def counts_by_state():
    with database_cursor() as cursor:
        cursor.execute("SELECT StatoVerifica AS stato, COUNT(*) AS n FROM SEGNALAZIONE GROUP BY StatoVerifica")
        rows = cursor.fetchall()
    counts = {state: 0 for state in VERIFICATION_STATES}
    counts.update({row["stato"]: row["n"] for row in rows})
    return counts


def list_items(view="priorita", cursor_id=None, limit=25):
    if view == "priorita":
        states = PRIORITY_STATES
    elif view == "tutte":
        states = VERIFICATION_STATES
    elif view in VERIFICATION_STATES:
        states = (view,)
    else:
        raise ValueError("Vista non valida.")
    # Le code da lavorare si leggono dal più vecchio; gli archivi dal più recente.
    oldest_first = view in ("priorita", "da_revisionare", "in_ricorso", "in_valutazione", "in_attesa_modello")
    marks = ",".join(["%s"] * len(states))
    comparison, order = (">", "ASC") if oldest_first else ("<", "DESC")
    with database_cursor() as cursor:
        cursor.execute(f"""SELECT s.IdSegnalazione AS id, s.Tipo AS tipo, s.Titolo AS titolo,
                s.StatoVerifica AS stato_verifica, s.Visibilita AS visibilita, s.DataCreazione AS data_creazione,
                s.VersioneInvio AS versione, s.Reinvii AS reinvii, s.Ricorsi AS ricorsi,
                CONCAT(u.Nome, ' ', u.Cognome) AS autore,
                e.Decisione AS decisione_modello, e.Confidenza AS confidenza, e.Motivazione AS motivazione_modello,
                (SELECT MAX(v.Gravita) FROM VERIFICA_VIOLAZIONE v WHERE v.IdEsito=e.IdEsito) AS gravita_massima,
                j.Stato AS stato_job, j.Tentativi AS tentativi
            FROM SEGNALAZIONE s JOIN UTENTE u ON u.IdUtente=s.IdAutore
            LEFT JOIN VERIFICA_ESITO e ON e.IdEsito=(SELECT MAX(e2.IdEsito) FROM VERIFICA_ESITO e2
                                                    WHERE e2.IdSegnalazione=s.IdSegnalazione)
            LEFT JOIN VERIFICA_JOB j ON j.IdSegnalazione=s.IdSegnalazione AND j.VersioneInvio=s.VersioneInvio
            WHERE s.StatoVerifica IN ({marks}) AND (%s IS NULL OR s.IdSegnalazione {comparison} %s)
            ORDER BY s.IdSegnalazione {order} LIMIT %s""", (*states, cursor_id, cursor_id, limit + 1))
        rows = cursor.fetchall()
    page = rows[:limit]
    for row in page:
        row["data_creazione"] = row["data_creazione"].isoformat(timespec="seconds")
        row["confidenza"] = float(row["confidenza"]) if row["confidenza"] is not None else None
    return {"items": page, "next_cursor": page[-1]["id"] if len(rows) > limit and page else None}


def item_detail(report_id):
    with database_cursor() as cursor:
        cursor.execute("""SELECT s.IdSegnalazione AS id, s.Tipo AS tipo, s.Titolo AS titolo, s.Descrizione AS descrizione,
                s.Indirizzo AS indirizzo, s.StatoVerifica AS stato_verifica, s.Visibilita AS visibilita,
                s.MotivazioneVerifica AS motivazione, s.VersioneInvio AS versione, s.Reinvii AS reinvii,
                s.Ricorsi AS ricorsi, s.DataCreazione AS data_creazione, CONCAT(u.Nome, ' ', u.Cognome) AS autore
            FROM SEGNALAZIONE s JOIN UTENTE u ON u.IdUtente=s.IdAutore WHERE s.IdSegnalazione=%s""", (report_id,))
        item = cursor.fetchone()
        if not item:
            return None
        cursor.execute("""SELECT IdAllegato AS id, TipoMedia AS mime FROM ALLEGATO
            WHERE IdSegnalazione=%s ORDER BY IdAllegato""", (report_id,))
        item["allegati"] = cursor.fetchall()
        cursor.execute("""SELECT IdEsito AS id, VersioneInvio AS versione, Modello AS modello,
                EsitoSuggerito AS esito_suggerito, Decisione AS decisione, Confidenza AS confidenza,
                Motivazione AS motivazione, NoteModeratore AS note_moderatore, Errore AS errore, DataEsito AS data
            FROM VERIFICA_ESITO WHERE IdSegnalazione=%s ORDER BY IdEsito DESC""", (report_id,))
        outcomes = cursor.fetchall()
        violations = {}
        if outcomes:
            marks = ",".join(["%s"] * len(outcomes))
            cursor.execute(f"""SELECT IdEsito AS esito, Categoria AS categoria, Gravita AS gravita,
                    Spiegazione AS spiegazione, Origine AS origine
                FROM VERIFICA_VIOLAZIONE WHERE IdEsito IN ({marks}) ORDER BY Gravita DESC, IdViolazione""",
                tuple(o["id"] for o in outcomes))
            for row in cursor.fetchall():
                violations.setdefault(row.pop("esito"), []).append(row)
        cursor.execute("""SELECT d.Origine AS origine, d.Azione AS azione, d.StatoPrecedente AS stato_precedente,
                d.StatoSuccessivo AS stato_successivo, d.Ribaltamento AS ribaltamento, d.Motivazione AS motivazione,
                d.VersioneInvio AS versione, d.DataDecisione AS data,
                CASE WHEN d.IdUtente IS NULL THEN NULL ELSE CONCAT(u.Nome, ' ', u.Cognome) END AS utente
            FROM DECISIONE_VERIFICA d LEFT JOIN UTENTE u ON u.IdUtente=d.IdUtente
            WHERE d.IdSegnalazione=%s ORDER BY d.IdDecisione""", (report_id,))
        history = cursor.fetchall()
        cursor.execute("""SELECT IdJob AS id, VersioneInvio AS versione, Stato AS stato, Tentativi AS tentativi,
                ProssimoTentativo AS prossimo_tentativo, AttesoModello AS atteso_modello, UltimoErrore AS ultimo_errore,
                DataCreazione AS data_creazione, DataFine AS data_fine
            FROM VERIFICA_JOB WHERE IdSegnalazione=%s ORDER BY IdJob DESC""", (report_id,))
        jobs = cursor.fetchall()
    for outcome in outcomes:
        outcome["violazioni"] = violations.get(outcome["id"], [])
        outcome["confidenza"] = float(outcome["confidenza"]) if outcome["confidenza"] is not None else None
    item["esiti"], item["storico"], item["job"] = outcomes, history, jobs
    return _isoformat(item)


def _isoformat(value):
    if isinstance(value, dict):
        return {key: _isoformat(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_isoformat(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat(timespec="seconds")
    return value


def author_email_target(user_id):
    """Email e preferenza dell'autore per l'avviso facoltativo via email."""
    with database_cursor() as cursor:
        cursor.execute("""SELECT Email AS email, Nome AS nome, NotificheEmail AS notifiche_email, StatoAccount AS stato
            FROM UTENTE WHERE IdUtente=%s""", (user_id,))
        return cursor.fetchone()
