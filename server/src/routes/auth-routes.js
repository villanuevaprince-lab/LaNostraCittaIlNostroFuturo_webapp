import { Router } from 'express';
import rateLimit from 'express-rate-limit';
import {
  authenticate,
  deleteAccount,
  getProfile,
  registerUser,
  updateProfile
} from '../services/auth-service.js';
import { requireAuth } from '../middlewares/auth.js';
import { ensureCsrfToken } from '../middlewares/csrf.js';
import { validate } from '../middlewares/validate.js';
import { loginSchema, registerSchema, updateProfileSchema } from '../validators/schemas.js';
import { asyncHandler } from '../utils/async-handler.js';
import { destroySession, regenerateSession, saveSession } from '../utils/session.js';

export const authRouter = Router();

const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  limit: 20,
  standardHeaders: 'draft-7',
  legacyHeaders: false,
  message: { error: { code: 'RATE_LIMIT', message: 'Troppi tentativi. Riprova più tardi.' } }
});

authRouter.get('/csrf', (req, res) => {
  res.json({ csrfToken: ensureCsrfToken(req) });
});

authRouter.post('/register', authLimiter, validate(registerSchema), asyncHandler(async (req, res) => {
  const userId = await registerUser(req.body);
  await regenerateSession(req);
  req.session.userId = userId;
  const csrfToken = ensureCsrfToken(req);
  await saveSession(req);
  res.status(201).json({ user: await getProfile(userId), csrfToken });
}));

authRouter.post('/login', authLimiter, validate(loginSchema), asyncHandler(async (req, res) => {
  const userId = await authenticate(req.body.email, req.body.password);
  await regenerateSession(req);
  req.session.userId = userId;
  const csrfToken = ensureCsrfToken(req);
  await saveSession(req);
  res.json({ user: await getProfile(userId), csrfToken });
}));

authRouter.post('/logout', requireAuth, asyncHandler(async (req, res) => {
  await destroySession(req);
  res.clearCookie(req.app.locals.sessionCookieName);
  res.status(204).end();
}));

authRouter.get('/me', asyncHandler(async (req, res) => {
  if (!req.session.userId) return res.json({ user: null });
  const user = await getProfile(req.session.userId);
  if (!user || user.statoAccount !== 'attivo') return res.json({ user: null });
  return res.json({ user });
}));

authRouter.put('/me', requireAuth, validate(updateProfileSchema), asyncHandler(async (req, res) => {
  res.json({ user: await updateProfile(req.user.id, req.body) });
}));

authRouter.delete('/me', requireAuth, asyncHandler(async (req, res) => {
  await deleteAccount(req.user.id);
  await destroySession(req);
  res.clearCookie(req.app.locals.sessionCookieName);
  res.status(204).end();
}));
