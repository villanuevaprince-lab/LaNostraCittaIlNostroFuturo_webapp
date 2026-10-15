from backend.database import database_cursor
from datetime import datetime, timedelta


def create_report_record(data, author, upload):
    initial_state = "aperta" if data["tipo"] == "segnalazione" else "in_valutazione"

    with database_cursor(write=True) as cursor:
        cursor.execute("""INSERT INTO SEGNALAZIONE
            (IdAutore, IdQuartiere, Tipo, Titolo, Descrizione, Stato, Visibilita,
             Latitudine, Longitudine, Indirizzo)
            VALUES (%s, %s, %s, %s, %s, %s, 'bozza', %s, %s, %s)""",
            (author["id"], data["quartiere_id"], data["tipo"], data["titolo"],
             data["descrizione"], initial_state, data.get("latitude"), data.get("longitude"), data.get("indirizzo") or None))
        report_id = cursor.lastrowid
        cursor.execute("""INSERT INTO ALLEGATO
            (IdSegnalazione, IdAutore, TipoMedia, RiferimentoFile, NomeOriginale,
             DimensioneByte, HashSHA256, DescrizioneAccessibile)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (report_id, author["id"], upload["mime"], upload["reference"],
             upload["original_name"], upload["size"], upload["sha256"], upload["accessible_description"]))
        for category_id in data["categorie"]:
            cursor.execute("""INSERT INTO SEGNALAZIONE_CATEGORIA
                (IdSegnalazione, IdCategoria, Origine) VALUES (%s, %s, 'utente')""",
                (report_id, category_id))
        cursor.execute("""INSERT INTO STORICO_STATO
            (IdSegnalazione, StatoPrecedente, StatoSuccessivo, IdAutoreModifica, Motivazione)
            VALUES (%s, NULL, %s, %s, 'Invio per revisione')""",
            (report_id, initial_state, author["id"]))
        cursor.execute("""INSERT INTO EVENTO_LOG
            (IdEsecutore, TipoAzione, Esito, Dettagli, IdSegnalazione)
            VALUES (%s, 'creazione_segnalazione', 'successo', 'Contenuto inviato per revisione con allegato', %s)""",
            (author["id"], report_id))
        # Bozza qui significa inviata alla coda, non modificabile dall'autore.
    return {"id": report_id, "titolo": data["titolo"], "stato": initial_state,
            "visibilita": "bozza"}


def list_report_records(search="", neighborhood_id=None, category_id=None, state=None,
                        author_id=None, viewer_id=None, order="recenti"):
    filters = ["s.Visibilita = 'pubblica'" if author_id is None else "s.Visibilita IN ('pubblica','bozza','nascosta','rimossa')",
               "(%s = '' OR s.Titolo LIKE %s OR s.Descrizione LIKE %s OR COALESCE(s.Indirizzo, '') LIKE %s)"]
    params = [search, f"%{search}%", f"%{search}%", f"%{search}%"]
    if neighborhood_id:
        filters.append("s.IdQuartiere = %s")
        params.append(neighborhood_id)
    if state:
        filters.append("s.Stato = %s")
        params.append(state)
    if category_id:
        filters.append("EXISTS (SELECT 1 FROM SEGNALAZIONE_CATEGORIA sc WHERE sc.IdSegnalazione = s.IdSegnalazione AND sc.IdCategoria = %s)")
        params.append(category_id)
    if author_id:
        filters.append("s.IdAutore = %s")
        params.append(author_id)
    query = """SELECT s.IdSegnalazione AS id, s.Tipo AS tipo, s.Titolo AS titolo,
        s.Descrizione AS descrizione, s.Stato AS stato, s.Visibilita AS visibilita,
        COALESCE(s.Indirizzo, '') AS indirizzo,
        CONCAT(u.Nome, ' ', u.Cognome) AS autore, s.DataCreazione AS data_creazione,
        s.IdQuartiere AS quartiere_id, q.Nome AS quartiere,
        (SELECT COUNT(*) FROM SOSTEGNO so WHERE so.IdSegnalazione=s.IdSegnalazione AND so.DataRitiro IS NULL) AS sostegni,
        (%s IS NOT NULL AND EXISTS (SELECT 1 FROM SOSTEGNO own_so
           WHERE own_so.IdSegnalazione=s.IdSegnalazione AND own_so.IdUtente=%s
           AND own_so.DataRitiro IS NULL)) AS sostenuta,
        (SELECT COUNT(*) FROM COMMENTO c WHERE c.IdSegnalazione=s.IdSegnalazione
           AND c.Visibilita='pubblica') AS commenti_count,
        (SELECT a.IdAllegato FROM ALLEGATO a WHERE a.IdSegnalazione=s.IdSegnalazione ORDER BY a.IdAllegato LIMIT 1) AS allegato_id,
        (SELECT a.TipoMedia FROM ALLEGATO a WHERE a.IdSegnalazione=s.IdSegnalazione ORDER BY a.IdAllegato LIMIT 1) AS allegato_tipo,
        (SELECT a.DescrizioneAccessibile FROM ALLEGATO a WHERE a.IdSegnalazione=s.IdSegnalazione ORDER BY a.IdAllegato LIMIT 1) AS allegato_descrizione
        FROM SEGNALAZIONE s JOIN UTENTE u ON u.IdUtente=s.IdAutore
        LEFT JOIN QUARTIERE q ON q.IdQuartiere=s.IdQuartiere
        WHERE """ + " AND ".join(filters) + (
            " ORDER BY sostegni DESC, s.DataCreazione DESC, s.IdSegnalazione DESC LIMIT 100"
            if order == "sostegni" else
            " ORDER BY s.DataCreazione DESC, s.IdSegnalazione DESC LIMIT 100")
    with database_cursor() as cursor:
        cursor.execute(query, (viewer_id, viewer_id, *params))
        rows = cursor.fetchall()
    for row in rows:
        row["data_creazione"] = row["data_creazione"].isoformat(timespec="seconds")
    return rows


def get_report_record(report_id):
    with database_cursor() as cursor:
        cursor.execute("""SELECT s.IdSegnalazione AS id, s.IdQuartiere AS quartiere_id,
            s.Tipo AS tipo, s.Titolo AS titolo, s.Descrizione AS descrizione, s.Stato AS stato,
            s.Visibilita AS visibilita, s.DataCreazione AS data_creazione, s.Indirizzo AS indirizzo,
            s.Latitudine AS latitude, s.Longitudine AS longitude,
            s.IdAutore AS autore_id, q.Nome AS quartiere,
            CONCAT(u.Nome, ' ', u.Cognome) AS autore,
            (SELECT GROUP_CONCAT(c.Nome SEPARATOR ', ') FROM SEGNALAZIONE_CATEGORIA sc
             JOIN CATEGORIA c ON c.IdCategoria=sc.IdCategoria WHERE sc.IdSegnalazione=s.IdSegnalazione) AS categorie,
            (SELECT a.IdAllegato FROM ALLEGATO a WHERE a.IdSegnalazione=s.IdSegnalazione
             ORDER BY a.IdAllegato LIMIT 1) AS allegato_id,
            (SELECT a.TipoMedia FROM ALLEGATO a WHERE a.IdSegnalazione=s.IdSegnalazione
             ORDER BY a.IdAllegato LIMIT 1) AS allegato_tipo,
            (SELECT COUNT(*) FROM SOSTEGNO so WHERE so.IdSegnalazione=s.IdSegnalazione
             AND so.DataRitiro IS NULL) AS sostegni
            FROM SEGNALAZIONE s JOIN UTENTE u ON u.IdUtente=s.IdAutore
            LEFT JOIN QUARTIERE q ON q.IdQuartiere=s.IdQuartiere
            WHERE s.IdSegnalazione=%s""", (report_id,))
        return cursor.fetchone()


def report_comments(report_id):
    with database_cursor() as cursor:
        cursor.execute("""SELECT c.IdCommento AS id, c.Testo AS testo,
            c.DataPubblicazione AS data, CONCAT(u.Nome, ' ', u.Cognome) AS autore
            FROM COMMENTO c JOIN UTENTE u ON u.IdUtente=c.IdAutore
            WHERE c.IdSegnalazione=%s AND c.Visibilita='pubblica' ORDER BY c.DataPubblicazione""", (report_id,))
        rows = cursor.fetchall()
    for row in rows:
        row["data"] = row["data"].isoformat(timespec="seconds")
    return rows


def add_comment(report_id, user_id, text):
    with database_cursor(write=True) as cursor:
        cursor.execute("SELECT Visibilita FROM SEGNALAZIONE WHERE IdSegnalazione=%s FOR UPDATE", (report_id,))
        report = cursor.fetchone()
        if not report or report["Visibilita"] != "pubblica":
            return None
        cursor.execute("INSERT INTO COMMENTO (IdAutore, IdSegnalazione, Testo, Visibilita) VALUES (%s, %s, %s, 'pubblica')",
                       (user_id, report_id, text))
        comment_id = cursor.lastrowid
        cursor.execute("""INSERT INTO EVENTO_LOG
            (IdEsecutore, TipoAzione, Esito, Dettagli, IdSegnalazione, IdCommento)
            VALUES (%s, 'pubblicazione_commento', 'successo', 'Commento pubblicato', %s, %s)""",
            (user_id, report_id, comment_id))
        cursor.execute("""SELECT c.DataPubblicazione AS data, CONCAT(u.Nome, ' ', u.Cognome) AS autore
            FROM COMMENTO c JOIN UTENTE u ON u.IdUtente=c.IdAutore WHERE c.IdCommento=%s""", (comment_id,))
        row = cursor.fetchone()
        return {"id": comment_id, "testo": text, "autore": row["autore"],
                "data": row["data"].isoformat(timespec="seconds")}


def set_support(report_id, user_id, active):
    with database_cursor(write=True) as cursor:
        cursor.execute("SELECT Visibilita FROM SEGNALAZIONE WHERE IdSegnalazione=%s FOR UPDATE", (report_id,))
        report = cursor.fetchone()
        if not report or report["Visibilita"] != "pubblica":
            return None
        cursor.execute("""SELECT IdSostegno, DataRitiro FROM SOSTEGNO
            WHERE IdUtente=%s AND IdSegnalazione=%s FOR UPDATE""", (user_id, report_id))
        existing = cursor.fetchone()
        changed = False
        if active:
            if not existing:
                # Il vincolo unico gestisce anche due richieste contemporanee.
                cursor.execute("""INSERT INTO SOSTEGNO (IdUtente, IdSegnalazione) VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE DataRitiro=NULL""", (user_id, report_id))
                changed = cursor.rowcount > 0
            elif existing["DataRitiro"] is not None:
                cursor.execute("""UPDATE SOSTEGNO SET DataRitiro=NULL, DataEspressione=CURRENT_TIMESTAMP
                    WHERE IdSostegno=%s""", (existing["IdSostegno"],))
                changed = True
            action = "espressione_sostegno"
        else:
            cursor.execute("UPDATE SOSTEGNO SET DataRitiro=CURRENT_TIMESTAMP WHERE IdUtente=%s AND IdSegnalazione=%s AND DataRitiro IS NULL",
                           (user_id, report_id))
            changed = cursor.rowcount > 0
            action = "ritiro_sostegno"
        if changed:
            cursor.execute("SELECT IdSostegno FROM SOSTEGNO WHERE IdUtente=%s AND IdSegnalazione=%s", (user_id, report_id))
            support = cursor.fetchone()
            cursor.execute("""INSERT INTO EVENTO_LOG
                (IdEsecutore, TipoAzione, Esito, Dettagli, IdSegnalazione, IdSostegno)
                VALUES (%s, %s, 'successo', %s, %s, %s)""",
                (user_id, action, action.replace("_", " "), report_id, support["IdSostegno"]))
        cursor.execute("""SELECT COUNT(*) AS sostegni FROM SOSTEGNO
            WHERE IdSegnalazione=%s AND DataRitiro IS NULL""", (report_id,))
        count = cursor.fetchone()["sostegni"]
    return {"sostenuta": active, "sostegni": count}


def moderate_report(report_id, moderator_id, visibility):
    if visibility not in {"nascosta", "rimossa", "pubblica"}:
        return False
    result = moderate_reports([report_id], moderator_id, visibility)
    return None if result["missing"] else True


def moderate_reports(ids, moderator_id, visibility):
    """Una transazione e ordine di lock stabile per un batch massimo di 50."""
    if visibility not in {"nascosta", "rimossa", "pubblica"} or not ids or len(ids) > 50:
        raise ValueError("Azione o selezione non valida.")
    changed, missing, unchanged = 0, [], 0
    with database_cursor(write=True) as cursor:
        for report_id in sorted(set(ids)):
            cursor.execute("SELECT Visibilita FROM SEGNALAZIONE WHERE IdSegnalazione=%s FOR UPDATE", (report_id,))
            row = cursor.fetchone()
            if not row:
                missing.append(report_id)
            elif row["Visibilita"] == visibility or row["Visibilita"] == "rimossa":
                unchanged += 1  # rimosso è terminale: non ripubblicare contenuti ritirati
            else:
                cursor.execute("UPDATE SEGNALAZIONE SET Visibilita=%s WHERE IdSegnalazione=%s", (visibility, report_id))
                cursor.execute("""INSERT INTO EVENTO_LOG
                    (IdEsecutore, TipoAzione, Esito, Dettagli, IdSegnalazione)
                    VALUES (%s, 'moderazione_segnalazione', 'successo', %s, %s)""",
                    (moderator_id, f"Visibilità: {row['Visibilita']} → {visibility}", report_id))
                changed += 1
    return {"modificate": changed, "invariate": unchanged, "missing": missing}


def withdraw_report(report_id, author_id):
    with database_cursor(write=True) as cursor:
        cursor.execute("SELECT IdAutore, Visibilita FROM SEGNALAZIONE WHERE IdSegnalazione=%s FOR UPDATE", (report_id,))
        row = cursor.fetchone()
        if not row or row["IdAutore"] != author_id:
            return None
        if row["Visibilita"] == "rimossa":
            return False
        cursor.execute("UPDATE SEGNALAZIONE SET Visibilita='rimossa' WHERE IdSegnalazione=%s", (report_id,))
        cursor.execute("""INSERT INTO EVENTO_LOG (IdEsecutore, TipoAzione, Esito, Dettagli, IdSegnalazione)
            VALUES (%s, 'ritiro_segnalazione', 'successo', 'Contenuto ritirato dall’autore', %s)""",
            (author_id, report_id))
    return True


def list_moderation_reports(cursor_id=None, visibility="bozza", limit=25):
    with database_cursor() as cursor:
        cursor.execute("""SELECT s.IdSegnalazione AS id, s.Titolo AS titolo, s.Tipo AS tipo,
            s.Stato AS stato, s.Visibilita AS visibilita, s.DataCreazione AS data_creazione,
            CONCAT(u.Nome, ' ', u.Cognome) AS autore, u.IdUtente AS autore_id
            FROM SEGNALAZIONE s JOIN UTENTE u ON u.IdUtente=s.IdAutore
            WHERE s.Visibilita=%s AND (%s IS NULL OR s.IdSegnalazione < %s)
            ORDER BY s.IdSegnalazione DESC LIMIT %s""",
            (visibility, cursor_id, cursor_id, limit + 1))
        rows = cursor.fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    for row in rows:
        row["data_creazione"] = row["data_creazione"].isoformat(timespec="seconds")
    return {"items": rows, "next_cursor": rows[-1]["id"] if more else None}


def list_moderation_users(cursor_id=None, limit=25):
    with database_cursor() as cursor:
        cursor.execute("""SELECT u.IdUtente AS id, u.Nome AS nome, u.Cognome AS cognome,
            u.StatoAccount AS stato FROM UTENTE u LEFT JOIN MODERATORE m ON m.IdUtente=u.IdUtente
            WHERE u.StatoAccount IN ('attivo', 'bloccato') AND m.IdUtente IS NULL
              AND (%s IS NULL OR u.IdUtente < %s)
            ORDER BY u.IdUtente DESC LIMIT %s""", (cursor_id, cursor_id, limit + 1))
        rows = cursor.fetchall()
    more = len(rows) > limit
    return {"items": rows[:limit], "next_cursor": rows[limit - 1]["id"] if more else None}


def moderate_comment(comment_id, moderator_id):
    with database_cursor(write=True) as cursor:
        cursor.execute("UPDATE COMMENTO SET Visibilita='rimossa' WHERE IdCommento=%s", (comment_id,))
        if cursor.rowcount == 0:
            return False
        cursor.execute("""INSERT INTO EVENTO_LOG
            (IdEsecutore, TipoAzione, Esito, Dettagli, IdCommento)
            VALUES (%s, 'moderazione_commento', 'successo', 'Commento rimosso', %s)""",
            (moderator_id, comment_id))
    return True


def block_user(user_id, moderator_id, reason, days):
    if user_id == moderator_id:
        return False
    end_date = datetime.now() + timedelta(days=days) if days else None
    with database_cursor(write=True) as cursor:
        cursor.execute("""SELECT IdUtente FROM UTENTE WHERE IdUtente=%s AND StatoAccount='attivo'
            AND NOT EXISTS (SELECT 1 FROM MODERATORE WHERE IdUtente=%s) FOR UPDATE""", (user_id, user_id))
        if not cursor.fetchone():
            return False
        cursor.execute("UPDATE UTENTE SET StatoAccount='bloccato' WHERE IdUtente=%s", (user_id,))
        cursor.execute("""INSERT INTO BLOCCO (IdUtenteBloccato, IdModeratore, Motivazione, DataFinePrevista)
            VALUES (%s, %s, %s, %s)""", (user_id, moderator_id, reason, end_date))
        block_id = cursor.lastrowid
        cursor.execute("""INSERT INTO EVENTO_LOG
            (IdEsecutore, TipoAzione, Esito, Dettagli, IdUtenteBersaglio, IdBlocco)
            VALUES (%s, 'blocco_utente', 'successo', %s, %s, %s)""",
            (moderator_id, reason, user_id, block_id))
    return True


def unblock_user(user_id, moderator_id, reason):
    with database_cursor(write=True) as cursor:
        cursor.execute("""SELECT IdBlocco FROM BLOCCO
            WHERE IdUtenteBloccato=%s AND DataRevoca IS NULL
            ORDER BY DataInizio DESC LIMIT 1 FOR UPDATE""", (user_id,))
        row = cursor.fetchone()
        if not row:
            return False
        cursor.execute("""UPDATE BLOCCO SET IdModeratoreRevoca=%s, DataRevoca=CURRENT_TIMESTAMP,
                          MotivoRevoca=%s WHERE IdBlocco=%s""",
                       (moderator_id, reason, row["IdBlocco"]))
        cursor.execute("UPDATE UTENTE SET StatoAccount='attivo' WHERE IdUtente=%s", (user_id,))
        cursor.execute("""INSERT INTO EVENTO_LOG
            (IdEsecutore, TipoAzione, Esito, Dettagli, IdUtenteBersaglio, IdBlocco)
            VALUES (%s, 'revoca_blocco', 'successo', %s, %s, %s)""",
            (moderator_id, reason, user_id, row["IdBlocco"]))
    return True


def change_report_state(report_id, user_id, new_state, reason=None):
    transitions = {
        "nuova": {"aperta", "in_valutazione", "chiusa"},
        "aperta": {"in_valutazione", "in_lavorazione", "presa_in_carico", "risolta", "chiusa"},
        "in_valutazione": {"in_lavorazione", "presa_in_carico", "risolta", "chiusa"},
        "in_lavorazione": {"presa_in_carico", "risolta", "chiusa"},
        "presa_in_carico": {"in_lavorazione", "risolta", "chiusa"},
        "risolta": {"aperta", "chiusa"},
        "chiusa": set(),
    }
    with database_cursor(write=True) as cursor:
        cursor.execute("SELECT Stato FROM SEGNALAZIONE WHERE IdSegnalazione=%s FOR UPDATE", (report_id,))
        report = cursor.fetchone()
        if not report:
            return False
        cursor.execute("SELECT 1 FROM STATO_SEGNALAZIONE WHERE Codice=%s", (new_state,))
        if not cursor.fetchone():
            return None
        if new_state not in transitions.get(report["Stato"], set()):
            return None
        cursor.execute("UPDATE SEGNALAZIONE SET Stato=%s WHERE IdSegnalazione=%s", (new_state, report_id))
        cursor.execute("""INSERT INTO STORICO_STATO
            (IdSegnalazione, StatoPrecedente, StatoSuccessivo, IdAutoreModifica, Motivazione)
            VALUES (%s, %s, %s, %s, %s)""", (report_id, report["Stato"], new_state, user_id, reason))
        cursor.execute("""INSERT INTO EVENTO_LOG (IdEsecutore, TipoAzione, Esito, Dettagli, IdSegnalazione)
                          VALUES (%s, 'modifica_stato_segnalazione', 'successo', %s, %s)""",
                       (user_id, f"Stato aggiornato: {report['Stato']} → {new_state}", report_id))
    return True


def attachment_path(attachment_id, viewer_id=None, is_moderator=False):
    with database_cursor() as cursor:
        cursor.execute("""SELECT a.RiferimentoFile FROM ALLEGATO a
            JOIN SEGNALAZIONE s ON s.IdSegnalazione=a.IdSegnalazione
            WHERE a.IdAllegato=%s AND (s.Visibilita='pubblica' OR
               (s.Visibilita <> 'rimossa' AND (s.IdAutore=%s OR %s=1)))""",
            (attachment_id, viewer_id, int(is_moderator)))
        row = cursor.fetchone()
    return row["RiferimentoFile"] if row else None


def user_supports(report_id, user_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT 1 FROM SOSTEGNO WHERE IdUtente=%s AND IdSegnalazione=%s AND DataRitiro IS NULL",
                       (user_id, report_id))
        return cursor.fetchone() is not None


def list_active_users(exclude_user_id=None):
    with database_cursor() as cursor:
        cursor.execute("""SELECT IdUtente AS id, Nome AS nome, Cognome AS cognome
            FROM UTENTE WHERE StatoAccount='attivo' AND (%s IS NULL OR IdUtente <> %s)
            ORDER BY Cognome, Nome LIMIT 200""", (exclude_user_id, exclude_user_id))
        return cursor.fetchall()
