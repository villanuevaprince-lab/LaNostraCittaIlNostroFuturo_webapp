import { pool, withTransaction } from '../config/database.js';
import { writeAudit } from '../repositories/audit-repository.js';
import { getReport, listReports } from '../repositories/report-repository.js';
import { AppError } from '../utils/app-error.js';
import { removeUpload, saveUpload } from './storage-service.js';

export async function searchReports(filters, viewerId) {
  return listReports(pool, filters, viewerId);
}

export async function readReport(reportId, viewer) {
  const report = await getReport(pool, reportId, viewer?.id);
  if (!report) throw new AppError(404, 'Segnalazione non trovata.', 'REPORT_NOT_FOUND');
  const privileged = viewer && (viewer.id === report.idAutore || viewer.ruolo !== 'utente');
  if (report.visibilita !== 'pubblica' && !privileged) {
    throw new AppError(404, 'Segnalazione non trovata.', 'REPORT_NOT_FOUND');
  }
  return report;
}

export async function createReport(userId, data, file) {
  const stored = await saveUpload(file);
  try {
    const reportId = await withTransaction(async (connection) => {
      const [reportResult] = await connection.execute(
        `INSERT INTO SEGNALAZIONE (
           IdAutore, IdQuartiere, Tipo, Titolo, Descrizione, Stato, Visibilita,
           Latitudine, Longitudine, Indirizzo
         ) VALUES (?, ?, ?, ?, ?, 'nuova', 'pubblica', ?, ?, ?)`,
        [
          userId, data.idQuartiere, data.tipo, data.titolo, data.descrizione,
          data.latitudine, data.longitudine, data.indirizzo
        ]
      );
      const id = reportResult.insertId;

      const [attachmentResult] = await connection.execute(
        `INSERT INTO ALLEGATO (
           IdSegnalazione, IdAutore, TipoMedia, RiferimentoFile, NomeOriginale,
           DimensioneByte, HashSHA256, DescrizioneAccessibile
         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
        [
          id, userId, stored.mime, stored.reference, stored.originalName,
          stored.size, stored.hash, data.descrizioneAccessibile
        ]
      );

      for (const categoryId of [...new Set(data.categorie)]) {
        await connection.execute(
          `INSERT INTO SEGNALAZIONE_CATEGORIA (IdSegnalazione, IdCategoria, Origine)
           VALUES (?, ?, 'utente')`,
          [id, categoryId]
        );
      }

      await connection.execute(
        `INSERT INTO STORICO_STATO (
           IdSegnalazione, StatoPrecedente, StatoSuccessivo, IdAutoreModifica, Motivazione
         ) VALUES (?, NULL, 'nuova', ?, 'Creazione della segnalazione')`,
        [id, userId]
      );

      await writeAudit(connection, {
        executorId: userId,
        type: 'creazione_segnalazione',
        details: `Creata ${data.tipo}.`,
        reportId: id,
        attachmentId: attachmentResult.insertId
      });
      return id;
    });
    return readReport(reportId, { id: userId, ruolo: 'utente' });
  } catch (error) {
    await removeUpload(stored.absolutePath);
    throw error;
  }
}

export async function addComment(userId, reportId, text) {
  return withTransaction(async (connection) => {
    const [reports] = await connection.execute(
      `SELECT IdSegnalazione FROM SEGNALAZIONE
       WHERE IdSegnalazione = ? AND Visibilita = 'pubblica'`,
      [reportId]
    );
    if (!reports.length) throw new AppError(404, 'Segnalazione non trovata.', 'REPORT_NOT_FOUND');
    const [result] = await connection.execute(
      `INSERT INTO COMMENTO (IdAutore, IdSegnalazione, Testo, Visibilita)
       VALUES (?, ?, ?, 'pubblica')`,
      [userId, reportId, text]
    );
    await writeAudit(connection, {
      executorId: userId,
      type: 'pubblicazione_commento',
      details: 'Pubblicato un commento.',
      reportId,
      commentId: result.insertId
    });
    return result.insertId;
  });
}

export async function supportReport(userId, reportId) {
  return withTransaction(async (connection) => {
    const [reports] = await connection.execute(
      `SELECT IdSegnalazione FROM SEGNALAZIONE
       WHERE IdSegnalazione = ? AND Visibilita = 'pubblica'`,
      [reportId]
    );
    if (!reports.length) throw new AppError(404, 'Segnalazione non trovata.', 'REPORT_NOT_FOUND');
    await connection.execute(
      `INSERT INTO SOSTEGNO (IdUtente, IdSegnalazione, DataEspressione, DataRitiro)
       VALUES (?, ?, CURRENT_TIMESTAMP, NULL)
       ON DUPLICATE KEY UPDATE DataEspressione = CURRENT_TIMESTAMP, DataRitiro = NULL`,
      [userId, reportId]
    );
    const [rows] = await connection.execute(
      'SELECT IdSostegno FROM SOSTEGNO WHERE IdUtente = ? AND IdSegnalazione = ?',
      [userId, reportId]
    );
    await writeAudit(connection, {
      executorId: userId,
      type: 'espressione_sostegno',
      details: 'Aggiunto sostegno alla segnalazione.',
      reportId,
      supportId: rows[0].IdSostegno
    });
  });
}

export async function withdrawSupport(userId, reportId) {
  await withTransaction(async (connection) => {
    const [rows] = await connection.execute(
      `SELECT IdSostegno FROM SOSTEGNO
       WHERE IdUtente = ? AND IdSegnalazione = ? AND DataRitiro IS NULL`,
      [userId, reportId]
    );
    if (!rows.length) return;
    await connection.execute(
      'UPDATE SOSTEGNO SET DataRitiro = CURRENT_TIMESTAMP WHERE IdSostegno = ?',
      [rows[0].IdSostegno]
    );
    await writeAudit(connection, {
      executorId: userId,
      type: 'ritiro_sostegno',
      details: 'Ritirato sostegno dalla segnalazione.',
      reportId,
      supportId: rows[0].IdSostegno
    });
  });
}

export async function changeReportState(moderatorId, reportId, nextState, reason) {
  await withTransaction(async (connection) => {
    const [states] = await connection.execute(
      'SELECT Codice FROM STATO_SEGNALAZIONE WHERE Codice = ? LIMIT 1',
      [nextState]
    );
    if (!states.length) throw new AppError(422, 'Stato non riconosciuto.', 'INVALID_STATE');

    const [reports] = await connection.execute(
      'SELECT Stato FROM SEGNALAZIONE WHERE IdSegnalazione = ? FOR UPDATE',
      [reportId]
    );
    if (!reports.length) throw new AppError(404, 'Segnalazione non trovata.', 'REPORT_NOT_FOUND');
    const previous = reports[0].Stato;
    if (previous === nextState) return;

    await connection.execute('UPDATE SEGNALAZIONE SET Stato = ? WHERE IdSegnalazione = ?', [nextState, reportId]);
    await connection.execute(
      `INSERT INTO STORICO_STATO (
         IdSegnalazione, StatoPrecedente, StatoSuccessivo, IdAutoreModifica, Motivazione
       ) VALUES (?, ?, ?, ?, ?)`,
      [reportId, previous, nextState, moderatorId, reason || null]
    );
    const eventId = await writeAudit(connection, {
      executorId: moderatorId,
      type: 'modifica_stato_segnalazione',
      details: `Stato modificato da ${previous} a ${nextState}.`,
      reportId
    });
    await connection.execute(
      `INSERT INTO VARIAZIONE_LOG (IdEvento, NomeCampo, ValorePrecedente, ValoreSuccessivo)
       VALUES (?, 'SEGNALAZIONE.Stato', ?, ?)`,
      [eventId, previous, nextState]
    );
  });
}

export async function removeReport(actor, reportId) {
  await withTransaction(async (connection) => {
    const [reports] = await connection.execute(
      'SELECT IdAutore, Visibilita FROM SEGNALAZIONE WHERE IdSegnalazione = ? FOR UPDATE',
      [reportId]
    );
    if (!reports.length) throw new AppError(404, 'Segnalazione non trovata.', 'REPORT_NOT_FOUND');
    if (actor.ruolo === 'utente' && actor.id !== reports[0].IdAutore) {
      throw new AppError(403, 'Non puoi rimuovere questa segnalazione.', 'FORBIDDEN');
    }
    await connection.execute(
      `UPDATE SEGNALAZIONE SET Visibilita = 'rimossa' WHERE IdSegnalazione = ?`,
      [reportId]
    );
    await writeAudit(connection, {
      executorId: actor.id,
      type: 'rimozione_segnalazione',
      details: 'Segnalazione rimossa logicamente.',
      reportId
    });
  });
}
