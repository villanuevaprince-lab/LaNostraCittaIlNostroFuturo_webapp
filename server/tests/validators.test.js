import { describe, expect, it } from 'vitest';
import {
  createReportSchema,
  registerSchema,
  reportListSchema
} from '../src/validators/schemas.js';

describe('registerSchema', () => {
  it('normalizza email e accetta una password robusta', () => {
    const result = registerSchema.parse({
      nome: 'Mario',
      cognome: 'Rossi',
      email: ' Mario.Rossi@Example.com ',
      password: 'Sicura12345',
      idQuartiere: ''
    });
    expect(result.email).toBe('mario.rossi@example.com');
    expect(result.idQuartiere).toBeNull();
  });

  it('rifiuta password deboli', () => {
    expect(registerSchema.safeParse({
      nome: 'Mario', cognome: 'Rossi', email: 'mario@example.com', password: 'password'
    }).success).toBe(false);
  });
});

describe('createReportSchema', () => {
  const valid = {
    tipo: 'segnalazione',
    titolo: 'Buca sul marciapiede',
    descrizione: 'La buca rende difficile e pericoloso il passaggio dei pedoni.',
    idQuartiere: '1',
    latitudine: '45.4642',
    longitudine: '9.1900',
    indirizzo: 'Via Torino, Milano',
    descrizioneAccessibile: 'Una buca profonda al centro del marciapiede.',
    categorie: '[1,3]'
  };

  it('converte i campi multipart', () => {
    const result = createReportSchema.parse(valid);
    expect(result.categorie).toEqual([1, 3]);
    expect(result.latitudine).toBe(45.4642);
  });

  it('richiede entrambe le coordinate', () => {
    expect(createReportSchema.safeParse({ ...valid, longitudine: '' }).success).toBe(false);
  });
});

describe('reportListSchema', () => {
  it('limita paginazione e ordinamento', () => {
    const result = reportListSchema.parse({ pagina: '2', limite: '12', ordine: 'sostenute' });
    expect(result).toMatchObject({ pagina: 2, limite: 12, ordine: 'sostenute' });
  });
});
