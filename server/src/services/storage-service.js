import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileTypeFromBuffer } from 'file-type';
import { env } from '../config/env.js';
import { AppError } from '../utils/app-error.js';

const allowedTypes = new Set([
  'image/jpeg',
  'image/png',
  'image/webp',
  'video/mp4',
  'video/webm'
]);

export async function saveUpload(file) {
  if (!file) {
    throw new AppError(422, 'È obbligatorio allegare una foto o un breve video.', 'ATTACHMENT_REQUIRED');
  }

  const detected = await fileTypeFromBuffer(file.buffer);
  if (!detected || !allowedTypes.has(detected.mime)) {
    throw new AppError(415, 'Formato non supportato. Usa JPG, PNG, WebP, MP4 o WebM.', 'UNSUPPORTED_MEDIA');
  }

  await fs.mkdir(env.storagePath, { recursive: true });
  const fileName = `${crypto.randomUUID()}.${detected.ext}`;
  const absolutePath = path.join(env.storagePath, fileName);
  const hash = crypto.createHash('sha256').update(file.buffer).digest('hex');
  await fs.writeFile(absolutePath, file.buffer, { flag: 'wx' });

  return {
    fileName,
    absolutePath,
    reference: `/api/files/${fileName}`,
    mime: detected.mime,
    originalName: path.basename(file.originalname).slice(0, 255),
    size: file.size,
    hash
  };
}

export async function removeUpload(absolutePath) {
  if (!absolutePath) return;
  await fs.rm(absolutePath, { force: true });
}

export function resolveStoredFile(fileName) {
  const safeName = path.basename(fileName);
  if (safeName !== fileName) throw new AppError(400, 'Nome file non valido.', 'INVALID_FILE_NAME');
  return path.join(env.storagePath, safeName);
}
