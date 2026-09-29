import multer from 'multer';
import { AppError } from '../utils/app-error.js';

export function notFound(req, _res, next) {
  next(new AppError(404, `Risorsa non trovata: ${req.method} ${req.originalUrl}`, 'NOT_FOUND'));
}

export function errorHandler(error, req, res, _next) {
  let normalized = error;

  if (error instanceof multer.MulterError) {
    normalized = new AppError(
      error.code === 'LIMIT_FILE_SIZE' ? 413 : 400,
      error.code === 'LIMIT_FILE_SIZE' ? 'Il file supera la dimensione massima.' : 'Caricamento non valido.',
      error.code
    );
  } else if (error?.code === 'ER_DUP_ENTRY') {
    normalized = new AppError(409, 'Esiste già un elemento con questi dati.', 'DUPLICATE_VALUE');
  } else if (error?.code === 'ER_NO_REFERENCED_ROW_2') {
    normalized = new AppError(422, 'Uno dei riferimenti indicati non esiste.', 'INVALID_REFERENCE');
  }

  const status = normalized.statusCode ?? 500;
  if (status >= 500) req.log?.error({ err: error }, 'Errore interno');

  res.status(status).json({
    error: {
      code: normalized.code ?? 'INTERNAL_ERROR',
      message: status >= 500 ? 'Si è verificato un errore interno.' : normalized.message,
      ...(normalized.details ? { details: normalized.details } : {})
    }
  });
}
