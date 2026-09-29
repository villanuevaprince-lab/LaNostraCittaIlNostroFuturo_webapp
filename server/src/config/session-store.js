import session from 'express-session';
import { pool } from './database.js';
import { env } from './env.js';

class MySQLSessionStore extends session.Store {
  constructor() {
    super();
    this.cleanupTimer = setInterval(() => {
      pool.execute('DELETE FROM SESSIONE_WEB WHERE Scadenza < ?', [Date.now()]).catch(() => {});
    }, 15 * 60 * 1000);
    this.cleanupTimer.unref();
  }

  get(sessionId, callback) {
    pool.execute(
      'SELECT Dati FROM SESSIONE_WEB WHERE IdSessione = ? AND Scadenza >= ? LIMIT 1',
      [sessionId, Date.now()]
    ).then(([rows]) => {
      if (!rows.length) return callback(null, null);
      try { callback(null, JSON.parse(rows[0].Dati)); }
      catch (error) { callback(error); }
    }).catch(callback);
  }

  set(sessionId, sessionData, callback = () => {}) {
    const expires = sessionData.cookie?.expires
      ? new Date(sessionData.cookie.expires).getTime()
      : Date.now() + env.SESSION_MAX_AGE_MS;
    pool.execute(
      `INSERT INTO SESSIONE_WEB (IdSessione, Scadenza, Dati)
       VALUES (?, ?, ?)
       ON DUPLICATE KEY UPDATE Scadenza = VALUES(Scadenza), Dati = VALUES(Dati)`,
      [sessionId, expires, JSON.stringify(sessionData)]
    ).then(() => callback()).catch(callback);
  }

  destroy(sessionId, callback = () => {}) {
    pool.execute('DELETE FROM SESSIONE_WEB WHERE IdSessione = ?', [sessionId])
      .then(() => callback()).catch(callback);
  }

  touch(sessionId, sessionData, callback = () => {}) {
    const expires = sessionData.cookie?.expires
      ? new Date(sessionData.cookie.expires).getTime()
      : Date.now() + env.SESSION_MAX_AGE_MS;
    pool.execute('UPDATE SESSIONE_WEB SET Scadenza = ? WHERE IdSessione = ?', [expires, sessionId])
      .then(() => callback()).catch(callback);
  }
}

export function createSessionStore() {
  return new MySQLSessionStore();
}
