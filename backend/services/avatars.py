"""Avatar privi di metadati; i byte rimangono nel volume persistente degli upload."""

from io import BytesIO
from pathlib import Path
from uuid import uuid4

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError


def avatar_path(reference):
    if not reference or Path(reference).name != reference or not reference.endswith(".webp"):
        return None
    return Path(current_app.config["UPLOAD_FOLDER"]).resolve() / "avatars" / reference


def save_avatar(upload):
    if not upload or upload.mimetype not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValueError("Carica un'immagine JPEG, PNG o WebP.")
    content = upload.stream.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise ValueError("L'avatar non può superare 2 MB.")
    try:
        with Image.open(BytesIO(content)) as source:
            if source.width > 4096 or source.height > 4096:
                raise ValueError("L'immagine è troppo grande.")
            image = ImageOps.exif_transpose(source)
            image.thumbnail((512, 512))
            image = image.convert("RGB")
            destination = Path(current_app.config["UPLOAD_FOLDER"]).resolve() / "avatars"
            destination.mkdir(parents=True, exist_ok=True)
            reference = f"{uuid4().hex}.webp"
            image.save(destination / reference, "WEBP", quality=85)
            return reference
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("File immagine non valido.") from error
