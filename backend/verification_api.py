"""Verifica AI: reinvio e ricorso dell'autore, dashboard e decisioni dei moderatori."""

from flask import Blueprint, current_app, g, jsonify, render_template, request

from backend.repositories import verification as repository
from backend.security import limiter, login_required, role_required
from backend.services.verification_worker import deliver_email


verification_api = Blueprint("verification_api", __name__)


def _json():
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else None


def _text(payload, key, minimum, maximum):
    value = payload.get(key)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if minimum <= len(value) <= maximum else None


def _action_error(error):
    return jsonify(error=str(error)), error.status


# --- autore ------------------------------------------------------------------

@verification_api.post("/api/segnalazioni/<int:report_id>/reinvio")
@login_required
@limiter.limit("10 per hour")
def resubmit_report(report_id):
    payload = _json()
    if payload is None:
        return jsonify(error="Invia un oggetto JSON valido."), 400
    title = _text(payload, "titolo", 3, 200)
    description = _text(payload, "descrizione", 10, 5000)
    if title is None or description is None:
        return jsonify(error="Titolo da 3 a 200 caratteri e descrizione da 10 a 5000 caratteri."), 400
    try:
        result = repository.resubmit(report_id, g.user["id"], title, description,
                                     current_app.config["VERIFICA_MAX_REINVII"])
    except repository.VerificationActionError as error:
        return _action_error(error)
    return jsonify(ok=True, **result,
                   message="Contenuto reinviato: è di nuovo in fase di valutazione.")


@verification_api.post("/api/segnalazioni/<int:report_id>/ricorso")
@login_required
@limiter.limit("10 per hour")
def appeal_report(report_id):
    payload = _json()
    if payload is None:
        return jsonify(error="Invia un oggetto JSON valido."), 400
    reason = _text(payload, "motivazione", 10, 1000)
    if reason is None:
        return jsonify(error="Spiega in 10–1000 caratteri perché chiedi la revisione."), 400
    try:
        result = repository.appeal(report_id, g.user["id"], reason)
    except repository.VerificationActionError as error:
        return _action_error(error)
    return jsonify(ok=True, **result, message="Ricorso inviato: un moderatore esaminerà il contenuto.")


# --- moderatori --------------------------------------------------------------

@verification_api.get("/moderazione/verifiche")
@role_required("moderatore")
def verification_page():
    return render_template("verification_moderation.html")


@verification_api.get("/api/moderazione/verifiche")
@role_required("moderatore")
def verification_queue():
    view = request.args.get("vista", "priorita")
    cursor = request.args.get("cursor", type=int)
    limit = request.args.get("limit", 25, type=int)
    if (view not in {"priorita", "tutte", *repository.VERIFICATION_STATES} or not 1 <= limit <= 50
            or (cursor is not None and cursor < 1)):
        return jsonify(error="Vista o paginazione non valide."), 400
    return jsonify(repository.list_items(view, cursor, limit))


@verification_api.get("/api/moderazione/verifiche/conteggi")
@role_required("moderatore")
def verification_counts():
    return jsonify(repository.counts_by_state())


@verification_api.get("/api/moderazione/verifiche/<int:report_id>")
@role_required("moderatore")
def verification_detail(report_id):
    item = repository.item_detail(report_id)
    if item is None:
        return jsonify(error="Contenuto non trovato."), 404
    return jsonify(item)


@verification_api.post("/api/moderazione/verifiche/<int:report_id>/decisione")
@role_required("moderatore")
def verification_decision(report_id):
    payload = _json()
    if payload is None:
        return jsonify(error="Invia un oggetto JSON valido."), 400
    action = payload.get("azione")
    reason = _text(payload, "motivazione", 3, 1000)
    if action not in {"approva", "respingi"}:
        return jsonify(error="Azione non valida: usa approva o respingi."), 400
    if reason is None:
        return jsonify(error="Indica il motivo della decisione (3–1000 caratteri)."), 400
    try:
        result = repository.moderator_decide(report_id, g.user["id"], action, reason)
    except repository.VerificationActionError as error:
        return _action_error(error)
    deliver_email(result.pop("notifica"))
    return jsonify(ok=True, **result)
