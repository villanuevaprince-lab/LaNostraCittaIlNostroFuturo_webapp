import fs from 'node:fs';
import path from 'node:path';
import mysql from 'mysql2/promise';
import { env } from './env.js';

function buildSslConfig() {
  if (env.DB_SSL_MODE === 'disabled') return undefined;

  const ssl = { rejectUnauthorized: env.DB_SSL_MODE === 'verify-ca' };
  if (env.DB_SSL_CA_PATH) {
    ssl.ca = fs.readFileSync(path.resolve(env.DB_SSL_CA_PATH), 'utf8');
  }
  return ssl;
}

export const pool = mysql.createPool({
  host: env.DB_HOST,
  port: env.DB_PORT,
  user: env.DB_USER,
  password: env.DB_PASSWORD,
  database: env.DB_NAME,
  charset: 'utf8mb4',
  timezone: 'Z',
  ssl: buildSslConfig(),
  connectionLimit: 10,
  maxIdle: 10,
  idleTimeout: 60_000,
  enableKeepAlive: true,
  keepAliveInitialDelay: 0,
  namedPlaceholders: true
});

export async function checkDatabase() {
  const connection = await pool.getConnection();
  try {
    await connection.query('SELECT 1');
  } finally {
    connection.release();
  }
}

export async function withTransaction(work) {
  const connection = await pool.getConnection();
  try {
    await connection.beginTransaction();
    const result = await work(connection);
    await connection.commit();
    return result;
  } catch (error) {
    await connection.rollback();
    throw error;
  } finally {
    connection.release();
  }
}
