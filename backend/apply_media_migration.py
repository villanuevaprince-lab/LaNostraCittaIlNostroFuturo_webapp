"""Applica la migrazione 005 usando le credenziali del .env, senza mysql.exe."""

from backend.app import create_app
from backend.database import ROOT_DIR, database_cursor


def main():
    app = create_app()
    statement = (ROOT_DIR / "database/migrations/005_shared_attachment_content.sql").read_text(encoding="utf-8")
    with app.app_context(), database_cursor(write=True) as cursor:
        cursor.execute(statement)
    print("Migrazione 005 applicata (o tabella già presente).")


if __name__ == "__main__":
    main()
