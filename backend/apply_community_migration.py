"""Applica 007 con le credenziali del .env, senza mysql.exe."""
from backend.app import create_app
from backend.database import ROOT_DIR, database_cursor


def main():
    app = create_app()
    with app.app_context(), database_cursor(write=True) as cursor:
        cursor.execute("SELECT COUNT(*) AS n FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='COMMENTO' AND column_name='IdCommentoPadre'")
        if cursor.fetchone()["n"]:
            raise SystemExit("Migrazione 007 già avviata/applicata. Verifica anche la tabella NOTIFICA prima di riprovare.")
        sql = (ROOT_DIR / "database/migrations/007_comments_notifications.sql").read_text(encoding="utf-8")
        sql = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
        for statement in sql.split(";"):
            if statement.strip():
                cursor.execute(statement)
    print("Migrazione 007 completata.")


if __name__ == "__main__":
    main()
