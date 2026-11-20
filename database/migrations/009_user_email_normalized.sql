-- 009: email personali reali, normalizzate e univoche senza distinzione di maiuscole.
-- 1) normalizza gli indirizzi esistenti (spazi e maiuscole);
-- 2) fissa la collation utf8mb4_0900_ai_ci sulla colonna (confronto case-insensitive);
-- 3) un CHECK confronta i byte (BINARY) perché con una collation _ci 'A' = 'a' sarebbe sempre vero.
-- La UNIQUE uq_utente_email esistente resta e diventa case-insensitive con la nuova collation.
-- Prima di applicarla controlla i duplicati: python -m backend.apply_email_migration lo fa e si ferma.
-- Richiede MySQL 8.0.16 o successivo. Non rilanciare se già applicata.

UPDATE UTENTE SET Email = LOWER(TRIM(Email));

ALTER TABLE UTENTE
  MODIFY Email VARCHAR(254) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL;

ALTER TABLE UTENTE
  ADD CONSTRAINT chk_utente_email_normalizzata
  CHECK (CAST(Email AS BINARY) = CAST(LOWER(TRIM(Email)) AS BINARY) AND Email LIKE '%_@_%');
