import { pool } from '../config/database.js';
import { AppError } from '../utils/app-error.js';

async function loadUser(userId) {
  const [rows] = await pool.execute(
    `SELECT
       u.IdUtente AS id,
       u.Nome AS nome,
       u.Cognome AS cognome,
       u.Email AS email,
       u.StatoAccount AS statoAccount,
       u.IdQuartiere AS idQuartiere,
       q.Nome AS quartiere,
       m.LivelloPermessi AS ruolo
     FROM UTENTE u
     LEFT JOIN QUARTIERE q ON q.IdQuartiere = u.IdQuartiere
     LEFT JOIN MODERATORE m ON m.IdUtente = u.IdUtente
     WHERE u.IdUtente = ?
     LIMIT 1`,
    [userId]
  );
  if (!rows.length) return null;
  return { ...rows[0], ruolo: rows[0].ruolo ?? 'utente' };
}

export async function requireAuth(req, _res, next) {
  try {
    if (!req.session.userId) {
      throw new AppError(401, 'Devi accedere per continuare.', 'AUTH_REQUIRED');
    }
    const user = await loadUser(req.session.userId);
    if (!user) {
      req.session.destroy(() => {});
      throw new AppError(401, 'Sessione non più valida.', 'SESSION_INVALID');
    }
    if (user.statoAccount !== 'attivo') {
      throw new AppError(403, 'Questo account non può utilizzare la piattaforma.', 'ACCOUNT_DISABLED');
    }
    req.user = user;
    next();
  } catch (error) {
    next(error);
  }
}

export async function optionalAuth(req, _res, next) {
  try {
    if (req.session.userId) {
      const user = await loadUser(req.session.userId);
      if (user?.statoAccount === 'attivo') req.user = user;
    }
    next();
  } catch (error) {
    next(error);
  }
}

export function requireRole(...roles) {
  return (req, _res, next) => {
    if (!req.user || !roles.includes(req.user.ruolo)) {
      return next(new AppError(403, 'Non hai i permessi necessari.', 'FORBIDDEN'));
    }
    next();
  };
}
