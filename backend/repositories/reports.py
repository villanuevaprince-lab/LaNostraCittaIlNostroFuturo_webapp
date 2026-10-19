import hashlib
import json

from backend.database import database_cursor
from datetime import datetime, timedelta

MEDIA_CHUNK_BYTES = 256 * 1024


def write_attachment_content(cursor, attachment_id, content):
    """Chunk piccoli evitano query oltre il max_allowed_packet MySQL."""
    for number, start in enumerate(range(0, len(content), MEDIA_CHUNK_BYTES)):
        cursor.execute("""INSERT INTO ALLEGATO_CONTENUTO (IdAllegato, Numero, Dati)
            VALUES (%s, %s, %s)""", (attachment_id, number, content[start:start + MEDIA_CHUNK_BYTES]))


STATE_TRANSITIONS = {
    "nuova": {"aperta", "in_valutazione", "chiusa"},
    "aperta": {"in_valutazione", "in_lavorazione", "presa_in_carico", "risolta", "chiusa"},
    "in_valutazione": {"in_lavorazione", "presa_in_carico", "risolta", "chiusa"},
    "in_lavorazione": {"presa_in_carico", "risolta", "chiusa"},
    "presa_in_carico": {"in_lavorazione", "risolta", "chiusa"},
    "risolta": {"aperta", "chiusa"},
    "chiusa": set(),
}


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
        write_attachment_content(cursor, cursor.lastrowid, upload["content"])
        for category_id in data["categorie"]:
            cursor.execute("""INSERT INTO SEGNALAZIONE_CATEGORIA
                (IdSegnalazione, IdCategoria, Origine) VALUES (%s, %s, 'utente')""",
                (report_id, category_id))
        # Il trigger di pubblicazione richiede che l'allegato sia già presente.
        cursor.execute("UPDATE SEGNALAZIONE SET Visibilita='pubblica' WHERE IdSegnalazione=%s", (report_id,))
        cursor.execute("""INSERT INTO STORICO_STATO
            (IdSegnalazione, StatoPrecedente, StatoSuccessivo, IdAutoreModifica, Motivazione)
            VALUES (%s, NULL, %s, %s, 'Pubblicazione del contenuto')""",
            (report_id, initial_state, author["id"]))
        cursor.execute("""INSERT INTO EVENTO_LOG
            (IdEsecutore, TipoAzione, Esito, Dettagli, IdSegnalazione)
            VALUES (%s, 'creazione_segnalazione', 'successo', 'Contenuto pubblicato con allegato', %s)""",
            (author["id"], report_id))
    return {"id": report_id, "titolo": data["titolo"], "stato": initial_state,
            "visibilita": "pubblica"}


def list_report_records(search="", neighborhood_id=None, category_ids=None, state=None,
                        author_id=None, viewer_id=None, order="recenti",
                        visibility_filter=None, cursor_id=None, limit=100):
    filters = ["s.Visibilita = 'pubblica'" if author_id is None else "s.Visibilita IN ('pubblica','bozza','nascosta','rimossa')",
               "(%s = '' OR s.Titolo LIKE %s OR s.Descrizione LIKE %s OR COALESCE(s.Indirizzo, '') LIKE %s)"]
    params = [search, f"%{search}%", f"%{search}%", f"%{search}%"]
    if neighborhood_id:
        filters.append("s.IdQuartiere = %s")
        params.append(neighborhood_id)
    if state:
        filters.append("s.Stato = %s")
        params.append(state)
    if category_ids:
        placeholders = ",".join(["%s"] * len(category_ids))
        filters.append(f"EXISTS (SELECT 1 FROM SEGNALAZIONE_CATEGORIA sc WHERE sc.IdSegnalazione = s.IdSegnalazione AND sc.IdCategoria IN ({placeholders}))")
        params.extend(category_ids)
    if author_id:
        filters.append("s.IdAutore = %s")
        params.append(author_id)
        if visibility_filter in {"pubblica", "bozza", "nascosta"}:
            filters.append("s.Visibilita = %s")
            params.append(visibility_filter)
        elif visibility_filter in {"rimossa_moderazione", "rimossa_autore"}:
            filters.append("s.Visibilita = 'rimossa'")
            withdrawal = "EXISTS" if visibility_filter == "rimossa_autore" else "NOT EXISTS"
            filters.append(f"{withdrawal} (SELECT 1 FROM EVENTO_LOG r WHERE r.IdSegnalazione=s.IdSegnalazione AND r.TipoAzione='ritiro_segnalazione')")
        if cursor_id:
            filters.append("s.IdSegnalazione < %s")
            params.append(cursor_id)
    query = """SELECT s.IdSegnalazione AS id, s.Tipo AS tipo, s.Titolo AS titolo,
        s.Descrizione AS descrizione, s.Stato AS stato, s.Visibilita AS visibilita,
        COALESCE(s.Indirizzo, '') AS indirizzo,
        CONCAT(u.Nome, ' ', u.Cognome) AS autore, s.DataCreazione AS data_creazione,
        s.IdQuartiere AS quartiere_id, q.Nome AS quartiere,
        (SELECT COUNT(*) FROM EVENTO_LOG e WHERE e.IdSegnalazione=s.IdSegnalazione
         AND e.TipoAzione='ritiro_segnalazione') AS ritirata_autore,
        (SELECT JSON_ARRAYAGG(JSON_OBJECT('id', cat.IdCategoria, 'nome', cat.Nome))
         FROM SEGNALAZIONE_CATEGORIA sc JOIN CATEGORIA cat ON cat.IdCategoria=sc.IdCategoria
         WHERE sc.IdSegnalazione=s.IdSegnalazione) AS categorie_json,
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
            " ORDER BY s.IdSegnalazione DESC LIMIT %s" if author_id and visibility_filter is not None else
            " ORDER BY sostegni DESC, s.DataCreazione DESC, s.IdSegnalazione DESC LIMIT 100"
            if order == "sostegni" else
            " ORDER BY s.DataCreazione DESC, s.IdSegnalazione DESC LIMIT 100")
    if author_id and visibility_filter is not None:
        params.append(limit)
    with database_cursor() as cursor:
        cursor.execute(query, (viewer_id, viewer_id, *params))
        rows = cursor.fetchall()
    for row in rows:
        row["data_creazione"] = row["data_creazione"].isoformat(timespec="seconds")
        raw = row.pop("categorie_json", None)
        row["categorie"] = sorted(json.loads(raw), key=lambda category: category["nome"]) if raw else []
    return rows


def get_report_record(report_id):
    with database_cursor() as cursor:
        cursor.execute("""SELECT s.IdSegnalazione AS id, s.IdQuartiere AS quartiere_id,
            s.Tipo AS tipo, s.Titolo AS titolo, s.Descrizione AS descrizione, s.Stato AS stato,
            s.Visibilita AS visibilita, s.DataCreazione AS data_creazione, s.Indirizzo AS indirizzo,
            s.Latitudine AS latitude, s.Longitudine AS longitude,
            s.IdAutore AS autore_id, q.Nome AS quartiere,
            CONCAT(u.Nome, ' ', u.Cognome) AS autore,
            (SELECT JSON_ARRAYAGG(JSON_OBJECT('id', c.IdCategoria, 'nome', c.Nome))
             FROM SEGNALAZIONE_CATEGORIA sc JOIN CATEGORIA c ON c.IdCategoria=sc.IdCategoria
             WHERE sc.IdSegnalazione=s.IdSegnalazione) AS categorie_json,
            (SELECT a.IdAllegato FROM ALLEGATO a WHERE a.IdSegnalazione=s.IdSegnalazione
             ORDER BY a.IdAllegato LIMIT 1) AS allegato_id,
            (SELECT a.TipoMedia FROM ALLEGATO a WHERE a.IdSegnalazione=s.IdSegnalazione
             ORDER BY a.IdAllegato LIMIT 1) AS allegato_tipo,
            (SELECT COUNT(*) FROM SOSTEGNO so WHERE so.IdSegnalazione=s.IdSegnalazione
             AND so.DataRitiro IS NULL) AS sostegni
            FROM SEGNALAZIONE s JOIN UTENTE u ON u.IdUtente=s.IdAutore
            LEFT JOIN QUARTIERE q ON q.IdQuartiere=s.IdQuartiere
            WHERE s.IdSegnalazione=%s""", (report_id,))
        row = cursor.fetchone()
    if row:
        raw = row.pop("categorie_json", None)
        row["categorie"] = sorted(json.loads(raw), key=lambda category: category["nome"]) if raw else []
    return row


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
            elif row["Visibilita"] == visibility:
                unchanged += 1
            elif row["Visibilita"] == "rimossa" and visibility != "pubblica":
                unchanged += 1
            else:
                if row["Visibilita"] == "rimossa":
                    cursor.execute("""SELECT 1 FROM EVENTO_LOG WHERE IdSegnalazione=%s
                        AND TipoAzione='ritiro_segnalazione' LIMIT 1""", (report_id,))
                    if cursor.fetchone():
                        unchanged += 1  # il ritiro dell'autore resta definitivo
                        continue
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


def list_moderation_reports(cursor_id=None, visibility="pubblica", limit=25):
    # La coda è organizzata per stato operativo. "rimossa" resta una vista
    # speciale che raccoglie tutti i contenuti eliminati dai moderatori/autori.
    if visibility == "rimossa":
        visibility_clause = "s.Visibilita='rimossa'"
        visibility_params = []
    elif visibility in STATE_TRANSITIONS:
        visibility_clause = "s.Visibilita <> 'rimossa' AND s.Stato=%s"
        visibility_params = [visibility]
    else:
        # Compatibilità con eventuali client precedenti alla vista per stato.
        visibility_clause = "s.Visibilita=%s"
        visibility_params = [visibility]
    with database_cursor() as cursor:
        query = """SELECT s.IdSegnalazione AS id, s.Titolo AS titolo, s.Tipo AS tipo,
            s.Stato AS stato, s.Visibilita AS visibilita, s.DataCreazione AS data_creazione,
            CONCAT(u.Nome, ' ', u.Cognome) AS autore, u.IdUtente AS autore_id,
            (SELECT COUNT(*) FROM EVENTO_LOG e WHERE e.IdSegnalazione=s.IdSegnalazione
             AND e.TipoAzione='ritiro_segnalazione') AS ritirata_autore
            FROM SEGNALAZIONE s JOIN UTENTE u ON u.IdUtente=s.IdAutore
            WHERE """ + visibility_clause + """ AND (%s IS NULL OR s.IdSegnalazione < %s)
            ORDER BY s.IdSegnalazione DESC LIMIT %s"""
        cursor.execute(query, (*visibility_params, cursor_id, cursor_id, limit + 1))
        rows = cursor.fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    for row in rows:
        row["data_creazione"] = row["data_creazione"].isoformat(timespec="seconds")
    return {"items": rows, "next_cursor": rows[-1]["id"] if more and rows else None}


def list_moderation_users(cursor_id=None, limit=25, search=""):
    # Prefisso, non wildcard arbitraria: la ricerca rimane utile su liste grandi.
    escaped = search.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
    with database_cursor() as cursor:
        cursor.execute("""SELECT u.IdUtente AS id, u.Nome AS nome, u.Cognome AS cognome,
            u.Email AS email, u.StatoAccount AS stato,
            b.DataFinePrevista AS blocco_fine,
            CASE WHEN u.StatoAccount='attivo' THEN 'attivo'
                 WHEN b.IdBlocco IS NULL THEN 'bloccato_senza_dettagli'
                 WHEN b.DataFinePrevista IS NULL THEN 'permanente'
                 WHEN b.DataFinePrevista <= CURRENT_TIMESTAMP THEN 'scaduto'
                 ELSE 'temporaneo' END AS tipo_blocco
            FROM UTENTE u LEFT JOIN MODERATORE m ON m.IdUtente=u.IdUtente
            LEFT JOIN BLOCCO b ON b.IdBlocco=(
                SELECT latest.IdBlocco FROM BLOCCO latest
                WHERE latest.IdUtenteBloccato=u.IdUtente AND latest.DataRevoca IS NULL
                ORDER BY latest.IdBlocco DESC LIMIT 1)
            WHERE u.StatoAccount IN ('attivo', 'bloccato') AND m.IdUtente IS NULL
              AND (%s IS NULL OR u.IdUtente < %s)
              AND (%s = '' OR u.Email LIKE %s ESCAPE '!' OR u.Nome LIKE %s ESCAPE '!'
                   OR u.Cognome LIKE %s ESCAPE '!' OR u.IdUtente=%s)
            ORDER BY u.IdUtente DESC LIMIT %s""",
            (cursor_id, cursor_id, search, escaped, escaped, escaped,
             int(search) if search.isdigit() else 0, limit + 1))
        rows = cursor.fetchall()
    more = len(rows) > limit
    for row in rows[:limit]:
        if row["blocco_fine"] is not None:
            row["blocco_fine"] = row["blocco_fine"].isoformat(timespec="seconds")
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


def permanently_ban_user(user_id, moderator_id, reason):
    """Nessuna DELETE: conserva FK e audit e revoca l'accesso senza scadenza."""
    if user_id == moderator_id:
        return False
    with database_cursor(write=True) as cursor:
        cursor.execute("""SELECT u.StatoAccount FROM UTENTE u
            WHERE u.IdUtente=%s AND u.StatoAccount IN ('attivo', 'bloccato')
            AND NOT EXISTS (SELECT 1 FROM MODERATORE WHERE IdUtente=u.IdUtente)
            FOR UPDATE""", (user_id,))
        user = cursor.fetchone()
        if not user:
            return False
        cursor.execute("""SELECT IdBlocco, DataFinePrevista FROM BLOCCO
            WHERE IdUtenteBloccato=%s AND DataRevoca IS NULL
            ORDER BY IdBlocco DESC LIMIT 1 FOR UPDATE""", (user_id,))
        previous = cursor.fetchone()
        if previous and previous["DataFinePrevista"] is None:
            return False
        if previous:
            # Conserva durata, autore e motivo del blocco precedente nello storico.
            cursor.execute("""UPDATE BLOCCO SET IdModeratoreRevoca=%s,
                DataRevoca=CURRENT_TIMESTAMP, MotivoRevoca='Sostituito da ban permanente'
                WHERE IdBlocco=%s""", (moderator_id, previous["IdBlocco"]))
        cursor.execute("""INSERT INTO BLOCCO
            (IdUtenteBloccato, IdModeratore, Motivazione, DataFinePrevista)
            VALUES (%s, %s, %s, NULL)""", (user_id, moderator_id, reason))
        block_id = cursor.lastrowid
        cursor.execute("UPDATE UTENTE SET StatoAccount='bloccato' WHERE IdUtente=%s", (user_id,))
        cursor.execute("""INSERT INTO EVENTO_LOG
            (IdEsecutore, TipoAzione, Esito, Dettagli, IdUtenteBersaglio, IdBlocco)
            VALUES (%s, 'ban_permanente', 'successo', %s, %s, %s)""",
            (moderator_id, reason, user_id, block_id))
    return True


def unblock_user(user_id, moderator_id, reason):
    with database_cursor(write=True) as cursor:
        cursor.execute("SELECT IdUtente FROM UTENTE WHERE IdUtente=%s FOR UPDATE", (user_id,))
        if not cursor.fetchone():
            return False
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
    with database_cursor(write=True) as cursor:
        cursor.execute("SELECT Stato FROM SEGNALAZIONE WHERE IdSegnalazione=%s FOR UPDATE", (report_id,))
        report = cursor.fetchone()
        if not report:
            return False
        cursor.execute("SELECT 1 FROM STATO_SEGNALAZIONE WHERE Codice=%s", (new_state,))
        if not cursor.fetchone():
            return None
        if new_state not in STATE_TRANSITIONS.get(report["Stato"], set()):
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


def attachment_content(attachment_id):
    """Legge un allegato dal DB, senza dipendere dal disco di questo computer."""
    with database_cursor() as cursor:
        cursor.execute("""SELECT a.TipoMedia AS mime, a.DimensioneByte AS size,
            a.HashSHA256 AS sha256, c.Dati AS data
            FROM ALLEGATO a JOIN ALLEGATO_CONTENUTO c ON c.IdAllegato=a.IdAllegato
            WHERE a.IdAllegato=%s ORDER BY c.Numero""", (attachment_id,))
        parts = cursor.fetchall()
    if not parts:
        return None
    content = b"".join(bytes(part["data"]) for part in parts)
    if len(content) != parts[0]["size"] or hashlib.sha256(content).hexdigest() != parts[0]["sha256"]:
        raise ValueError("Allegato corrotto")
    return content, parts[0]["mime"]


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
