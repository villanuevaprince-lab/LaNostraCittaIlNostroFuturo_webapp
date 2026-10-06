from flask import Blueprint, jsonify, redirect, render_template

from backend.database import database_enabled
from backend.security import login_required


pages = Blueprint("pages", __name__)


@pages.get("/")
def home():
    return render_template("home.html")


@pages.get("/home")
def home_alias():
    return redirect("/")


@pages.get("/dashboard")
@login_required
def dashboard():
    # Per ora la bacheca è comune: non duplichiamo una seconda homepage.
    return redirect("/")


@pages.get("/api/health")
def health():
    # Indica la configurazione, non esegue una connessione o una migrazione Aiven.
    return jsonify(status="ok", database="aiven" if database_enabled() else "demo")
