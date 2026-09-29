import { z } from 'zod';

const trimmed = (min, max) => z.string().trim().min(min).max(max);
const optionalId = z.preprocess(
  (value) => (value === '' || value === null || value === undefined ? null : value),
  z.coerce.number().int().positive().nullable()
);
const optionalCoordinate = (min, max) => z.preprocess(
  (value) => (value === '' || value === null || value === undefined ? null : value),
  z.coerce.number().min(min).max(max).nullable()
);

export const registerSchema = z.object({
  nome: trimmed(2, 100),
  cognome: trimmed(2, 100),
  email: z.string().trim().email().max(254).transform((value) => value.toLowerCase()),
  password: z.string().min(10).max(128)
    .regex(/[a-z]/, 'Serve almeno una lettera minuscola.')
    .regex(/[A-Z]/, 'Serve almeno una lettera maiuscola.')
    .regex(/[0-9]/, 'Serve almeno un numero.'),
  idQuartiere: optionalId.default(null)
});

export const loginSchema = z.object({
  email: z.string().trim().email().max(254).transform((value) => value.toLowerCase()),
  password: z.string().min(1).max(128)
});

export const updateProfileSchema = z.object({
  nome: trimmed(2, 100),
  cognome: trimmed(2, 100),
  idQuartiere: optionalId.default(null)
});

function parseCategories(value) {
  if (Array.isArray(value)) return value;
  if (typeof value !== 'string' || !value.trim()) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return value.split(',').map((item) => item.trim()).filter(Boolean);
  }
}

export const createReportSchema = z.object({
  tipo: z.enum(['segnalazione', 'proposta']),
  titolo: trimmed(5, 200),
  descrizione: trimmed(20, 5000),
  idQuartiere: optionalId.default(null),
  latitudine: optionalCoordinate(-90, 90).default(null),
  longitudine: optionalCoordinate(-180, 180).default(null),
  indirizzo: z.preprocess(
    (value) => (value === '' || value === null || value === undefined ? null : value),
    z.string().trim().max(255).nullable()
  ).default(null),
  descrizioneAccessibile: trimmed(5, 1000),
  categorie: z.preprocess(parseCategories, z.array(z.coerce.number().int().positive()).min(1).max(5))
}).refine(
  (data) => (data.latitudine === null) === (data.longitudine === null),
  { message: 'Latitudine e longitudine devono essere indicate insieme.', path: ['latitudine'] }
);

export const reportListSchema = z.object({
  q: z.string().trim().max(100).optional().default(''),
  tipo: z.enum(['segnalazione', 'proposta']).optional(),
  stato: z.string().trim().max(30).optional(),
  idQuartiere: z.coerce.number().int().positive().optional(),
  idCategoria: z.coerce.number().int().positive().optional(),
  ordine: z.enum(['recenti', 'sostenute']).default('recenti'),
  pagina: z.coerce.number().int().positive().default(1),
  limite: z.coerce.number().int().min(1).max(24).default(9)
});

export const idParamSchema = z.object({ id: z.coerce.number().int().positive() });

export const commentSchema = z.object({ testo: trimmed(2, 1500) });

export const updateStateSchema = z.object({
  stato: z.string().trim().min(2).max(30),
  motivazione: z.string().trim().max(500).optional().default('')
});

export const blockUserSchema = z.object({
  motivazione: trimmed(10, 1000),
  dataFinePrevista: z.preprocess(
    (value) => (value === '' || value === null || value === undefined ? null : value),
    z.string().datetime({ offset: true }).nullable()
  ).default(null)
});

export const unblockUserSchema = z.object({ motivoRevoca: trimmed(5, 1000) });

export const userListSchema = z.object({
  q: z.string().trim().max(100).optional().default(''),
  pagina: z.coerce.number().int().positive().default(1),
  limite: z.coerce.number().int().min(1).max(50).default(20)
});
