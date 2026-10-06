"""Repository utenti compatibile con la tabella UTENTE già presente su Aiven."""

from datetime import datetime, timezone

from mysql.connector import IntegrityError

from backend.database import database_cursor, database_enabled, demo_store


USER_COLUMNS = """
    IdUtente AS id, Nome AS nome, Cognome AS cognome, Email AS email,
    HashPassword AS hash_password, StatoAccount AS stato_account,
    DataRegistrazione AS data_registrazione, DataCancellazione AS data_cancellazione
"""


class DuplicateEmail(Exception):
    pass


def find_user_by_id(user_id):
    if not database_enabled():
        store = demo_store()
        with store["lock"]:
            user = store["users"].get(user_id)
            return dict(user) if user else None
    with database_cursor() as cursor:
        cursor.execute(f"SELECT {USER_COLUMNS} FROM UTENTE WHERE IdUtente = %s", (user_id,))
        return cursor.fetchone()


def find_user_by_email(email):
    if not database_enabled():
        store = demo_store()
        with store["lock"]:
            return next((dict(user) for user in store["users"].values()
                         if user["email"] == email.lower()), None)
    with database_cursor() as cursor:
        cursor.execute(f"SELECT {USER_COLUMNS} FROM UTENTE WHERE Email = %s", (email.lower(),))
        return cursor.fetchone()


def create_user(nome, cognome, email, password_hash):
    user = {
        "nome": nome, "cognome": cognome, "email": email.lower(),
        "hash_password": password_hash, "stato_account": "attivo",
        "data_registrazione": datetime.now(timezone.utc), "data_cancellazione": None,
    }
    if not database_enabled():
        store = demo_store()
        with store["lock"]:
            if any(item["email"] == user["email"] for item in store["users"].values()):
                raise DuplicateEmail()
            user["id"] = max(store["users"], default=100) + 1
            store["users"][user["id"]] = user
        return dict(user)

    try:
        with database_cursor(write=True) as cursor:
            cursor.execute("""
                INSERT INTO UTENTE (Nome, Cognome, Email, HashPassword, StatoAccount)
                VALUES (%s, %s, %s, %s, 'attivo')
            """, (nome, cognome, user["email"], password_hash))
            user["id"] = cursor.lastrowid
    except IntegrityError as error:
        # La UNIQUE sul DB risolve anche registrazioni concorrenti con la stessa email.
        if error.errno == 1062:
            raise DuplicateEmail() from error
        raise
    return user
