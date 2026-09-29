import { Router } from 'express';
import { requireAuth, requireRole } from '../middlewares/auth.js';
import { validate } from '../middlewares/validate.js';
import {
  blockUserSchema,
  idParamSchema,
  unblockUserSchema,
  userListSchema
} from '../validators/schemas.js';
import { asyncHandler } from '../utils/async-handler.js';
import {
  blockUser,
  hideComment,
  listRecentEvents,
  listUsers,
  unblockUser
} from '../services/moderation-service.js';

export const moderationRouter = Router();

moderationRouter.use(requireAuth, requireRole('base', 'amministratore'));

moderationRouter.get('/users', validate(userListSchema, 'query'), asyncHandler(async (req, res) => {
  res.json(await listUsers(req.query));
}));

moderationRouter.post('/users/:id/block', validate(idParamSchema, 'params'), validate(blockUserSchema), asyncHandler(async (req, res) => {
  await blockUser(req.user.id, req.params.id, req.body);
  res.status(201).json({ message: 'Account bloccato.' });
}));

moderationRouter.post('/users/:id/unblock', validate(idParamSchema, 'params'), validate(unblockUserSchema), asyncHandler(async (req, res) => {
  await unblockUser(req.user.id, req.params.id, req.body.motivoRevoca);
  res.json({ message: 'Blocco revocato.' });
}));

moderationRouter.delete('/comments/:id', validate(idParamSchema, 'params'), asyncHandler(async (req, res) => {
  await hideComment(req.user.id, req.params.id);
  res.status(204).end();
}));

moderationRouter.get('/events', asyncHandler(async (_req, res) => {
  res.json({ items: await listRecentEvents() });
}));
