import 'dotenv/config';
import path from 'node:path';
import { z } from 'zod';

const booleanFromString = z
  .enum(['true', 'false'])
  .default('false')
  .transform((value) => value === 'true');

const schema = z.object({
  NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
  PORT: z.coerce.number().int().min(1).max(65535).default(3000),
  APP_BASE_URL: z.string().url().default('http://127.0.0.1:3000'),
  TRUST_PROXY: booleanFromString,
  DB_HOST: z.string().min(1).default('localhost'),
  DB_PORT: z.coerce.number().int().min(1).max(65535).default(3306),
  DB_USER: z.string().min(1).default('root'),
  DB_PASSWORD: z.string().default(''),
  DB_NAME: z.string().min(1).default('nostra_citta'),
  DB_SSL_MODE: z.enum(['verify-ca', 'required', 'disabled']).default('disabled'),
  DB_SSL_CA_PATH: z.string().optional(),
  SESSION_SECRET: z.string().min(32).default('development-only-secret-change-me-now'),
  SESSION_COOKIE_NAME: z.string().min(1).default('nostra_citta.sid'),
  SESSION_MAX_AGE_MS: z.coerce.number().int().positive().default(28_800_000),
  STORAGE_DIR: z.string().default('storage/uploads'),
  MAX_UPLOAD_BYTES: z.coerce.number().int().positive().max(50_000_000).default(12_582_912)
});

const parsed = schema.safeParse(process.env);

if (!parsed.success) {
  console.error('Configurazione non valida:', parsed.error.flatten().fieldErrors);
  process.exit(1);
}

export const env = {
  ...parsed.data,
  storagePath: path.resolve(parsed.data.STORAGE_DIR),
  isProduction: parsed.data.NODE_ENV === 'production'
};
