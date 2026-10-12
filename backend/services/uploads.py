"""Validazione e salvataggio locale degli allegati segnalazione."""

from io import BytesIO
from pathlib import Path
import hashlib
import secrets

from PIL import ExifTags, Image, UnidentifiedImageError
from flask import current_app


MAX_FILE_BYTES = 20 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
VIDEO_TYPES = {"video/mp4": ".mp4", "video/webm": ".webm"}


class UploadError(ValueError):
    pass


def _mime_from_signature(data):
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video/mp4"
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"
    return None


def _fraction(value):
    return float(value[0]) / float(value[1]) if isinstance(value, tuple) else float(value)


def _gps_coordinates(exif):
    try:
        gps = exif.get_ifd(34853)
        tags = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps.items()}
        lat = sum(_fraction(v) / (60 ** i) for i, v in enumerate(tags["GPSLatitude"]))
        lon = sum(_fraction(v) / (60 ** i) for i, v in enumerate(tags["GPSLongitude"]))
        if tags.get("GPSLatitudeRef") == "S":
            lat = -lat
        if tags.get("GPSLongitudeRef") == "W":
            lon = -lon
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return round(lat, 6), round(lon, 6)
    except (KeyError, TypeError, ValueError, ZeroDivisionError, AttributeError):
        pass
    return None, None


def save_upload(file_storage, accessible_description):
    if file_storage is None or not file_storage.filename:
        raise UploadError("Allega una foto o un breve video.")
    raw = file_storage.stream.read(MAX_FILE_BYTES + 1)
    if not raw:
        raise UploadError("Il file è vuoto.")
    if len(raw) > MAX_FILE_BYTES:
        raise UploadError("Il file supera il limite di 20 MB.")
    mime = _mime_from_signature(raw)
    if mime not in IMAGE_TYPES and mime not in VIDEO_TYPES:
        raise UploadError("Formato non supportato: usa JPEG, PNG, WebP, MP4 o WebM.")
    latitude = longitude = None
    if mime in IMAGE_TYPES:
        try:
            image = Image.open(BytesIO(raw))
            image.verify()
            image = Image.open(BytesIO(raw))
            if image.width * image.height > 40_000_000:
                raise UploadError("L'immagine ha dimensioni eccessive.")
            latitude, longitude = _gps_coordinates(image.getexif())
            # Risalvare rimuove EXIF e metadati potenzialmente privati.
            cleaned = BytesIO()
            fmt = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[mime]
            if fmt == "JPEG" and image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            image.save(cleaned, format=fmt, optimize=True)
            raw = cleaned.getvalue()
            if len(raw) > MAX_FILE_BYTES:
                raise UploadError("L'immagine elaborata supera il limite di 20 MB.")
        except (UnidentifiedImageError, OSError, ValueError) as error:
            if isinstance(error, UploadError):
                raise
            raise UploadError("Il file immagine non è valido.") from error
    description = (accessible_description or "").strip()
    if not description or len(description) > 500:
        raise UploadError("Aggiungi una descrizione accessibile (massimo 500 caratteri).")

    root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    root.mkdir(mode=0o750, parents=True, exist_ok=True)
    filename = secrets.token_hex(24) + (IMAGE_TYPES | VIDEO_TYPES)[mime]
    path = (root / filename).resolve()
    if root not in path.parents:
        raise UploadError("Percorso file non valido.")
    path.write_bytes(raw)
    return {
        "path": path, "reference": filename, "mime": mime,
        "original_name": Path(file_storage.filename).name[:255],
        "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        "accessible_description": description,
        "latitude": latitude, "longitude": longitude,
    }


def remove_upload(upload):
    if upload:
        try:
            Path(upload["path"]).unlink(missing_ok=True)
        except OSError:
            current_app.logger.exception("Impossibile rimuovere un allegato temporaneo")
