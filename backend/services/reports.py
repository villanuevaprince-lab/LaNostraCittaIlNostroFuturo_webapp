from decimal import Decimal, InvalidOperation

from backend.api.geo import in_milan

from backend.repositories.catalog import valid_categories, valid_neighborhood
from backend.repositories.reports import create_report_record
from backend.services.uploads import remove_upload, save_upload


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
    if not isinstance(raw_categories, list) or not 1 <= len(raw_categories) <= 5:
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
        raise ReportValidationError("Seleziona il punto sulla mappa.")
    if not latitude.is_finite() or not longitude.is_finite() or not in_milan(latitude, longitude):
        raise ReportValidationError("Seleziona un punto nell'area di Milano.")
    try:
        threshold = int(data.get("soglia_sostegni") or 100)
    except (ValueError, TypeError):
        raise ReportValidationError("Soglia di sostegni non valida.")
    if not 1 <= threshold <= 1000000:
        raise ReportValidationError("La soglia deve essere compresa fra 1 e 1000000.")
    upload = save_upload(uploaded_file, title)
    try:
        return create_report_record({
            "tipo": report_type, "soglia_sostegni": threshold, "titolo": title, "descrizione": description,
            "indirizzo": address, "quartiere_id": neighborhood, "categorie": category_ids,
            "latitude": latitude.quantize(Decimal("0.000001")),
            "longitude": longitude.quantize(Decimal("0.000001")),
        }, author, upload)
    except Exception:
        remove_upload(upload)
        raise
