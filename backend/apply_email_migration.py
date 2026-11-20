"""Applica 009 con le credenziali del .env, dopo aver escluso i duplicati di email."""
from backend.app import create_app
from backend.database import ROOT_DIR, database_cursor


def main():
    app = create_app()
    with app.app_context(), database_cursor(write=True) as cursor:
        cursor.execute("""SELECT COUNT(*) AS n FROM information_schema.table_constraints
            WHERE table_schema=DATABASE() AND table_name='UTENTE'
            AND constraint_name='chk_utente_email_normalizzata'""")
        if cursor.fetchone()["n"]:
            raise SystemExit("Migrazione 009 già applicata (vincolo chk_utente_email_normalizzata presente).")
        cursor.execute("""SELECT LOWER(TRIM(Email)) COLLATE utf8mb4_0900_ai_ci AS email, COUNT(*) AS n
            FROM UTENTE GROUP BY LOWER(TRIM(Email)) COLLATE utf8mb4_0900_ai_ci HAVING COUNT(*) > 1""")
        duplicates = cursor.fetchall()
        if duplicates:
            listing = ", ".join(f"{row['email']} ({row['n']})" for row in duplicates)
            raise SystemExit(f"Email duplicate dopo la normalizzazione: {listing}. Risolvile prima di migrare.")
        cursor.execute("""SELECT COUNT(*) AS n FROM UTENTE WHERE Email NOT LIKE '%_@_%'""")
        if cursor.fetchone()["n"]:
            raise SystemExit("Ci sono email senza '@': correggile prima di migrare.")
        sql = (ROOT_DIR / "database/migrations/009_user_email_normalized.sql").read_text(encoding="utf-8")
        sql = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
        for statement in sql.split(";"):
            if statement.strip():
                cursor.execute(statement)
    print("Migrazione 009 completata.")


if __name__ == "__main__":
    main()
