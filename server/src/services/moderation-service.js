import { pool, withTransaction } from '../config/database.js';
import { writeAudit } from '../repositories/audit-repository.js';
import { AppError } from '../utils/app-error.js';

export async function listUsers(filters) {
  const offset = (filters.pagina - 1) * filters.limite;
  const like = `%${filters.q}%`;
  const condition = filters.q
    ? 'WHERE u.Nome LIKE ? OR u.Cognome LIKE ? OR u.Email LIKE ?'
    : '';
  const searchValues = filters.q ? [like, like, like] : [];
  const [rows] = await pool.execute(
    `SELECT
       u.IdUtente AS id, u.Nome AS nome, u.Cognome AS cognome,
       u.Email AS email, u.StatoAccount AS statoAccount,
       u.DataRegistrazione AS dataRegistrazione,
       COALESCE(m.LivelloPermessi, 'utente') AS ruolo,
       q.Nome AS quartiere
     FROM UTENTE u
     LEFT JOIN MODERATORE m ON m.IdUtente = u.IdUtente
     LEFT JOIN QUARTIERE q ON q.IdQuartiere = u.IdQuartiere
     ${condition}
     ORDER BY u.DataRegistrazione DESC LIMIT ? OFFSET ?`,
    [...searchValues, filters.limite, offset]
  );
  const [counts] = await pool.execute(
    `SELECT COUNT(*) AS totale FROM UTENTE u ${condition}`,
    searchValues
  );
  return {
    items: rows,
    pagina: filters.pagina,
    totale: Number(counts[0].totale),
    pagine: Math.ceil(Number(counts[0].totale) / filters.limite)
  };
}

export async function blockUser(moderatorId, userId, data) {
  if (moderatorId === userId) throw new AppError(422, 'Non puoi bloccare il tuo account.', 'SELF_BLOCK');
  await withTransaction(async (connection) => {
    const [users] = await connection.execute(
      `SELECT u.StatoAccount,
              targetModerator.LivelloPermessi AS ruoloBersaglio,
              actorModerator.LivelloPermessi AS ruoloEsecutore
       FROM UTENTE u
       LEFT JOIN MODERATORE targetModerator ON targetModerator.IdUtente = u.IdUtente
       JOIN MODERATORE actorModerator ON actorModerator.IdUtente = ?
       WHERE u.IdUtente = ? FOR UPDATE`,
      [moderatorId, userId]
    );
    if (!users.length) throw new AppError(404, 'Utente non trovato.', 'USER_NOT_FOUND');
    if (users[0].StatoAccount === 'cancellato') {
      throw new AppError(422, 'Un account cancellato non può essere bloccato.', 'ACCOUNT_DELETED');
    }
    if (users[0].ruoloBersaglio && users[0].ruoloEsecutore !== 'amministratore') {
      throw new AppError(403, 'Solo un amministratore può bloccare un moderatore.', 'FORBIDDEN');
    }
    const [result] = await connection.execute(
      `INSERT INTO BLOCCO (
         IdUtenteBloccato, IdModeratore, Motivazione, DataFinePrevista
       ) VALUES (?, ?, ?, ?)`,
      [userId, moderatorId, data.motivazione, data.dataFinePrevista ? new Date(data.dataFinePrevista) : null]
    );
    await connection.execute(
      `UPDATE UTENTE SET StatoAccount = 'bloccato' WHERE IdUtente = ?`,
      [userId]
    );
    await writeAudit(connection, {
      executorId: moderatorId,
      type: 'blocco_utente',
      details: 'Account bloccato da un moderatore.',
      targetUserId: userId,
      blockId: result.insertId
    });
  });
}

export async function unblockUser(moderatorId, userId, reason) {
  await withTransaction(async (connection) => {
    const [roles] = await connection.execute(
      `SELECT targetModerator.LivelloPermessi AS ruoloBersaglio,
              actorModerator.LivelloPermessi AS ruoloEsecutore
       FROM UTENTE u
       LEFT JOIN MODERATORE targetModerator ON targetModerator.IdUtente = u.IdUtente
       JOIN MODERATORE actorModerator ON actorModerator.IdUtente = ?
       WHERE u.IdUtente = ?`,
      [moderatorId, userId]
    );
    if (!roles.length) throw new AppError(404, 'Utente non trovato.', 'USER_NOT_FOUND');
    if (roles[0].ruoloBersaglio && roles[0].ruoloEsecutore !== 'amministratore') {
      throw new AppError(403, 'Solo un amministratore può sbloccare un moderatore.', 'FORBIDDEN');
    }
    const [blocks] = await connection.execute(
      `SELECT IdBlocco FROM BLOCCO
       WHERE IdUtenteBloccato = ? AND DataRevoca IS NULL
       ORDER BY DataInizio DESC LIMIT 1 FOR UPDATE`,
      [userId]
    );
    if (!blocks.length) throw new AppError(404, 'Nessun blocco attivo trovato.', 'BLOCK_NOT_FOUND');
    await connection.execute(
      `UPDATE BLOCCO
       SET IdModeratoreRevoca = ?, DataRevoca = CURRENT_TIMESTAMP, MotivoRevoca = ?
       WHERE IdBlocco = ?`,
      [moderatorId, reason, blocks[0].IdBlocco]
    );
    await connection.execute(
      `UPDATE UTENTE SET StatoAccount = 'attivo' WHERE IdUtente = ?`,
      [userId]
    );
    await writeAudit(connection, {
      executorId: moderatorId,
      type: 'revoca_blocco',
      details: 'Blocco account revocato.',
      targetUserId: userId,
      blockId: blocks[0].IdBlocco
    });
  });
}

export async function hideComment(moderatorId, commentId) {
  await withTransaction(async (connection) => {
    const [comments] = await connection.execute(
      'SELECT IdSegnalazione FROM COMMENTO WHERE IdCommento = ? FOR UPDATE',
      [commentId]
    );
    if (!comments.length) throw new AppError(404, 'Commento non trovato.', 'COMMENT_NOT_FOUND');
    await connection.execute(
      `UPDATE COMMENTO SET Visibilita = 'rimossa' WHERE IdCommento = ?`,
      [commentId]
    );
    await writeAudit(connection, {
      executorId: moderatorId,
      type: 'rimozione_commento',
      details: 'Commento rimosso da un moderatore.',
      reportId: comments[0].IdSegnalazione,
      commentId
    });
  });
}

export async function listRecentEvents() {
  const [rows] = await pool.execute(
    `SELECT
       e.IdEvento AS id, e.TipoAzione AS tipo, e.DataOra AS dataOra,
       e.Esito AS esito, e.Dettagli AS dettagli,
       CONCAT(u.Nome, ' ', u.Cognome) AS esecutore
     FROM EVENTO_LOG e
     LEFT JOIN UTENTE u ON u.IdUtente = e.IdEsecutore
     ORDER BY e.DataOra DESC LIMIT 50`
  );
  return rows;
}
