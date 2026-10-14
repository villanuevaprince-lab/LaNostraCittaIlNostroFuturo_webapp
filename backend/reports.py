from pathlib import Path

from flask import Blueprint, current_app, flash, g, jsonify, redirect, render_template, request, send_file
from mysql.connector import IntegrityError

from backend.repositories.reports import (
    add_comment, attachment_path, block_user, change_report_state, get_report_record,
    list_active_users, list_report_records, moderate_comment, moderate_report,
    report_comments, set_support, unblock_user, user_supports,
)
from backend.services.reports import ReportValidationError, create_report
from backend.services.uploads import UploadError
from backend.security import login_required, role_required


reports = Blueprint("reports", __name__)


@reports.get("/reports/new")
@login_required
def new_report():
    return render_template("report_new.html", user=g.user)


@reports.get("/api/segnalazioni")
def get_reports():
    if request.args.get("mie") == "1" and g.user is None:
        return jsonify(error="Accesso richiesto."), 401
    order = request.args.get("ordina", "recenti")
    if order not in {"recenti", "sostegni"}:
        return jsonify(error="Ordinamento non valido."), 400
    rows = list_report_records(
        request.args.get("q", "").strip()[:200],
        request.args.get("quartiere", type=int), request.args.get("categoria", type=int),
        request.args.get("stato", "").strip()[:30] or None,
        g.user["id"] if request.args.get("mie") == "1" and g.user else None,
        order,
    )
    return jsonify(rows)


@reports.post("/api/segnalazioni")
@login_required
def post_report():
    if not request.mimetype or not request.mimetype.startswith("multipart/form-data"):
        return jsonify(error="Invia il form multipart con un allegato."), 400
    data = request.form.to_dict()
    data["categorie"] = request.form.getlist("categorie")
    try:
        report = create_report(data, author=g.user, uploaded_file=request.files.get("allegato"))
    except (ReportValidationError, UploadError) as error:
        return jsonify(error=str(error)), 400
    except IntegrityError as error:
        if error.errno == 1062:
            return jsonify(error="Operazione duplicata."), 409
        raise
    flash("Segnalazione pubblicata correttamente." if data["tipo"] == "segnalazione"
          else "Proposta pubblicata correttamente.", "success")
    return jsonify(ok=True, report=report, redirect="/"), 201


@reports.get("/api/segnalazioni/<int:report_id>")
def get_report(report_id):
    report = get_report_record(report_id)
    if not report or report.get("visibilita", "pubblica") != "pubblica":
        return jsonify(error="Segnalazione non trovata."), 404
    report["commenti"] = report_comments(report_id)
    return jsonify(report)


@reports.post("/api/segnalazioni/<int:report_id>/commenti")
@login_required
def post_comment(report_id):
    report = get_report_record(report_id)
    payload = request.get_json(silent=True)
    text = payload.get("testo", "").strip() if isinstance(payload, dict) and isinstance(payload.get("testo"), str) else ""
    if not report or report.get("visibilita", "pubblica") != "pubblica":
        return jsonify(error="Segnalazione non trovata."), 404
    if not 1 <= len(text) <= 3000:
        return jsonify(error="Il commento deve contenere da 1 a 3000 caratteri."), 400
    comment = add_comment(report_id, g.user["id"], text)
    return jsonify(comment), 201


@reports.put("/api/segnalazioni/<int:report_id>/sostegno")
@login_required
def put_support(report_id):
    report = get_report_record(report_id)
    if not report or report.get("visibilita", "pubblica") != "pubblica":
        return jsonify(error="Segnalazione non trovata."), 404
    try:
        if not set_support(report_id, g.user["id"], True):
            return jsonify(error="Hai già espresso sostegno a questa segnalazione."), 409
    except IntegrityError as error:
        if error.errno == 1062:
            return jsonify(error="Hai già espresso sostegno a questa segnalazione."), 409
        raise
    return jsonify(ok=True), 200


@reports.delete("/api/segnalazioni/<int:report_id>/sostegno")
@login_required
def delete_support(report_id):
    set_support(report_id, g.user["id"], False)
    return jsonify(ok=True)


@reports.get("/api/segnalazioni/<int:report_id>/sostegno")
@login_required
def get_support(report_id):
    if not get_report_record(report_id):
        return jsonify(error="Segnalazione non trovata."), 404
    return jsonify(sostenuta=user_supports(report_id, g.user["id"]))


@reports.get("/api/stati")
def get_states():
    return jsonify([
        {"codice": "nuova", "etichetta": "Nuova"},
        {"codice": "aperta", "etichetta": "Aperta"},
        {"codice": "in_valutazione", "etichetta": "In valutazione"},
        {"codice": "in_lavorazione", "etichetta": "In lavorazione"},
        {"codice": "presa_in_carico", "etichetta": "Presa in carico"},
        {"codice": "risolta", "etichetta": "Risolta"},
        {"codice": "chiusa", "etichetta": "Chiusa"},
    ])


@reports.patch("/api/segnalazioni/<int:report_id>/stato")
@role_required("moderatore")
def patch_report_state(report_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("stato"), str):
        return jsonify(error="Indica uno stato valido."), 400
    reason = payload.get("motivazione", "")
    if not isinstance(reason, str) or len(reason) > 500:
        return jsonify(error="Motivazione non valida."), 400
    result = change_report_state(report_id, g.user["id"], payload["stato"], reason.strip() or None)
    if result is False:
        return jsonify(error="Segnalazione non trovata."), 404
    if result is None:
        return jsonify(error="Stato non previsto."), 400
    return jsonify(ok=True)


@reports.patch("/api/moderazione/segnalazioni/<int:report_id>")
@role_required("moderatore")
def moderate_report_visibility(report_id):
    payload = request.get_json(silent=True)
    visibility = payload.get("visibilita") if isinstance(payload, dict) else None
    result = moderate_report(report_id, g.user["id"], visibility)
    if result is None:
        return jsonify(error="Segnalazione non trovata."), 404
    if result is False:
        return jsonify(error="Visibilità non valida."), 400
    return jsonify(ok=True)


@reports.delete("/api/moderazione/commenti/<int:comment_id>")
@role_required("moderatore")
def moderate_comment_visibility(comment_id):
    if not moderate_comment(comment_id, g.user["id"]):
        return jsonify(error="Commento non trovato."), 404
    return jsonify(ok=True)


@reports.post("/api/moderazione/utenti/<int:user_id>/blocco")
@role_required("moderatore")
def moderator_block_user(user_id):
    payload = request.get_json(silent=True)
    reason = payload.get("motivazione", "").strip() if isinstance(payload, dict) and isinstance(payload.get("motivazione"), str) else ""
    days = payload.get("giorni") if isinstance(payload, dict) else None
    if not reason or len(reason) > 3000:
        return jsonify(error="Inserisci una motivazione (massimo 3000 caratteri)."), 400
    if days is not None and (not isinstance(days, int) or not 1 <= days <= 365):
        return jsonify(error="La durata deve essere da 1 a 365 giorni oppure nulla."), 400
    if not block_user(user_id, g.user["id"], reason, days):
        return jsonify(error="Utente non disponibile o già bloccato."), 409
    return jsonify(ok=True)


@reports.post("/api/moderazione/utenti/<int:user_id>/sblocco")
@role_required("moderatore")
def moderator_unblock_user(user_id):
    payload = request.get_json(silent=True)
    reason = payload.get("motivazione", "Verifica del moderatore.") if isinstance(payload, dict) else "Verifica del moderatore."
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 3000:
        return jsonify(error="Motivazione non valida."), 400
    reason = reason.strip()
    if not unblock_user(user_id, g.user["id"], reason):
        return jsonify(error="Blocco attivo non trovato."), 404
    return jsonify(ok=True)


@reports.get("/api/moderazione/utenti")
@role_required("moderatore")
def moderator_users():
    return jsonify(list_active_users(exclude_user_id=g.user["id"]))


@reports.get("/api/allegati/<int:attachment_id>")
def get_attachment(attachment_id):
    reference = attachment_path(attachment_id)
    if not reference or Path(reference).name != reference:
        return jsonify(error="Allegato non trovato."), 404
    root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    path = (root / reference).resolve()
    if root not in path.parents or not path.is_file():
        return jsonify(error="Allegato non trovato."), 404
    return send_file(path, conditional=True, max_age=3600)
