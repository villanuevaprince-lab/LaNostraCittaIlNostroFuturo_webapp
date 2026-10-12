from datetime import datetime, timezone

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
        categories = sorted({int(value) for value in data.get("categorie", [])})
    except (TypeError, ValueError):
        raise ReportValidationError("Quartiere o categorie non validi.")
    if report_type not in {"segnalazione", "proposta"}:
        raise ReportValidationError("Tipo non valido.")
    if not 3 <= len(title) <= 200:
        raise ReportValidationError("Il titolo deve contenere da 3 a 200 caratteri.")
    if not 10 <= len(description) <= 5000:
        raise ReportValidationError("La descrizione deve contenere da 10 a 5000 caratteri.")
    if not valid_neighborhood(neighborhood):
        raise ReportValidationError("Seleziona un quartiere attivo.")
    if not categories or len(categories) > 5 or not valid_categories(categories):
        raise ReportValidationError("Seleziona da una a cinque categorie valide.")
    address = (data.get("indirizzo") or "").strip()
    if len(address) > 255:
        raise ReportValidationError("L'indirizzo non può superare 255 caratteri.")
    latitude, longitude = data.get("latitude"), data.get("longitude")
    if latitude in (None, "") and longitude in (None, ""):
        latitude = longitude = None
    else:
        try:
            latitude, longitude = float(latitude), float(longitude)
        except (TypeError, ValueError):
            raise ReportValidationError("Inserisci coordinate numeriche valide.")
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ReportValidationError("Coordinate fuori dai limiti geografici.")
    description_accessible = data.get("descrizione_accessibile", "")
    upload = save_upload(uploaded_file, description_accessible)
    try:
        return create_report_record({
            "tipo": report_type, "titolo": title, "descrizione": description,
            "indirizzo": address, "quartiere_id": neighborhood, "categorie": categories,
            "latitude": latitude if latitude is not None else upload["latitude"],
            "longitude": longitude if longitude is not None else upload["longitude"],
            "data_creazione": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }, author, upload)
    except Exception:
        remove_upload(upload)
        raise
