"""Repository utenti compatibile con la tabella UTENTE già presente su Aiven."""

from datetime import datetime, timezone

from mysql.connector import IntegrityError

from backend.database import database_cursor


USER_COLUMNS = """
    IdUtente AS id, IdQuartiere AS quartiere_id, Nome AS nome, Cognome AS cognome, Email AS email,
    HashPassword AS hash_password, StatoAccount AS stato_account,
    DataRegistrazione AS data_registrazione, DataCancellazione AS data_cancellazione
"""


class DuplicateEmail(Exception):
    pass


def find_user_by_id(user_id):
    with database_cursor() as cursor:
        cursor.execute(f"SELECT {USER_COLUMNS} FROM UTENTE WHERE IdUtente = %s", (user_id,))
        return cursor.fetchone()


def find_user_by_email(email):
    with database_cursor() as cursor:
        cursor.execute(f"SELECT {USER_COLUMNS} FROM UTENTE WHERE Email = %s", (email.lower(),))
        return cursor.fetchone()


def create_user(nome, cognome, email, password_hash):
    user = {
        "quartiere_id": None,
        "nome": nome, "cognome": cognome, "email": email.lower(),
        "hash_password": password_hash, "stato_account": "attivo",
        "data_registrazione": datetime.now(timezone.utc), "data_cancellazione": None,
    }
    try:
        with database_cursor(write=True) as cursor:
            cursor.execute("""
                INSERT INTO UTENTE (Nome, Cognome, Email, HashPassword, StatoAccount)
                VALUES (%s, %s, %s, %s, 'attivo')
            """, (nome, cognome, user["email"], password_hash))
            user["id"] = cursor.lastrowid
            cursor.execute("""INSERT INTO EVENTO_LOG
                (IdEsecutore, TipoAzione, Esito, Dettagli, IdUtenteBersaglio)
                VALUES (%s, 'registrazione_account', 'successo', 'Creato un account', %s)""",
                (user["id"], user["id"]))
    except IntegrityError as error:
        # La UNIQUE sul DB risolve anche registrazioni concorrenti con la stessa email.
        if error.errno == 1062:
            raise DuplicateEmail() from error
        raise
    return user


def has_role(user_id, role="moderatore"):
    if role not in {"moderatore", "amministratore"}:
        return False
    with database_cursor() as cursor:
        cursor.execute("SELECT LivelloPermessi FROM MODERATORE WHERE IdUtente = %s", (user_id,))
        moderator = cursor.fetchone()
        return bool(moderator) and (role == "moderatore" or moderator["LivelloPermessi"] == "amministratore")


def update_profile(user_id, data):
    with database_cursor(write=True) as cursor:
        cursor.execute("SELECT Nome, Cognome, IdQuartiere FROM UTENTE WHERE IdUtente=%s FOR UPDATE", (user_id,))
        previous = cursor.fetchone()
        if not previous:
            return None
        cursor.execute("""UPDATE UTENTE SET Nome = %s, Cognome = %s, IdQuartiere = %s
                          WHERE IdUtente = %s AND StatoAccount = 'attivo'""",
                       (data["nome"], data["cognome"], data.get("quartiere_id"), user_id))
        cursor.execute("""INSERT INTO EVENTO_LOG
            (IdEsecutore, TipoAzione, Esito, Dettagli, IdUtenteBersaglio)
            VALUES (%s, 'modifica_profilo', 'successo', 'Aggiornato il profilo', %s)""",
            (user_id, user_id))
        event_id = cursor.lastrowid
        for field, key in (("Nome", "nome"), ("Cognome", "cognome"), ("IdQuartiere", "quartiere_id")):
            if previous[field] != data.get(key):
                cursor.execute("""INSERT INTO VARIAZIONE_LOG
                    (IdEvento, NomeCampo, ValorePrecedente, ValoreSuccessivo)
                    VALUES (%s, %s, %s, %s)""", (event_id, f"UTENTE.{field}", previous[field], data.get(key)))
    return find_user_by_id(user_id)


def delete_account(user_id):
    with database_cursor(write=True) as cursor:
        cursor.execute("""UPDATE UTENTE SET StatoAccount = 'cancellato',
                          DataCancellazione = CURRENT_TIMESTAMP WHERE IdUtente = %s""", (user_id,))
        cursor.execute("""INSERT INTO EVENTO_LOG
            (IdEsecutore, TipoAzione, Esito, Dettagli, IdUtenteBersaglio)
            VALUES (%s, 'cancellazione_account', 'successo', 'Cancellazione logica richiesta dall’utente', %s)""",
            (user_id, user_id))


def update_password_hash(user_id, password_hash):
    with database_cursor(write=True) as cursor:
        cursor.execute("UPDATE UTENTE SET HashPassword=%s WHERE IdUtente=%s", (password_hash, user_id))
