from decimal import Decimal, InvalidOperation

from backend.api.geo import in_milan

from backend.repositories.catalog import list_categories, valid_categories, valid_neighborhood
from backend.repositories.reports import create_report_record
from backend.services import ai as ai_service
from backend.services.uploads import remove_upload, save_upload

MAX_CATEGORIES = 5


class ReportValidationError(ValueError):
    pass


def create_report(data, author, uploaded_file):
    title = (data.get("titolo") or "").strip()
    description = (data.get("descrizione") or "").strip()
    report_type = data.get("tipo")
    neighborhood = data.get("quartiere_id")
    try:
        neighborhood = int(neighborhood)
    except (TypeError, ValueError):
        raise ReportValidationError("Quartiere non valido.")
    raw_categories = data.get("categoria_ids") or ([data.get("categoria_id")] if data.get("categoria_id") else [])
    # Con l'IA attiva la categoria può mancare: la propone il modello (o si chiede dopo).
    ai_active = ai_service.enabled()
    if not isinstance(raw_categories, list) or not (0 if ai_active else 1) <= len(raw_categories) <= MAX_CATEGORIES:
        raise ReportValidationError("Seleziona da una a cinque categorie.")
    try:
        category_ids = [int(category_id) for category_id in raw_categories]
    except (TypeError, ValueError):
        raise ReportValidationError("Categorie non valide.")
    if any(category_id <= 0 for category_id in category_ids) or len(set(category_ids)) != len(category_ids):
        raise ReportValidationError("Le categorie devono essere valide e distinte.")
    if report_type not in {"segnalazione", "proposta"}:
        raise ReportValidationError("Tipo non valido.")
    if not 3 <= len(title) <= 200:
        raise ReportValidationError("Il titolo deve contenere da 3 a 200 caratteri.")
    if not 10 <= len(description) <= 5000:
        raise ReportValidationError("La descrizione deve contenere da 10 a 5000 caratteri.")
    if not valid_neighborhood(neighborhood):
        raise ReportValidationError("Seleziona un quartiere attivo.")
    if not valid_categories(category_ids):
        raise ReportValidationError("Seleziona solo categorie attive.")
    address = (data.get("indirizzo") or "").strip()
    if not 3 <= len(address) <= 255:
        raise ReportValidationError("Seleziona un luogo e indica un indirizzo (3–255 caratteri).")
    try:
        latitude = Decimal(data.get("latitude") or "")
        longitude = Decimal(data.get("longitude") or "")
    except InvalidOperation:
        latitude = longitude = None  # il punto può arrivare dall'EXIF della foto
    else:
        if not latitude.is_finite() or not longitude.is_finite() or not in_milan(latitude, longitude):
            raise ReportValidationError("Seleziona un punto nell'area di Milano.")
    try:
        threshold = int(data.get("soglia_sostegni") or 100)
    except (ValueError, TypeError):
        raise ReportValidationError("Soglia di sostegni non valida.")
    if not 1 <= threshold <= 1000000:
        raise ReportValidationError("La soglia deve essere compresa fra 1 e 1000000.")
    upload = save_upload(uploaded_file, title)
    gps = upload.get("exif_gps")
    gps_in_milan = bool(gps) and in_milan(gps["latitude"], gps["longitude"])
    if latitude is None:
        if not gps_in_milan:
            raise ReportValidationError("Seleziona il punto sulla mappa.")
        latitude, longitude = Decimal(str(gps["latitude"])), Decimal(str(gps["longitude"]))
    ai = _analyze(title, description, category_ids, upload, gps, gps_in_milan) if ai_active else None
    record = {
        "tipo": report_type, "soglia_sostegni": threshold, "titolo": title, "descrizione": description,
        "indirizzo": address, "quartiere_id": neighborhood, "categorie": category_ids,
        "latitude": latitude.quantize(Decimal("0.000001")),
        "longitude": longitude.quantize(Decimal("0.000001")),
    }
    if ai:
        record["ia"] = ai
    try:
        return create_report_record(record, author, upload)
    except Exception:
        remove_upload(upload)
        raise


def _analyze(title, description, category_ids, upload, gps, gps_in_milan):
    ai = ai_service.analyze_report(title, description, list_categories(), set(category_ids), upload)
    if ai["esito"] == "blocca":
        raise ReportValidationError(ai["messaggi"][0])
    ai["categorie_ia"] = ai["categorie_ia"][:max(0, MAX_CATEGORIES - len(category_ids))]
    if not category_ids and not ai["categorie_ia"]:
        raise ReportValidationError("Non siamo riusciti a scegliere la categoria: selezionane almeno una.")
    if gps:
        ai["analisi"].append({
            "tipo": "exif_gps", "modello": "exif", "esito": "in_milano" if gps_in_milan else "fuori_milano",
            "confidenza": None, "risultato": gps, "revisione": False, "allegato": True,
        })
    return ai
