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
        category_id = int(data.get("categoria_id"))
    except (TypeError, ValueError):
        raise ReportValidationError("Quartiere o categoria non validi.")
    if report_type not in {"segnalazione", "proposta"}:
        raise ReportValidationError("Tipo non valido.")
    if not 3 <= len(title) <= 200:
        raise ReportValidationError("Il titolo deve contenere da 3 a 200 caratteri.")
    if not 10 <= len(description) <= 5000:
        raise ReportValidationError("La descrizione deve contenere da 10 a 5000 caratteri.")
    if not valid_neighborhood(neighborhood):
        raise ReportValidationError("Seleziona un quartiere attivo.")
    if not valid_categories([category_id]):
        raise ReportValidationError("Seleziona una categoria valida.")
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
    upload = save_upload(uploaded_file, title)
    try:
        return create_report_record({
            "tipo": report_type, "titolo": title, "descrizione": description,
            "indirizzo": address, "quartiere_id": neighborhood, "categorie": [category_id],
            "latitude": latitude.quantize(Decimal("0.000001")),
            "longitude": longitude.quantize(Decimal("0.000001")),
        }, author, upload)
    except Exception:
        remove_upload(upload)
        raise
