"""Operazioni transazionali per merge e documentazione degli interventi."""
from backend.database import database_cursor
from backend.repositories.reports import write_attachment_content


def merge_reports(source_id, target_id, moderator_id, reason):
    if source_id == target_id:
        raise ValueError("La segnalazione principale deve essere diversa.")
    with database_cursor(write=True) as cursor:
        # Lock in ordine stabile; tutte le interazioni bloccano la stessa riga.
        rows = {}
        for report_id in sorted([source_id, target_id]):
            cursor.execute("SELECT IdSegnalazione, Tipo, Visibilita, duplicate_of_id FROM SEGNALAZIONE WHERE IdSegnalazione=%s FOR UPDATE", (report_id,))
            rows[report_id] = cursor.fetchone()
        source, target = rows[source_id], rows[target_id]
        if not source or not target:
            raise ValueError("Contenuto non trovato.")
        if source['duplicate_of_id'] or target['duplicate_of_id']:
            raise ValueError("Un contenuto è già un duplicato. Scegli la segnalazione principale.")
        if source['Tipo'] != target['Tipo'] or any(row['Visibilita'] != 'pubblica' for row in (source, target)):
            raise ValueError("Unisci solo contenuti pubblici dello stesso tipo.")
        cursor.execute("SELECT IdSegnalazione FROM SEGNALAZIONE WHERE duplicate_of_id=%s LIMIT 1", (source_id,))
        if cursor.fetchone():
            raise ValueError("Questo contenuto raccoglie già duplicati: mantienilo come principale.")
        # Copia solo sostegni attivi; il vincolo unico impedisce il doppio voto.
        cursor.execute("""INSERT INTO SOSTEGNO (IdUtente, IdSegnalazione, DataEspressione)
            SELECT IdUtente, %s, DataEspressione FROM SOSTEGNO
            WHERE IdSegnalazione=%s AND DataRitiro IS NULL
            ON DUPLICATE KEY UPDATE DataRitiro=NULL""", (target_id, source_id))
        # Mantiene le righe originali e i riferimenti dei log storici.
        cursor.execute("UPDATE SOSTEGNO SET DataRitiro=CURRENT_TIMESTAMP WHERE IdSegnalazione=%s AND DataRitiro IS NULL", (source_id,))
        cursor.execute("UPDATE COMMENTO SET IdSegnalazione=%s WHERE IdSegnalazione=%s", (target_id, source_id))
        cursor.execute("UPDATE SEGNALAZIONE SET duplicate_of_id=%s WHERE IdSegnalazione=%s", (target_id, source_id))
        cursor.execute("""INSERT INTO EVENTO_LOG (IdEsecutore, TipoAzione, Esito, Dettagli, IdSegnalazione)
            VALUES (%s,'unione_duplicato','successo',%s,%s)""",
            (moderator_id, f"Duplicato di #{target_id}. {reason}", source_id))
    return target_id


def save_resolution(report_id, moderator_id, text, upload):
    with database_cursor(write=True) as cursor:
        cursor.execute("SELECT Tipo, Visibilita, duplicate_of_id FROM SEGNALAZIONE WHERE IdSegnalazione=%s FOR UPDATE", (report_id,))
        row = cursor.fetchone()
        if not row or row['Tipo'] != 'segnalazione' or row['Visibilita'] != 'pubblica' or row['duplicate_of_id']:
            raise ValueError("Scegli una segnalazione pubblica principale.")
        cursor.execute("""INSERT INTO ALLEGATO
            (IdSegnalazione, IdAutore, TipoMedia, RiferimentoFile, NomeOriginale,
             DimensioneByte, HashSHA256, DescrizioneAccessibile, Ruolo)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'dopo')""",
            (report_id, moderator_id, upload['mime'], upload['reference'], upload['original_name'],
             upload['size'], upload['sha256'], upload['accessible_description']))
        write_attachment_content(cursor, cursor.lastrowid, upload['content'])
        cursor.execute("UPDATE DETTAGLIO_SEGNALAZIONE SET Risoluzione=%s WHERE IdSegnalazione=%s", (text, report_id))
        cursor.execute("""INSERT INTO EVENTO_LOG (IdEsecutore, TipoAzione, Esito, Dettagli, IdSegnalazione)
            VALUES (%s,'documentazione_intervento','successo',%s,%s)""", (moderator_id, text, report_id))
