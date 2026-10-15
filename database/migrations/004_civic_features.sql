-- Eseguire UNA volta su Aiven dopo un backup e dopo le migrazioni 002/003.
-- Non modifica contenuti esistenti; il codice richiede queste colonne.
USE nostra_citta;

ALTER TABLE UTENTE
  ADD COLUMN Bio VARCHAR(500) NOT NULL DEFAULT '',
  ADD COLUMN NotificheEmail BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN AvatarRiferimento VARCHAR(255) NULL,
  ADD COLUMN SessionVersion INT UNSIGNED NOT NULL DEFAULT 0;

ALTER TABLE SEGNALAZIONE
  ADD INDEX idx_segnalazione_coda (Visibilita, IdSegnalazione);
