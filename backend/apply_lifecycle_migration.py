"""python -m backend.apply_lifecycle_migration: legge il .env del progetto."""
from backend.app import create_app
from backend.database import ROOT_DIR, database_cursor

def main():
    app = create_app()
    with app.app_context(), database_cursor(write=True) as cursor:
        cursor.execute("SELECT COUNT(*) AS n FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='SEGNALAZIONE' AND column_name='duplicate_of_id'")
        if cursor.fetchone()["n"]:
            raise SystemExit("Migrazione 006 già avviata/applicata. Verifica anche PROPOSTA, DETTAGLIO_SEGNALAZIONE e ALLEGATO.Ruolo prima di riavviare il sito.")
        sql = (ROOT_DIR / "database/migrations/006_civic_lifecycle.sql").read_text(encoding="utf-8")
        sql = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
        for statement in sql.split(";"):
            if statement.strip():
                cursor.execute(statement)
    print("Migrazione 006 completata.")

if __name__ == "__main__":
    main()
