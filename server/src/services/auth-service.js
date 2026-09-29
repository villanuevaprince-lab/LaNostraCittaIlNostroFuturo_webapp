import argon2 from 'argon2';
import { pool, withTransaction } from '../config/database.js';
import { writeAudit } from '../repositories/audit-repository.js';
import { AppError } from '../utils/app-error.js';

const publicUserQuery = `
  SELECT
    u.IdUtente AS id,
    u.Nome AS nome,
    u.Cognome AS cognome,
    u.Email AS email,
    u.IdQuartiere AS idQuartiere,
    q.Nome AS quartiere,
    u.DataRegistrazione AS dataRegistrazione,
    u.StatoAccount AS statoAccount,
    COALESCE(m.LivelloPermessi, 'utente') AS ruolo
  FROM UTENTE u
  LEFT JOIN QUARTIERE q ON q.IdQuartiere = u.IdQuartiere
  LEFT JOIN MODERATORE m ON m.IdUtente = u.IdUtente`;

export async function getProfile(userId) {
  const [rows] = await pool.execute(`${publicUserQuery} WHERE u.IdUtente = ? LIMIT 1`, [userId]);
  return rows[0] ?? null;
}

export async function registerUser(data) {
  const hash = await argon2.hash(data.password, { type: argon2.argon2id });
  return withTransaction(async (connection) => {
    const [existing] = await connection.execute(
      'SELECT IdUtente FROM UTENTE WHERE Email = ? LIMIT 1',
      [data.email]
    );
    if (existing.length) {
      throw new AppError(409, 'Esiste già un account con questa email.', 'EMAIL_IN_USE');
    }

    const [result] = await connection.execute(
      `INSERT INTO UTENTE (IdQuartiere, Nome, Cognome, Email, HashPassword, StatoAccount)
       VALUES (?, ?, ?, ?, ?, 'attivo')`,
      [data.idQuartiere, data.nome, data.cognome, data.email, hash]
    );

    await writeAudit(connection, {
      executorId: result.insertId,
      type: 'registrazione_account',
      details: 'Registrazione account completata.',
      targetUserId: result.insertId
    });
    return result.insertId;
  });
}

export async function authenticate(email, password) {
  const [rows] = await pool.execute(
    `SELECT IdUtente AS id, HashPassword AS hash, StatoAccount AS statoAccount
     FROM UTENTE WHERE Email = ? LIMIT 1`,
    [email]
  );
  const candidate = rows[0];
  if (!candidate) {
    throw new AppError(401, 'Email o password non corrette.', 'INVALID_CREDENTIALS');
  }

  let valid = false;
  try {
    valid = await argon2.verify(candidate.hash, password);
  } catch {
    valid = false;
  }
  if (!valid) {
    throw new AppError(401, 'Email o password non corrette.', 'INVALID_CREDENTIALS');
  }
  if (candidate.statoAccount !== 'attivo') {
    throw new AppError(403, 'Questo account non può accedere.', 'ACCOUNT_DISABLED');
  }
  return candidate.id;
}

export async function updateProfile(userId, data) {
  await pool.execute(
    `UPDATE UTENTE SET Nome = ?, Cognome = ?, IdQuartiere = ?
     WHERE IdUtente = ? AND StatoAccount = 'attivo'`,
    [data.nome, data.cognome, data.idQuartiere, userId]
  );
  return getProfile(userId);
}

export async function deleteAccount(userId) {
  await withTransaction(async (connection) => {
    await connection.execute(
      `UPDATE UTENTE
       SET StatoAccount = 'cancellato', DataCancellazione = CURRENT_TIMESTAMP
       WHERE IdUtente = ?`,
      [userId]
    );
    await writeAudit(connection, {
      executorId: userId,
      type: 'cancellazione_account',
      details: 'Cancellazione logica dell’account.',
      targetUserId: userId
    });
  });
}
