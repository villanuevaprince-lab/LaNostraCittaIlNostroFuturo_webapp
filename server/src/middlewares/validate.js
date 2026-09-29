import { AppError } from '../utils/app-error.js';

export function validate(schema, source = 'body') {
  return (req, _res, next) => {
    const result = schema.safeParse(req[source]);
    if (!result.success) {
      return next(new AppError(
        422,
        'I dati inviati non sono validi.',
        'VALIDATION_ERROR',
        result.error.flatten().fieldErrors
      ));
    }
    req[source] = result.data;
    next();
  };
}
