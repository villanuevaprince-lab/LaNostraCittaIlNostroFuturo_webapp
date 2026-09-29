import crypto from 'node:crypto';
import { AppError } from '../utils/app-error.js';

export function ensureCsrfToken(req) {
  if (!req.session.csrfToken) {
    req.session.csrfToken = crypto.randomBytes(32).toString('hex');
  }
  return req.session.csrfToken;
}

export function csrfProtection(req, _res, next) {
  if (['GET', 'HEAD', 'OPTIONS'].includes(req.method)) return next();

  const expected = req.session.csrfToken;
  const provided = req.get('x-csrf-token');
  if (!expected || !provided) {
    return next(new AppError(403, 'Token di sicurezza mancante.', 'CSRF_MISSING'));
  }

  const expectedBuffer = Buffer.from(expected);
  const providedBuffer = Buffer.from(provided);
  if (
    expectedBuffer.length !== providedBuffer.length ||
    !crypto.timingSafeEqual(expectedBuffer, providedBuffer)
  ) {
    return next(new AppError(403, 'Token di sicurezza non valido.', 'CSRF_INVALID'));
  }
  next();
}
