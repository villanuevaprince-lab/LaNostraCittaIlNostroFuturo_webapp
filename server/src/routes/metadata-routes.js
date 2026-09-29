import { Router } from 'express';
import { pool } from '../config/database.js';
import { asyncHandler } from '../utils/async-handler.js';

export const metadataRouter = Router();

metadataRouter.get('/', asyncHandler(async (_req, res) => {
  const [[quartieri], [categorie], [stati]] = await Promise.all([
    pool.execute(
      `SELECT IdQuartiere AS id, Nome AS nome, Municipio AS municipio
       FROM QUARTIERE WHERE Attivo = TRUE ORDER BY Municipio, Nome`
    ),
    pool.execute(
      `SELECT IdCategoria AS id, Nome AS nome, Descrizione AS descrizione, Colore AS colore
       FROM CATEGORIA WHERE Attiva = TRUE ORDER BY Nome`
    ),
    pool.execute(
      `SELECT Codice AS codice, Etichetta AS etichetta, Ordine AS ordine, StatoFinale AS statoFinale
       FROM STATO_SEGNALAZIONE ORDER BY Ordine`
    )
  ]);
  res.json({ quartieri, categorie, stati });
}));
