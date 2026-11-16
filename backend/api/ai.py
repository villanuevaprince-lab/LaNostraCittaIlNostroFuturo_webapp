"""Endpoint di supporto al form: suggerimento categorie e posizione letta dall'EXIF."""

from flask import Blueprint, jsonify, request

from backend.api.geo import in_milan
from backend.repositories.catalog import list_categories
from backend.security import limiter, login_required
from backend.services import ai
from backend.services.uploads import UploadError, read_exif_location


ai_api = Blueprint("ai_api", __name__, url_prefix="/api/ia")


@ai_api.post("/suggerisci-categorie")
@login_required
@limiter.limit("10 per minute")
def suggest_categories():
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("titolo") or "").strip()
    description = str(payload.get("descrizione") or "").strip()
    if not 3 <= len(title) <= 200 or not 10 <= len(description) <= 5000:
        return jsonify(error="Scrivi un titolo e una descrizione prima di chiedere un suggerimento."), 400
    if not ai.enabled():
        return jsonify(categorie=[], disponibile=False)
    categories = list_categories()
    try:
        picked = ai.classify_topics(title, description, categories)
    except ai.AIUnavailable:
        return jsonify(error="Il suggerimento automatico non è disponibile: scegli tu la categoria."), 503
    names = {category["id"]: category["nome"] for category in categories}
    return jsonify(disponibile=True, categorie=[
        {"id": item["id"], "nome": names[item["id"]], "confidenza": item["confidenza"]} for item in picked])


@ai_api.post("/analizza-foto")
@login_required
@limiter.limit("20 per minute")
def analyze_photo():
    try:
        gps = read_exif_location(request.files.get("allegato"))
    except UploadError as error:
        return jsonify(error=str(error)), 400
    if gps is None:
        return jsonify(gps=None)
    return jsonify(gps={**gps, "in_milan": in_milan(gps["latitude"], gps["longitude"])})
