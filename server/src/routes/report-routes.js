import { Router } from 'express';
import multer from 'multer';
import { env } from '../config/env.js';
import { optionalAuth, requireAuth, requireRole } from '../middlewares/auth.js';
import { validate } from '../middlewares/validate.js';
import {
  commentSchema,
  createReportSchema,
  idParamSchema,
  reportListSchema,
  updateStateSchema
} from '../validators/schemas.js';
import { asyncHandler } from '../utils/async-handler.js';
import {
  addComment,
  changeReportState,
  createReport,
  readReport,
  removeReport,
  searchReports,
  supportReport,
  withdrawSupport
} from '../services/report-service.js';

export const reportRouter = Router();

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { files: 1, fileSize: env.MAX_UPLOAD_BYTES, fields: 20 }
});

reportRouter.get('/', optionalAuth, validate(reportListSchema, 'query'), asyncHandler(async (req, res) => {
  res.json(await searchReports(req.query, req.user?.id));
}));

reportRouter.post(
  '/',
  requireAuth,
  upload.single('allegato'),
  validate(createReportSchema),
  asyncHandler(async (req, res) => {
    const report = await createReport(req.user.id, req.body, req.file);
    res.status(201).json({ report });
  })
);

reportRouter.get('/:id', optionalAuth, validate(idParamSchema, 'params'), asyncHandler(async (req, res) => {
  res.json({ report: await readReport(req.params.id, req.user) });
}));

reportRouter.post('/:id/comments', requireAuth, validate(idParamSchema, 'params'), validate(commentSchema), asyncHandler(async (req, res) => {
  const id = await addComment(req.user.id, req.params.id, req.body.testo);
  res.status(201).json({ id });
}));

reportRouter.put('/:id/support', requireAuth, validate(idParamSchema, 'params'), asyncHandler(async (req, res) => {
  await supportReport(req.user.id, req.params.id);
  res.status(204).end();
}));

reportRouter.delete('/:id/support', requireAuth, validate(idParamSchema, 'params'), asyncHandler(async (req, res) => {
  await withdrawSupport(req.user.id, req.params.id);
  res.status(204).end();
}));

reportRouter.patch(
  '/:id/state',
  requireAuth,
  requireRole('base', 'amministratore'),
  validate(idParamSchema, 'params'),
  validate(updateStateSchema),
  asyncHandler(async (req, res) => {
    await changeReportState(req.user.id, req.params.id, req.body.stato, req.body.motivazione);
    res.status(204).end();
  })
);

reportRouter.delete('/:id', requireAuth, validate(idParamSchema, 'params'), asyncHandler(async (req, res) => {
  await removeReport(req.user, req.params.id);
  res.status(204).end();
}));
