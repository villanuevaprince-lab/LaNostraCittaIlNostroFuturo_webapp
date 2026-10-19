"""Importa gli allegati storici dal vecchio computer in Aiven.

Eseguire dalla radice: python -m backend.backfill_attachments --source <repo-vecchia> [--apply]
"""

import argparse
import hashlib
from pathlib import Path, PurePosixPath

from backend.app import create_app
from backend.database import database_cursor
from backend.repositories.reports import write_attachment_content
from backend.services.uploads import MAX_FILE_BYTES


def source_file(source, reference):
    relative = PurePosixPath(reference.replace("\\", "/").lstrip("/"))
    if not reference or ".." in relative.parts or ":" in str(relative):
        return None
    candidates = (source / relative, source / "storage" / "uploads" / relative,
                  source / "uploads" / relative)
    for candidate in candidates:
        path = candidate.resolve()
        if path.is_relative_to(source) and path.is_file():
            return path
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path,
                        help="Cartella del progetto sul computer dove sono conservate le foto")
    parser.add_argument("--apply", action="store_true", help="Scrive i file nel database Aiven")
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.is_dir():
        parser.error("La cartella --source non esiste.")
    app = create_app()
    with app.app_context():
        with database_cursor() as cursor:
            cursor.execute("""SELECT a.IdAllegato AS id, a.RiferimentoFile AS reference,
                a.HashSHA256 AS sha256 FROM ALLEGATO a
                WHERE NOT EXISTS (SELECT 1 FROM ALLEGATO_CONTENUTO c
                                  WHERE c.IdAllegato=a.IdAllegato)
                ORDER BY a.IdAllegato""")
            missing = cursor.fetchall()
        imported = 0
        unavailable = []
        for row in missing:
            path = source_file(source, row["reference"])
            if not path or path.stat().st_size > MAX_FILE_BYTES:
                unavailable.append(row["id"])
                continue
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if not content or (row["sha256"] and row["sha256"].lower() != digest):
                unavailable.append(row["id"])
                continue
            if args.apply:
                with database_cursor(write=True) as cursor:
                    cursor.execute("SELECT IdAllegato FROM ALLEGATO WHERE IdAllegato=%s FOR UPDATE", (row["id"],))
                    if not cursor.fetchone():
                        continue
                    cursor.execute("SELECT 1 FROM ALLEGATO_CONTENUTO WHERE IdAllegato=%s LIMIT 1", (row["id"],))
                    if cursor.fetchone():
                        continue
                    cursor.execute("UPDATE ALLEGATO SET DimensioneByte=%s, HashSHA256=%s WHERE IdAllegato=%s",
                                   (len(content), digest, row["id"]))
                    write_attachment_content(cursor, row["id"], content)
            imported += 1
        print(f"{'Importabili' if not args.apply else 'Importati'}: {imported}; file non trovati/non validi: {len(unavailable)}")
        if unavailable:
            print("ID allegati da recuperare dal vecchio computer:", ", ".join(map(str, unavailable)))


if __name__ == "__main__":
    main()
