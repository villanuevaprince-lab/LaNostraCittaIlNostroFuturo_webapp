from flask import Blueprint, jsonify

from backend.services.catalog import get_catalogs


catalog_api = Blueprint("catalog_api", __name__, url_prefix="/api")


@catalog_api.get("/quartieri")
def neighborhoods():
    return jsonify(get_catalogs()["quartieri"])


@catalog_api.get("/categorie")
def categories():
    return jsonify(get_catalogs()["categorie"])
