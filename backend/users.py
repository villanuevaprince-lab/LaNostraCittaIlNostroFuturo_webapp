"""Repository utenti compatibile con la tabella UTENTE già presente su Aiven."""

from datetime import datetime, timezone

from mysql.connector import IntegrityError

from backend.database import database_cursor


USER_COLUMNS = """
    IdUtente AS id, IdQuartiere AS quartiere_id, Nome AS nome, Cognome AS cognome, Email AS email,
    HashPassword AS hash_password, Bio AS bio, NotificheEmail AS notifiche_email,
    AvatarRiferimento AS avatar_riferimento, SessionVersion AS session_version,
    StatoAccount AS stato_account,
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
        "quartiere_id": None, "bio": "", "notifiche_email": False, "avatar_riferimento": None,
        "session_version": 0,
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


def find_active_ban(user_id):
    """Ultimo blocco non revocato: motivo, inizio e fine prevista (None = permanente)."""
    with database_cursor() as cursor:
        cursor.execute("""SELECT IdBlocco AS id, Motivazione AS motivo, DataInizio AS data_inizio,
                                 DataFinePrevista AS data_fine
                          FROM BLOCCO WHERE IdUtenteBloccato = %s AND DataRevoca IS NULL
                          ORDER BY IdBlocco DESC LIMIT 1""", (user_id,))
        return cursor.fetchone()


def expire_ban(user_id, block_id):
    """Chiude un blocco temporaneo scaduto e riattiva l'account; idempotente."""
    with database_cursor(write=True) as cursor:
        cursor.execute("""UPDATE BLOCCO SET DataRevoca = CURRENT_TIMESTAMP,
                          MotivoRevoca = 'Scadenza del blocco temporaneo'
                          WHERE IdBlocco = %s AND IdUtenteBloccato = %s AND DataRevoca IS NULL""",
                       (block_id, user_id))
        if cursor.rowcount != 1:
            return False
        cursor.execute("UPDATE UTENTE SET StatoAccount = 'attivo' WHERE IdUtente = %s AND StatoAccount = 'bloccato'",
                       (user_id,))
        cursor.execute("""INSERT INTO EVENTO_LOG
            (IdEsecutore, TipoAzione, Esito, Dettagli, IdUtenteBersaglio, IdBlocco)
            VALUES (NULL, 'scadenza_blocco', 'successo', 'Blocco temporaneo scaduto', %s, %s)""",
            (user_id, block_id))
    return True


def has_role(user_id, role="moderatore"):
    if role not in {"moderatore", "amministratore"}:
        return False
    with database_cursor() as cursor:
        cursor.execute("SELECT LivelloPermessi FROM MODERATORE WHERE IdUtente = %s", (user_id,))
        moderator = cursor.fetchone()
        return bool(moderator) and (role == "moderatore" or moderator["LivelloPermessi"] == "amministratore")


def update_profile(user_id, data):
    with database_cursor(write=True) as cursor:
        cursor.execute("SELECT Nome, Cognome, IdQuartiere, Bio, NotificheEmail FROM UTENTE WHERE IdUtente=%s FOR UPDATE", (user_id,))
        previous = cursor.fetchone()
        if not previous:
            return None
        cursor.execute("""UPDATE UTENTE SET Nome = %s, Cognome = %s, IdQuartiere = %s,
                          Bio = %s, NotificheEmail = %s
                          WHERE IdUtente = %s AND StatoAccount = 'attivo'""",
                       (data["nome"], data["cognome"], data.get("quartiere_id"),
                        data["bio"], data["notifiche_email"], user_id))
        cursor.execute("""INSERT INTO EVENTO_LOG
            (IdEsecutore, TipoAzione, Esito, Dettagli, IdUtenteBersaglio)
            VALUES (%s, 'modifica_profilo', 'successo', 'Aggiornato il profilo', %s)""",
            (user_id, user_id))
        event_id = cursor.lastrowid
        for field, key in (("Nome", "nome"), ("Cognome", "cognome"), ("IdQuartiere", "quartiere_id"),
                           ("Bio", "bio"), ("NotificheEmail", "notifiche_email")):
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


def change_password_hash(user_id, previous_hash, new_hash):
    """CAS: una modifica concorrente della password non viene sovrascritta."""
    with database_cursor(write=True) as cursor:
        cursor.execute("""UPDATE UTENTE SET HashPassword=%s, SessionVersion=SessionVersion+1 WHERE IdUtente=%s
            AND HashPassword=%s AND StatoAccount='attivo'""", (new_hash, user_id, previous_hash))
        if cursor.rowcount != 1:
            return False
        cursor.execute("""INSERT INTO EVENTO_LOG
            (IdEsecutore, TipoAzione, Esito, Dettagli, IdUtenteBersaglio)
            VALUES (%s, 'modifica_password', 'successo', 'Password aggiornata', %s)""", (user_id, user_id))
    return True


def set_avatar_reference(user_id, reference):
    with database_cursor(write=True) as cursor:
        cursor.execute("""UPDATE UTENTE SET AvatarRiferimento=%s
            WHERE IdUtente=%s AND StatoAccount='attivo'""", (reference, user_id))
        if cursor.rowcount != 1:
            return False
        cursor.execute("""INSERT INTO EVENTO_LOG
            (IdEsecutore, TipoAzione, Esito, Dettagli, IdUtenteBersaglio)
            VALUES (%s, 'modifica_avatar', 'successo', 'Avatar aggiornato', %s)""", (user_id, user_id))
    return True


def reset_password_hash(user_id, previous_hash, new_hash):
    """Reset da link email. La condizione sull'hash precedente rende il token monouso
    anche con richieste concorrenti; SessionVersion+1 chiude tutte le sessioni aperte."""
    with database_cursor(write=True) as cursor:
        cursor.execute("""UPDATE UTENTE SET HashPassword=%s, SessionVersion=SessionVersion+1
            WHERE IdUtente=%s AND HashPassword=%s AND StatoAccount IN ('attivo', 'bloccato')
            AND DataCancellazione IS NULL""", (new_hash, user_id, previous_hash))
        if cursor.rowcount != 1:
            return False
        cursor.execute("""INSERT INTO EVENTO_LOG
            (IdEsecutore, TipoAzione, Esito, Dettagli, IdUtenteBersaglio)
            VALUES (%s, 'reset_password', 'successo', 'Password reimpostata tramite link email', %s)""",
            (user_id, user_id))
    return True


def change_email(user_id, previous_email, new_email):
    """Conferma del cambio email: vale solo se l'indirizzo attuale è ancora quello del token."""
    try:
        with database_cursor(write=True) as cursor:
            cursor.execute("""UPDATE UTENTE SET Email=%s WHERE IdUtente=%s AND Email=%s
                AND StatoAccount='attivo'""", (new_email.lower(), user_id, previous_email.lower()))
            if cursor.rowcount != 1:
                return False
            cursor.execute("""INSERT INTO EVENTO_LOG
                (IdEsecutore, TipoAzione, Esito, Dettagli, IdUtenteBersaglio)
                VALUES (%s, 'modifica_email', 'successo', 'Email confermata tramite link', %s)""",
                (user_id, user_id))
            cursor.execute("""INSERT INTO VARIAZIONE_LOG (IdEvento, NomeCampo, ValorePrecedente, ValoreSuccessivo)
                VALUES (%s, 'UTENTE.Email', %s, %s)""", (cursor.lastrowid, previous_email.lower(), new_email.lower()))
    except IntegrityError as error:
        if error.errno == 1062:
            raise DuplicateEmail() from error
        raise
    return True
