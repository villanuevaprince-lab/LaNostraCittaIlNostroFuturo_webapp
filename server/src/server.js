import fs from 'node:fs/promises';
import { createApp } from './app.js';
import { checkDatabase, pool } from './config/database.js';
import { env } from './config/env.js';

async function start() {
  await fs.mkdir(env.storagePath, { recursive: true });
  await checkDatabase();
  const app = createApp();
  const server = app.listen(env.PORT, () => {
    console.log(`La Nostra Città disponibile su ${env.APP_BASE_URL}`);
  });

  async function shutdown(signal) {
    console.log(`${signal}: arresto in corso...`);
    server.close(async () => {
      await pool.end();
      process.exit(0);
    });
  }
  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));
}

start().catch((error) => {
  console.error('Avvio non riuscito:', error.message);
  process.exit(1);
});
