"""Registrazione, login e logout: normali form POST con redirect dopo il successo."""

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session
from werkzeug.security import generate_password_hash

from backend.forms import LoginForm, RegisterForm
from backend.security import limiter, safe_next, start_session, verify_password
from backend.users import DuplicateEmail, create_user, find_user_by_email


auth = Blueprint("auth", __name__)


@auth.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute; 20 per hour", methods=["POST"])
def register():
    destination = safe_next(request.form.get("next", request.args.get("next")))
    if g.user:
        return redirect(destination, code=303)
    form = RegisterForm()
    if form.validate_on_submit():
        try:
            # Solo l'hash è scritto nel DB; mai la password originale.
            user = create_user(
                form.nome.data, form.cognome.data, form.email.data,
                generate_password_hash(form.password.data, method="scrypt"),
            )
        except DuplicateEmail:
            form.email.errors.append("Email già registrata. Accedi con il tuo account.")
            return render_template("register.html", form=form, next_url=destination), 409
        start_session(user)
        flash("Registrazione completata. Hai già effettuato l'accesso.", "success")
        return redirect(destination, code=303)
    status = 400 if request.method == "POST" else 200
    return render_template("register.html", form=form, next_url=destination), status


@auth.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute; 100 per hour", methods=["POST"])
def login():
    destination = safe_next(request.form.get("next", request.args.get("next")))
    if g.user:
        return redirect(destination, code=303)
    form = LoginForm()
    error = None
    if form.validate_on_submit():
        user = find_user_by_email(form.email.data)
        stored_hash = user["hash_password"] if user else current_app.extensions["dummy_password_hash"]
        valid = verify_password(stored_hash, form.password.data)
        if valid and user and user["stato_account"] == "attivo" and not user["data_cancellazione"]:
            start_session(user)
            flash("Accesso effettuato.", "success")
            return redirect(destination, code=303)
        # Non riveliamo se l'email esiste, se la password è errata o l'account è bloccato.
        error = "Email o password non valide, oppure account non disponibile."
    status = 401 if error else (400 if request.method == "POST" else 200)
    return render_template("login.html", form=form, next_url=destination, error=error), status


@auth.post("/logout")
def logout():
    # CSRFProtect controlla anche questo POST. Nessuna modifica tramite GET.
    session.clear()
    flash("Hai effettuato l'uscita.", "success")
    return redirect("/", code=303)
