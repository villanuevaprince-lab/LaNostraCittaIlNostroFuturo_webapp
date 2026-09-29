import fs from 'node:fs';
import { Router } from 'express';
import { pool } from '../config/database.js';
import { getStoredAttachment } from '../repositories/report-repository.js';
import { asyncHandler } from '../utils/async-handler.js';
import { AppError } from '../utils/app-error.js';
import { resolveStoredFile } from '../services/storage-service.js';

export const fileRouter = Router();

fileRouter.get('/:fileName', asyncHandler(async (req, res) => {
  const record = await getStoredAttachment(pool, req.params.fileName);
  if (!record || record.visibilita !== 'pubblica') {
    throw new AppError(404, 'File non trovato.', 'FILE_NOT_FOUND');
  }
  const absolutePath = resolveStoredFile(req.params.fileName);
  if (!fs.existsSync(absolutePath)) {
    throw new AppError(404, 'File non trovato.', 'FILE_NOT_FOUND');
  }
  res.type(record.tipo);
  res.set('Cache-Control', 'public, max-age=3600');
  res.sendFile(absolutePath);
}));
