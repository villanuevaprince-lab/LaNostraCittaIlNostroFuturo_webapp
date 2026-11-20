"""Applica 010 (pipeline di verifica AI) con le credenziali del .env, senza mysql.exe."""
from backend.app import create_app
from backend.database import ROOT_DIR, database_cursor


def main():
    app = create_app()
    with app.app_context(), database_cursor(write=True) as cursor:
        cursor.execute("""SELECT COUNT(*) AS n FROM information_schema.tables
            WHERE table_schema=DATABASE() AND table_name='VERIFICA_JOB'""")
        if cursor.fetchone()["n"]:
            raise SystemExit("Migrazione 010 già applicata (tabella VERIFICA_JOB presente).")
        cursor.execute("""SELECT COUNT(*) AS n FROM information_schema.tables
            WHERE table_schema=DATABASE() AND table_name='NOTIFICA'""")
        if not cursor.fetchone()["n"]:
            raise SystemExit("Applica prima la migrazione 007 (tabella NOTIFICA).")
        sql = (ROOT_DIR / "database/migrations/010_ai_verification_pipeline.sql").read_text(encoding="utf-8")
        sql = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
        for statement in sql.split(";"):
            if statement.strip():
                cursor.execute(statement)
    print("Migrazione 010 completata.")


if __name__ == "__main__":
    main()
