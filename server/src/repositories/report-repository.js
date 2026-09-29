function normalizeJson(value) {
  if (value === null || value === undefined) return [];
  if (Array.isArray(value)) return value;
  try { return JSON.parse(value); } catch { return []; }
}

function normalizeReport(row) {
  if (!row) return null;
  return {
    ...row,
    numeroSostegni: Number(row.numeroSostegni ?? 0),
    sostenutaDaMe: Boolean(row.sostenutaDaMe),
    categorie: normalizeJson(row.categorie)
  };
}

const reportSelect = `
  SELECT
    s.IdSegnalazione AS id,
    s.IdAutore AS idAutore,
    s.IdQuartiere AS idQuartiere,
    s.Tipo AS tipo,
    s.Titolo AS titolo,
    s.Descrizione AS descrizione,
    s.DataCreazione AS dataCreazione,
    s.DataAggiornamento AS dataAggiornamento,
    s.Stato AS stato,
    s.Visibilita AS visibilita,
    s.Latitudine AS latitudine,
    s.Longitudine AS longitudine,
    s.Indirizzo AS indirizzo,
    CONCAT(u.Nome, ' ', LEFT(u.Cognome, 1), '.') AS autore,
    q.Nome AS quartiere,
    (SELECT COUNT(*) FROM SOSTEGNO so
      WHERE so.IdSegnalazione = s.IdSegnalazione AND so.DataRitiro IS NULL) AS numeroSostegni,
    (SELECT COUNT(*) > 0 FROM SOSTEGNO mine
      WHERE mine.IdSegnalazione = s.IdSegnalazione
        AND mine.IdUtente = ? AND mine.DataRitiro IS NULL) AS sostenutaDaMe,
    (SELECT JSON_ARRAYAGG(JSON_OBJECT('id', c.IdCategoria, 'nome', c.Nome, 'colore', c.Colore))
      FROM SEGNALAZIONE_CATEGORIA sc
      JOIN CATEGORIA c ON c.IdCategoria = sc.IdCategoria
      WHERE sc.IdSegnalazione = s.IdSegnalazione) AS categorie,
    (SELECT a.RiferimentoFile FROM ALLEGATO a
      WHERE a.IdSegnalazione = s.IdSegnalazione
      ORDER BY a.IdAllegato LIMIT 1) AS anteprima,
    (SELECT a.TipoMedia FROM ALLEGATO a
      WHERE a.IdSegnalazione = s.IdSegnalazione
      ORDER BY a.IdAllegato LIMIT 1) AS anteprimaTipo,
    (SELECT a.DescrizioneAccessibile FROM ALLEGATO a
      WHERE a.IdSegnalazione = s.IdSegnalazione
      ORDER BY a.IdAllegato LIMIT 1) AS anteprimaAlt
  FROM SEGNALAZIONE s
  JOIN UTENTE u ON u.IdUtente = s.IdAutore
  LEFT JOIN QUARTIERE q ON q.IdQuartiere = s.IdQuartiere`;

export async function listReports(connection, filters, viewerId = 0) {
  const conditions = [`s.Visibilita = 'pubblica'`];
  const values = [viewerId || 0];

  if (filters.q) {
    conditions.push('(s.Titolo LIKE ? OR s.Descrizione LIKE ? OR s.Indirizzo LIKE ?)');
    const like = `%${filters.q}%`;
    values.push(like, like, like);
  }
  if (filters.tipo) {
    conditions.push('s.Tipo = ?');
    values.push(filters.tipo);
  }
  if (filters.stato) {
    conditions.push('s.Stato = ?');
    values.push(filters.stato);
  }
  if (filters.idQuartiere) {
    conditions.push('s.IdQuartiere = ?');
    values.push(filters.idQuartiere);
  }
  if (filters.idCategoria) {
    conditions.push(`EXISTS (
      SELECT 1 FROM SEGNALAZIONE_CATEGORIA selected
      WHERE selected.IdSegnalazione = s.IdSegnalazione AND selected.IdCategoria = ?
    )`);
    values.push(filters.idCategoria);
  }

  const where = conditions.join(' AND ');
  const offset = (filters.pagina - 1) * filters.limite;
  const order = filters.ordine === 'sostenute'
    ? 'numeroSostegni DESC, s.DataCreazione DESC'
    : 's.DataCreazione DESC';

  const [rows] = await connection.execute(
    `${reportSelect} WHERE ${where} ORDER BY ${order} LIMIT ? OFFSET ?`,
    [...values, filters.limite, offset]
  );
  const [countRows] = await connection.execute(
    `SELECT COUNT(*) AS totale FROM SEGNALAZIONE s WHERE ${where}`,
    values.slice(1)
  );

  return {
    items: rows.map(normalizeReport),
    pagina: filters.pagina,
    limite: filters.limite,
    totale: Number(countRows[0].totale),
    pagine: Math.ceil(Number(countRows[0].totale) / filters.limite)
  };
}

export async function getReport(connection, reportId, viewerId = 0) {
  const [rows] = await connection.execute(
    `${reportSelect} WHERE s.IdSegnalazione = ? LIMIT 1`,
    [viewerId || 0, reportId]
  );
  if (!rows.length) return null;

  const [attachments] = await connection.execute(
    `SELECT
       IdAllegato AS id, TipoMedia AS tipo, RiferimentoFile AS url,
       NomeOriginale AS nomeOriginale, DimensioneByte AS dimensione,
       DescrizioneAccessibile AS descrizione, DataCaricamento AS dataCaricamento
     FROM ALLEGATO WHERE IdSegnalazione = ? ORDER BY IdAllegato`,
    [reportId]
  );
  const [comments] = await connection.execute(
    `SELECT
       c.IdCommento AS id, c.IdAutore AS idAutore, c.Testo AS testo,
       c.DataPubblicazione AS dataPubblicazione,
       CONCAT(u.Nome, ' ', LEFT(u.Cognome, 1), '.') AS autore
     FROM COMMENTO c
     JOIN UTENTE u ON u.IdUtente = c.IdAutore
     WHERE c.IdSegnalazione = ? AND c.Visibilita = 'pubblica'
     ORDER BY c.DataPubblicazione`,
    [reportId]
  );
  const [history] = await connection.execute(
    `SELECT
       st.IdStorico AS id, st.StatoPrecedente AS statoPrecedente,
       st.StatoSuccessivo AS statoSuccessivo, st.Motivazione AS motivazione,
       st.DataModifica AS dataModifica,
       CONCAT(u.Nome, ' ', LEFT(u.Cognome, 1), '.') AS autore
     FROM STORICO_STATO st
     JOIN UTENTE u ON u.IdUtente = st.IdAutoreModifica
     WHERE st.IdSegnalazione = ? ORDER BY st.DataModifica`,
    [reportId]
  );

  return { ...normalizeReport(rows[0]), allegati: attachments, commenti: comments, storico: history };
}

export async function getStoredAttachment(connection, fileName) {
  const [rows] = await connection.execute(
    `SELECT a.RiferimentoFile AS riferimento, a.TipoMedia AS tipo, s.Visibilita AS visibilita
     FROM ALLEGATO a
     JOIN SEGNALAZIONE s ON s.IdSegnalazione = a.IdSegnalazione
     WHERE a.RiferimentoFile = ? LIMIT 1`,
    [`/api/files/${fileName}`]
  );
  return rows[0] ?? null;
}
