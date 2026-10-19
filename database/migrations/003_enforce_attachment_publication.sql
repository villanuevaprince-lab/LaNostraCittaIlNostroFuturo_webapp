-- Applicare manualmente DOPO 002_extend_existing_schema.sql, con backup.
-- MySQL 8.0.16+; non idempotente. Le segnalazioni pubbliche preesistenti
-- senza allegato vanno sanate prima di considerare completo il vincolo.
USE nostra_citta;

DELIMITER //
CREATE TRIGGER trg_segnalazione_prima_insert
BEFORE INSERT ON SEGNALAZIONE FOR EACH ROW
BEGIN
  IF NEW.Visibilita = 'pubblica' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Pubblicare solo dopo aver inserito un allegato';
  END IF;
END//

CREATE TRIGGER trg_segnalazione_prima_update
BEFORE UPDATE ON SEGNALAZIONE FOR EACH ROW
BEGIN
  IF NEW.Visibilita = 'pubblica' AND OLD.Visibilita <> 'pubblica'
     AND NOT EXISTS (SELECT 1 FROM ALLEGATO WHERE IdSegnalazione = OLD.IdSegnalazione) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Segnalazione senza allegato';
  END IF;
END//

CREATE TRIGGER trg_allegato_prima_delete
BEFORE DELETE ON ALLEGATO FOR EACH ROW
BEGIN
  IF EXISTS (SELECT 1 FROM SEGNALAZIONE
             WHERE IdSegnalazione = OLD.IdSegnalazione AND Visibilita = 'pubblica')
     AND (SELECT COUNT(*) FROM ALLEGATO WHERE IdSegnalazione = OLD.IdSegnalazione) <= 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Ultimo allegato di una segnalazione pubblica';
  END IF;
END//

CREATE TRIGGER trg_allegato_prima_update
BEFORE UPDATE ON ALLEGATO FOR EACH ROW
BEGIN
  IF NEW.IdSegnalazione <> OLD.IdSegnalazione
     AND EXISTS (SELECT 1 FROM SEGNALAZIONE
                 WHERE IdSegnalazione = OLD.IdSegnalazione AND Visibilita = 'pubblica')
     AND (SELECT COUNT(*) FROM ALLEGATO WHERE IdSegnalazione = OLD.IdSegnalazione) <= 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Ultimo allegato di una segnalazione pubblica';
  END IF;
END//
DELIMITER ;
