from backend.database import database_cursor, database_enabled, demo_store
from datetime import datetime, timedelta


def create_report_record(data, author, upload):
    initial_state = "aperta" if data["tipo"] == "segnalazione" else "in_valutazione"
    if not database_enabled():
        store = demo_store()
        with store["lock"]:
            report_id = max((row["id"] for row in store["reports"]), default=0) + 1
            report = {
                "id": report_id, "tipo": data["tipo"], "titolo": data["titolo"],
                "descrizione": data["descrizione"], "stato": initial_state,
                "indirizzo": data.get("indirizzo") or "", "autore": f"{author['nome']} {author['cognome']}",
                "data_creazione": data["data_creazione"], "sostegni": 0,
                "autore_id": author["id"],
                "quartiere_id": int(data["quartiere_id"]), "categorie": data["categorie"],
                "allegato": upload["reference"], "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "allegato_id": report_id, "allegato_tipo": upload["mime"],
                "allegato_descrizione": upload["accessible_description"],
            }
            store["reports"].insert(0, report)
            store["history"] = store.setdefault("history", {})
            store["history"][report_id] = [{"stato_precedente": None, "stato_successivo": initial_state}]
        return report

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
            VALUES (%s, NULL, %s, %s, 'Pubblicazione iniziale')""",
            (report_id, initial_state, author["id"]))
        cursor.execute("""INSERT INTO EVENTO_LOG
            (IdEsecutore, TipoAzione, Esito, Dettagli, IdSegnalazione)
            VALUES (%s, 'creazione_segnalazione', 'successo', 'Segnalazione pubblicata con allegato', %s)""",
            (author["id"], report_id))
        # Il passaggio a pubblica avviene solo dopo l'allegato, nella stessa transazione.
        cursor.execute("UPDATE SEGNALAZIONE SET Visibilita='pubblica' WHERE IdSegnalazione=%s", (report_id,))
    return {"id": report_id, "titolo": data["titolo"], "stato": initial_state}


def list_report_records(search="", neighborhood_id=None, category_id=None, state=None, author_id=None, order="recenti"):
    if not database_enabled():
        store = demo_store()
        term = search.casefold()
        rows = [row for row in store["reports"] if row.get("visibilita", "pubblica") == "pubblica"
                and (not term or term in (row["titolo"] + row["descrizione"] + row["indirizzo"]).casefold())
                and (not neighborhood_id or str(row.get("quartiere_id")) == str(neighborhood_id))
                and (not state or row["stato"] == state)
                and (not category_id or str(category_id) in {str(c) for c in row.get("categorie", [])})
                and (not author_id or row.get("autore_id") == author_id)]
        if order == "sostegni":
            rows.sort(key=lambda row: (row.get("sostegni", 0), row["data_creazione"], row["id"]), reverse=True)
        else:
            rows.sort(key=lambda row: (row["data_creazione"], row["id"]), reverse=True)
        return rows[:100]
    filters = ["s.Visibilita = 'pubblica'", "(%s = '' OR s.Titolo LIKE %s OR s.Descrizione LIKE %s OR COALESCE(s.Indirizzo, '') LIKE %s)"]
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
        s.Descrizione AS descrizione, s.Stato AS stato, COALESCE(s.Indirizzo, '') AS indirizzo,
        CONCAT(u.Nome, ' ', u.Cognome) AS autore, s.DataCreazione AS data_creazione,
        s.IdQuartiere AS quartiere_id,
        (SELECT COUNT(*) FROM SOSTEGNO so WHERE so.IdSegnalazione=s.IdSegnalazione AND so.DataRitiro IS NULL) AS sostegni,
        (SELECT a.IdAllegato FROM ALLEGATO a WHERE a.IdSegnalazione=s.IdSegnalazione ORDER BY a.IdAllegato LIMIT 1) AS allegato_id,
        (SELECT a.TipoMedia FROM ALLEGATO a WHERE a.IdSegnalazione=s.IdSegnalazione ORDER BY a.IdAllegato LIMIT 1) AS allegato_tipo,
        (SELECT a.DescrizioneAccessibile FROM ALLEGATO a WHERE a.IdSegnalazione=s.IdSegnalazione ORDER BY a.IdAllegato LIMIT 1) AS allegato_descrizione
        FROM SEGNALAZIONE s JOIN UTENTE u ON u.IdUtente=s.IdAutore
        WHERE """ + " AND ".join(filters) + (
            " ORDER BY sostegni DESC, s.DataCreazione DESC, s.IdSegnalazione DESC LIMIT 100"
            if order == "sostegni" else
            " ORDER BY s.DataCreazione DESC, s.IdSegnalazione DESC LIMIT 100"
        )
    with database_cursor() as cursor:
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
    for row in rows:
        row["data_creazione"] = row["data_creazione"].isoformat(timespec="seconds")
    return rows


def get_report_record(report_id):
    if not database_enabled():
        return next((dict(row) for row in demo_store()["reports"] if row["id"] == report_id), None)
    with database_cursor() as cursor:
        cursor.execute("""SELECT s.IdSegnalazione AS id, s.IdQuartiere AS quartiere_id,
            s.Tipo AS tipo, s.Titolo AS titolo, s.Descrizione AS descrizione, s.Stato AS stato,
            s.Visibilita AS visibilita, s.DataCreazione AS data_creazione, s.Indirizzo AS indirizzo,
            CONCAT(u.Nome, ' ', u.Cognome) AS autore
            FROM SEGNALAZIONE s JOIN UTENTE u ON u.IdUtente=s.IdAutore
            WHERE s.IdSegnalazione=%s""", (report_id,))
        return cursor.fetchone()


def report_comments(report_id):
    if not database_enabled():
        return [comment for comment in demo_store().get("comments", {}).get(report_id, [])
                if comment.get("visibilita", "pubblica") == "pubblica"]
    with database_cursor() as cursor:
        cursor.execute("""SELECT c.IdCommento AS id, c.Testo AS testo,
            c.DataPubblicazione AS data, CONCAT(u.Nome, ' ', u.Cognome) AS autore
            FROM COMMENTO c JOIN UTENTE u ON u.IdUtente=c.IdAutore
            WHERE c.IdSegnalazione=%s AND c.Visibilita='pubblica' ORDER BY c.DataPubblicazione""", (report_id,))
        return cursor.fetchall()


def add_comment(report_id, user_id, text):
    if not database_enabled():
        store = demo_store()
        comment = {"id": len(store["comments"].get(report_id, [])) + 1, "testo": text}
        store["comments"].setdefault(report_id, []).append(comment)
        return comment
    with database_cursor(write=True) as cursor:
        cursor.execute("INSERT INTO COMMENTO (IdAutore, IdSegnalazione, Testo, Visibilita) VALUES (%s, %s, %s, 'pubblica')",
                       (user_id, report_id, text))
        comment_id = cursor.lastrowid
        cursor.execute("""INSERT INTO EVENTO_LOG
            (IdEsecutore, TipoAzione, Esito, Dettagli, IdSegnalazione, IdCommento)
            VALUES (%s, 'pubblicazione_commento', 'successo', 'Commento pubblicato', %s, %s)""",
            (user_id, report_id, comment_id))
        return {"id": comment_id, "testo": text}


def set_support(report_id, user_id, active):
    if not database_enabled():
        store = demo_store()
        key = (int(user_id), int(report_id))
        previously_active = key in store["supports"]
        if previously_active == active:
            return False
        if active:
            store["supports"].add(key)
        else:
            store["supports"].discard(key)
        report = next((row for row in store["reports"] if row["id"] == report_id), None)
        if report:
            report["sostegni"] = max(0, report.get("sostegni", 0) + (1 if active else -1))
        store.setdefault("events", []).append({"azione": "espressione_sostegno" if active else "ritiro_sostegno",
                                                       "utente_id": user_id, "segnalazione_id": report_id})
        return True
    with database_cursor(write=True) as cursor:
        cursor.execute("SELECT IdSostegno, DataRitiro FROM SOSTEGNO WHERE IdUtente=%s AND IdSegnalazione=%s FOR UPDATE",
                       (user_id, report_id))
        previous = cursor.fetchone()
        if (previous is not None and previous["DataRitiro"] is None) == active:
            return False
        if active:
            if previous:
                cursor.execute("""UPDATE SOSTEGNO SET DataRitiro=NULL, DataEspressione=CURRENT_TIMESTAMP
                    WHERE IdSostegno=%s""", (previous["IdSostegno"],))
            else:
                cursor.execute("INSERT INTO SOSTEGNO (IdUtente, IdSegnalazione) VALUES (%s, %s)", (user_id, report_id))
            action = "espressione_sostegno"
        else:
            cursor.execute("UPDATE SOSTEGNO SET DataRitiro=CURRENT_TIMESTAMP WHERE IdUtente=%s AND IdSegnalazione=%s AND DataRitiro IS NULL",
                           (user_id, report_id))
            action = "ritiro_sostegno"
        support = previous
        if support is None:
            cursor.execute("SELECT IdSostegno FROM SOSTEGNO WHERE IdUtente=%s AND IdSegnalazione=%s", (user_id, report_id))
            support = cursor.fetchone()
        if support:
            cursor.execute("""INSERT INTO EVENTO_LOG
                (IdEsecutore, TipoAzione, Esito, Dettagli, IdSegnalazione, IdSostegno)
                VALUES (%s, %s, 'successo', %s, %s, %s)""",
                (user_id, action, action.replace("_", " "), report_id, support["IdSostegno"]))
    return True


def moderate_report(report_id, moderator_id, visibility):
    if visibility not in {"nascosta", "rimossa", "pubblica"}:
        return False
    if not database_enabled():
        report = next((row for row in demo_store()["reports"] if row["id"] == report_id), None)
        if not report:
            return None
        report["visibilita"] = visibility
        demo_store().setdefault("events", []).append({"azione": "moderazione_segnalazione", "id": report_id})
        return True
    with database_cursor(write=True) as cursor:
        cursor.execute("UPDATE SEGNALAZIONE SET Visibilita=%s WHERE IdSegnalazione=%s",
                       (visibility, report_id))
        if cursor.rowcount == 0:
            return None
        cursor.execute("""INSERT INTO EVENTO_LOG
            (IdEsecutore, TipoAzione, Esito, Dettagli, IdSegnalazione)
            VALUES (%s, 'moderazione_segnalazione', 'successo', %s, %s)""",
            (moderator_id, f"Visibilità impostata a {visibility}", report_id))
    return True


def moderate_comment(comment_id, moderator_id):
    if not database_enabled():
        for comments in demo_store().get("comments", {}).values():
            comment = next((row for row in comments if row["id"] == comment_id), None)
            if comment:
                comment["visibilita"] = "rimossa"
                demo_store().setdefault("events", []).append({"azione": "moderazione_commento", "id": comment_id})
                return True
        return False
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
    if not database_enabled():
        user = demo_store()["users"].get(user_id)
        if not user or user["stato_account"] != "attivo":
            return False
        user["stato_account"] = "bloccato"
        demo_store().setdefault("events", []).append({"azione": "blocco_utente", "id": user_id, "motivazione": reason})
        return True
    end_date = datetime.now() + timedelta(days=days) if days else None
    with database_cursor(write=True) as cursor:
        cursor.execute("SELECT IdUtente FROM UTENTE WHERE IdUtente=%s AND StatoAccount='attivo' FOR UPDATE", (user_id,))
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
    if not database_enabled():
        user = demo_store()["users"].get(user_id)
        if not user or user["stato_account"] != "bloccato":
            return False
        user["stato_account"] = "attivo"
        demo_store().setdefault("events", []).append({"azione": "revoca_blocco", "id": user_id, "motivazione": reason})
        return True
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
    if not database_enabled():
        report = next((row for row in demo_store()["reports"] if row["id"] == report_id), None)
        if not report:
            return False
        if new_state not in transitions:
            return None
        previous = report["stato"]
        if new_state not in transitions.get(previous, set()):
            return None
        report["stato"] = new_state
        demo_store().setdefault("history", {}).setdefault(report_id, []).append({
            "stato_precedente": previous, "stato_successivo": new_state, "motivazione": reason,
        })
        return True
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


def attachment_path(attachment_id):
    if not database_enabled():
        row = next((report for report in demo_store()["reports"]
                    if report.get("allegato_id") == attachment_id), None)
        return row.get("allegato") if row else None
    with database_cursor() as cursor:
        cursor.execute("""SELECT a.RiferimentoFile FROM ALLEGATO a
            JOIN SEGNALAZIONE s ON s.IdSegnalazione=a.IdSegnalazione
            WHERE a.IdAllegato=%s AND s.Visibilita='pubblica'""", (attachment_id,))
        row = cursor.fetchone()
    return row["RiferimentoFile"] if row else None


def user_supports(report_id, user_id):
    if not database_enabled():
        return (int(user_id), int(report_id)) in demo_store()["supports"]
    with database_cursor() as cursor:
        cursor.execute("SELECT 1 FROM SOSTEGNO WHERE IdUtente=%s AND IdSegnalazione=%s AND DataRitiro IS NULL",
                       (user_id, report_id))
        return cursor.fetchone() is not None


def list_active_users(exclude_user_id=None):
    if not database_enabled():
        return [{"id": user["id"], "nome": user["nome"], "cognome": user["cognome"]}
                for user in demo_store()["users"].values()
                if user["stato_account"] == "attivo" and user["id"] != exclude_user_id]
    with database_cursor() as cursor:
        cursor.execute("""SELECT IdUtente AS id, Nome AS nome, Cognome AS cognome
            FROM UTENTE WHERE StatoAccount='attivo' AND (%s IS NULL OR IdUtente <> %s)
            ORDER BY Cognome, Nome LIMIT 200""", (exclude_user_id, exclude_user_id))
        return cursor.fetchall()
