from flask import Blueprint, flash, g, jsonify, redirect, render_template, request

from backend.database import create_report, list_reports
from backend.forms import ReportForm
from backend.security import login_required


reports = Blueprint("reports", __name__)


@reports.route("/reports/new", methods=["GET", "POST"])
@login_required
def new_report():
    form = ReportForm()
    if form.validate_on_submit():
        # L'autore proviene dalla sessione verificata, mai da un input del form.
        create_report(form.report_data(), author=g.user)
        flash("Segnalazione pubblicata correttamente." if form.tipo.data == "segnalazione"
              else "Proposta pubblicata correttamente.", "success")
        # Post/Redirect/Get: il refresh della home non ripete l'inserimento.
        return redirect("/", code=303)
    return render_template("report_new.html", form=form), (400 if request.method == "POST" else 200)


@reports.get("/api/segnalazioni")
def get_reports():
    return jsonify(list_reports(request.args.get("q", "").strip()[:200]))


@reports.post("/api/segnalazioni")
@login_required
def post_report():
    data = request.get_json(silent=True)
    fields = ("tipo", "titolo", "descrizione", "indirizzo")
    if not isinstance(data, dict) or any(
        name in data and not isinstance(data[name], str) for name in fields
    ):
        return jsonify(error="Invia un oggetto JSON con campi testuali."), 400
    # La protezione CSRF globale ha già controllato l'header X-CSRFToken.
    form = ReportForm(formdata=None, data=data, meta={"csrf": False})
    if not form.validate():
        return jsonify(error="Dati non validi.", fields=form.errors), 400
    report = create_report(form.report_data(), author=g.user)
    return jsonify(report), 201
