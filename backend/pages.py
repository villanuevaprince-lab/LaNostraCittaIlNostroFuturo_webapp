from flask import Blueprint, jsonify, redirect, render_template

from backend.database import database_cursor
from backend.security import login_required, role_required


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
    return render_template("dashboard.html")


@pages.get("/profilo")
@login_required
def profile():
    return render_template("profile.html")


@pages.get("/moderazione")
@role_required("moderatore")
def moderation():
    return render_template("moderation.html")


@pages.get("/api/health")
def health():
    with database_cursor() as cursor:
        cursor.execute("SELECT 1 AS pronto")
        cursor.fetchone()
    return jsonify(status="ok", database="aiven", release="mysql-production-3000")
