"""Applica 008 con le credenziali del .env, senza mysql.exe."""
from backend.app import create_app
from backend.database import ROOT_DIR, database_cursor


def main():
    app = create_app()
    with app.app_context(), database_cursor(write=True) as cursor:
        cursor.execute("""SELECT COUNT(*) AS n FROM information_schema.statistics
            WHERE table_schema=DATABASE() AND table_name='ANALISI_IA' AND index_name='idx_analisi_segnalazione'""")
        if cursor.fetchone()["n"]:
            raise SystemExit("Migrazione 008 già applicata (indice idx_analisi_segnalazione presente).")
        sql = (ROOT_DIR / "database/migrations/008_ai_analysis.sql").read_text(encoding="utf-8")
        sql = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
        for statement in sql.split(";"):
            if statement.strip():
                cursor.execute(statement)
    print("Migrazione 008 completata.")


if __name__ == "__main__":
    main()
