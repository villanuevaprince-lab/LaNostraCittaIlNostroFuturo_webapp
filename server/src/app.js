import path from 'node:path';
import { fileURLToPath } from 'node:url';
import express from 'express';
import session from 'express-session';
import helmet from 'helmet';
import rateLimit from 'express-rate-limit';
import pinoHttp from 'pino-http';
import { env } from './config/env.js';
import { createSessionStore } from './config/session-store.js';
import { pool } from './config/database.js';
import { csrfProtection } from './middlewares/csrf.js';
import { errorHandler, notFound } from './middlewares/error-handler.js';
import { authRouter } from './routes/auth-routes.js';
import { fileRouter } from './routes/file-routes.js';
import { metadataRouter } from './routes/metadata-routes.js';
import { moderationRouter } from './routes/moderation-routes.js';
import { reportRouter } from './routes/report-routes.js';

const clientPath = fileURLToPath(new URL('../../client', import.meta.url));

export function createApp(options = {}) {
  const app = express();
  if (env.TRUST_PROXY) app.set('trust proxy', 1);

  app.disable('x-powered-by');
  app.locals.sessionCookieName = env.SESSION_COOKIE_NAME;

  app.use(pinoHttp({
    redact: [
      'req.headers.authorization',
      'req.headers.cookie',
      'req.headers["x-csrf-token"]',
      'res.headers["set-cookie"]'
    ]
  }));

  app.use(helmet({
    crossOriginResourcePolicy: { policy: 'same-site' },
    contentSecurityPolicy: {
      directives: {
        defaultSrc: ["'self'"],
        scriptSrc: ["'self'", 'https://unpkg.com'],
        styleSrc: ["'self'", "'unsafe-inline'", 'https://unpkg.com'],
        imgSrc: ["'self'", 'data:', 'blob:', 'https://*.tile.openstreetmap.org'],
        mediaSrc: ["'self'", 'blob:'],
        connectSrc: ["'self'"],
        fontSrc: ["'self'", 'data:'],
        objectSrc: ["'none'"],
        baseUri: ["'self'"],
        formAction: ["'self'"]
      }
    }
  }));

  app.use(express.json({ limit: '100kb' }));
  app.use(express.urlencoded({ extended: false, limit: '100kb' }));
  app.use(session({
    name: env.SESSION_COOKIE_NAME,
    secret: env.SESSION_SECRET,
    store: options.sessionStore ?? createSessionStore(),
    resave: false,
    saveUninitialized: false,
    rolling: true,
    cookie: {
      httpOnly: true,
      secure: env.isProduction,
      sameSite: 'lax',
      maxAge: env.SESSION_MAX_AGE_MS
    }
  }));

  app.use(rateLimit({
    windowMs: 15 * 60 * 1000,
    limit: 500,
    standardHeaders: 'draft-7',
    legacyHeaders: false,
    skip: (req) => req.path === '/api/health'
  }));
  app.use(csrfProtection);

  app.get('/api/health', async (_req, res, next) => {
    try {
      await pool.query('SELECT 1');
      res.json({ status: 'ok', database: 'connected' });
    } catch (error) {
      next(error);
    }
  });
  app.use('/api/auth', authRouter);
  app.use('/api/metadata', metadataRouter);
  app.use('/api/reports', reportRouter);
  app.use('/api/moderation', moderationRouter);
  app.use('/api/files', fileRouter);

  app.use(express.static(clientPath, {
    extensions: ['html'],
    maxAge: env.isProduction ? '1h' : 0
  }));

  app.use((req, res, next) => {
    if (req.method === 'GET' && !req.path.startsWith('/api/')) {
      return res.sendFile(path.join(clientPath, 'index.html'));
    }
    next();
  });

  app.use(notFound);
  app.use(errorHandler);
  return app;
}
