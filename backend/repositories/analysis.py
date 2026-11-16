"""Risultati delle analisi IA (tabella ANALISI_IA) e revisione da parte del comitato."""

import json


def save_analyses(cursor, report_id, attachment_id, analyses):
    """Scrive i risultati nella stessa transazione della segnalazione."""
    for item in analyses:
        cursor.execute("""INSERT INTO ANALISI_IA
            (IdSegnalazione, IdAllegato, TipoAnalisi, Modello, Esito, Confidenza, Risultato, StatoRevisione)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (report_id, attachment_id if item.get("allegato") else None, item["tipo"], item["modello"][:120],
             item["esito"], item.get("confidenza"), json.dumps(item.get("risultato") or {}, ensure_ascii=False),
             "da_revisionare" if item.get("revisione") else "non_necessaria"))


def review_analyses(cursor, report_id, moderator_id, visibility):
    """Chiude le analisi in attesa: se il moderatore pubblica, il sospetto dell'IA era infondato."""
    cursor.execute("""UPDATE ANALISI_IA SET StatoRevisione=%s, IdModeratoreRevisione=%s,
        DataRevisione=CURRENT_TIMESTAMP WHERE IdSegnalazione=%s AND StatoRevisione='da_revisionare'""",
        ("respinta" if visibility == "pubblica" else "confermata", moderator_id, report_id))


def parse_analyses(raw):
    """Converte l'array JSON prodotto dalla sub-select SQL (o None) in una lista di dict."""
    if not raw:
        return []
    return json.loads(raw) if isinstance(raw, (str, bytes)) else list(raw)


ANALYSIS_JSON_SQL = """(SELECT JSON_ARRAYAGG(JSON_OBJECT('tipo', a.TipoAnalisi, 'esito', a.Esito,
            'confidenza', a.Confidenza, 'revisione', a.StatoRevisione,
            'motivo', JSON_UNQUOTE(JSON_EXTRACT(a.Risultato, '$.motivo'))))
         FROM ANALISI_IA a WHERE a.IdSegnalazione=s.IdSegnalazione) AS analisi_json"""
