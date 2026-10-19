from pathlib import Path
from io import BytesIO

from flask import Blueprint, current_app, flash, g, jsonify, redirect, render_template, request, send_file
from mysql.connector import IntegrityError

from backend.repositories.reports import (
    add_comment, attachment_content, attachment_path, block_user, change_report_state, get_report_record,
    list_moderation_reports, list_moderation_users, list_report_records,
    moderate_comment, moderate_report, moderate_reports, permanently_ban_user,
    report_comments, STATE_TRANSITIONS,
    set_support, unblock_user, user_supports, withdraw_report,
)
from backend.services.reports import ReportValidationError, create_report
from backend.services.uploads import UploadError
from backend.security import login_required, role_required


reports = Blueprint("reports", __name__)


@reports.get("/reports/new")
@login_required
def new_report():
    return render_template("report_new.html", user=g.user)


@reports.get("/reports/<int:report_id>")
def report_detail_page(report_id):
    report = get_report_record(report_id)
    if not report or (report["visibilita"] != "pubblica" and
                      not (g.user and (g.user["id"] == report["autore_id"] or g.user["is_moderator"]))):
        return render_template("error.html", message="Segnalazione non trovata.", status=404), 404
    return render_template("report_detail.html", report_id=report_id)


@reports.get("/api/segnalazioni")
def get_reports():
    if request.args.get("mie") == "1" and g.user is None:
        return jsonify(error="Accesso richiesto."), 401
    order = request.args.get("ordina", "recenti")
    if order not in {"recenti", "sostegni"}:
        return jsonify(error="Ordinamento non valido."), 400
    raw_categories = request.args.getlist("categoria")
    if (len(raw_categories) > 10 or any(not value.isdigit() or int(value) < 1 for value in raw_categories)
            or len(set(raw_categories)) != len(raw_categories)):
        return jsonify(error="Seleziona fino a dieci categorie distinte."), 400
    categories = [int(value) for value in raw_categories]
    rows = list_report_records(
        request.args.get("q", "").strip()[:200],
        request.args.get("quartiere", type=int), categories or None,
        request.args.get("stato", "").strip()[:30] or None,
        g.user["id"] if request.args.get("mie") == "1" and g.user else None,
        g.user["id"] if g.user else None,
        order,
    )
    return jsonify(rows)


@reports.get("/api/me/segnalazioni")
@login_required
def my_reports():
    view = request.args.get("vista", "tutte")
    cursor = request.args.get("cursor", type=int)
    if view not in {"tutte", "pubblica", "bozza", "nascosta", "rimossa_moderazione", "rimossa_autore"} or (cursor is not None and cursor < 1):
        return jsonify(error="Vista o paginazione non valide."), 400
    rows = list_report_records(author_id=g.user["id"], viewer_id=g.user["id"],
                               visibility_filter=view, cursor_id=cursor, limit=26)
    page = rows[:25]
    return jsonify(items=page, next_cursor=page[-1]["id"] if len(rows) > 25 else None)


@reports.post("/api/segnalazioni")
@login_required
def post_report():
    if not request.mimetype or not request.mimetype.startswith("multipart/form-data"):
        return jsonify(error="Invia il form multipart con un allegato."), 400
    data = request.form.to_dict()
    if "categoria_ids" in request.form:
        data["categoria_ids"] = request.form.getlist("categoria_ids")
    try:
        report = create_report(data, author=g.user, uploaded_file=request.files.get("allegato"))
    except (ReportValidationError, UploadError) as error:
        return jsonify(error=str(error)), 400
    except IntegrityError as error:
        if error.errno == 1062:
            return jsonify(error="Operazione duplicata."), 409
        raise
    flash("Contenuto pubblicato. Lo trovi nella tua area personale e nella bacheca.", "success")
    return jsonify(ok=True, report=report, redirect="/dashboard"), 201


@reports.get("/api/segnalazioni/<int:report_id>")
def get_report(report_id):
    report = get_report_record(report_id)
    if not report or (report["visibilita"] != "pubblica" and
                      not (g.user and (g.user["id"] == report["autore_id"] or g.user["is_moderator"]))):
        return jsonify(error="Segnalazione non trovata."), 404
    report["commenti"] = report_comments(report_id) if report["visibilita"] == "pubblica" else []
    report["data_creazione"] = report["data_creazione"].isoformat(timespec="seconds")
    return jsonify(report)


@reports.delete("/api/segnalazioni/<int:report_id>")
@login_required
def delete_report(report_id):
    result = withdraw_report(report_id, g.user["id"])
    if result is None:
        return jsonify(error="Segnalazione non trovata."), 404
    return jsonify(ok=True, ritirata=True)


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
    if comment is None:
        return jsonify(error="Contenuto non più pubblico."), 409
    return jsonify(comment), 201


@reports.put("/api/segnalazioni/<int:report_id>/sostegno")
@login_required
def put_support(report_id):
    report = get_report_record(report_id)
    if not report or report.get("visibilita", "pubblica") != "pubblica":
        return jsonify(error="Segnalazione non trovata."), 404
    try:
        summary = set_support(report_id, g.user["id"], True)
    except IntegrityError as error:
        if error.errno == 1062:
            return jsonify(error="Hai già espresso sostegno a questa segnalazione."), 409
        raise
    if summary is None:
        return jsonify(error="Contenuto non più pubblico."), 409
    return jsonify(ok=True, **summary), 200


@reports.delete("/api/segnalazioni/<int:report_id>/sostegno")
@login_required
def delete_support(report_id):
    report = get_report_record(report_id)
    if not report or report.get("visibilita", "pubblica") != "pubblica":
        return jsonify(error="Segnalazione non trovata."), 404
    summary = set_support(report_id, g.user["id"], False)
    if summary is None:
        return jsonify(error="Contenuto non più pubblico."), 409
    return jsonify(ok=True, **summary)


@reports.get("/api/segnalazioni/<int:report_id>/sostegno")
@login_required
def get_support(report_id):
    report = get_report_record(report_id)
    if not report or report.get("visibilita", "pubblica") != "pubblica":
        return jsonify(error="Segnalazione non trovata."), 404
    return jsonify(sostenuta=user_supports(report_id, g.user["id"]))


@reports.get("/api/stati")
def get_states():
    rows = [
        {"codice": "nuova", "etichetta": "Nuova"},
        {"codice": "aperta", "etichetta": "Aperta"},
        {"codice": "in_valutazione", "etichetta": "In valutazione"},
        {"codice": "in_lavorazione", "etichetta": "In lavorazione"},
        {"codice": "presa_in_carico", "etichetta": "Presa in carico"},
        {"codice": "risolta", "etichetta": "Risolta"},
        {"codice": "chiusa", "etichetta": "Chiusa"},
    ]
    for row in rows:
        row["prossimi"] = sorted(STATE_TRANSITIONS.get(row["codice"], set()))
    return jsonify(rows)


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


@reports.get("/api/moderazione/coda")
@role_required("moderatore")
def moderation_queue():
    visibility = request.args.get("vista", request.args.get("visibilita", "tutte"))
    cursor = request.args.get("cursor", type=int)
    limit = request.args.get("limit", 25, type=int)
    if visibility not in {*STATE_TRANSITIONS, "tutte", "rimossa", "pubblica", "bozza", "nascosta"} or not 1 <= limit <= 50 or cursor is not None and cursor < 1:
        return jsonify(error="Filtro o paginazione non validi."), 400
    return jsonify(list_moderation_reports(cursor, visibility, limit))


@reports.post("/api/moderazione/segnalazioni/azioni")
@role_required("moderatore")
def moderate_batch():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Invia un oggetto JSON valido."), 400
    ids, action = payload.get("ids"), payload.get("azione")
    actions = {"approva": "pubblica", "rifiuta": "rimossa", "nascondi": "nascosta"}
    if (action not in actions or not isinstance(ids, list) or not 1 <= len(ids) <= 50
            or any(type(value) is not int or value < 1 for value in ids)):
        return jsonify(error="Azione o selezione non valida (massimo 50)."), 400
    return jsonify(moderate_reports(ids, g.user["id"], actions[action]))


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


@reports.post("/api/moderazione/utenti/<int:user_id>/ban-permanente")
@role_required("moderatore")
def moderator_permanent_ban(user_id):
    payload = request.get_json(silent=True)
    reason = payload.get("motivazione", "").strip() if isinstance(payload, dict) and isinstance(payload.get("motivazione"), str) else ""
    if not 1 <= len(reason) <= 3000:
        return jsonify(error="Inserisci una motivazione (massimo 3000 caratteri)."), 400
    if not permanently_ban_user(user_id, g.user["id"], reason):
        return jsonify(error="Utente non disponibile o già bloccato permanentemente."), 409
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
    cursor = request.args.get("cursor", type=int)
    search = request.args.get("q", "").strip()
    if cursor is not None and cursor < 1 or len(search) > 100:
        return jsonify(error="Ricerca o paginazione non valida."), 400
    return jsonify(list_moderation_users(cursor, search=search))


@reports.get("/api/allegati/<int:attachment_id>")
def get_attachment(attachment_id):
    reference = attachment_path(attachment_id, g.user["id"] if g.user else None,
                                bool(g.user and g.user["is_moderator"]))
    if not reference or Path(reference).name != reference:
        # I percorsi legacy sono letti dal DB dopo il backfill, senza usarli come path locali.
        if not reference:
            return jsonify(error="Allegato non trovato."), 404
    try:
        stored = attachment_content(attachment_id)
    except ValueError:
        current_app.logger.error("Contenuto allegato %s non valido", attachment_id)
        return jsonify(error="Allegato non disponibile."), 503
    if stored:
        content, mime = stored
        return send_file(BytesIO(content), mimetype=mime, conditional=True,
                         as_attachment=not mime.startswith(("image/", "video/")), max_age=3600)
    if Path(reference).name != reference:
        return jsonify(error="Allegato legacy non ancora importato dal computer originale."), 404
    root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    path = (root / reference).resolve()
    if root not in path.parents or not path.is_file():
        return jsonify(error="Allegato non trovato."), 404
    return send_file(path, conditional=True, max_age=3600)
