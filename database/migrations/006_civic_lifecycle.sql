-- Fase 1. Eseguire una sola volta dopo 005. Lo storico conserva i codici legacy.
INSERT INTO STATO_SEGNALAZIONE (Codice, Etichetta, Ordine, StatoFinale) VALUES
 ('inviata','Inviata',80,FALSE), ('archiviata','Respinta / Archiviata',90,TRUE),
 ('approvata','Approvata',100,TRUE);
UPDATE SEGNALAZIONE SET Stato=CASE
 WHEN Tipo='proposta' AND Stato='chiusa' THEN 'archiviata'
 WHEN Tipo='proposta' AND Stato='risolta' THEN 'approvata'
 WHEN Tipo='proposta' THEN 'in_valutazione'
 WHEN Stato IN ('nuova','aperta','in_valutazione') THEN 'inviata'
 WHEN Stato='chiusa' THEN 'archiviata' ELSE Stato END;
ALTER TABLE SEGNALAZIONE
 ALTER COLUMN Stato SET DEFAULT 'inviata',
 ADD COLUMN duplicate_of_id INT UNSIGNED NULL,
 ADD CONSTRAINT fk_duplicate_report FOREIGN KEY (duplicate_of_id) REFERENCES SEGNALAZIONE(IdSegnalazione),
 ADD CONSTRAINT chk_lifecycle_type CHECK (
  (Tipo='segnalazione' AND Stato IN ('inviata','presa_in_carico','in_lavorazione','risolta','archiviata')) OR
  (Tipo='proposta' AND Stato IN ('in_valutazione','approvata','archiviata'))),
 ADD UNIQUE KEY uq_report_type (IdSegnalazione, Tipo),
 ADD INDEX ix_report_queue (Visibilita, Stato, IdSegnalazione);
CREATE TABLE DETTAGLIO_SEGNALAZIONE (
 IdSegnalazione INT UNSIGNED PRIMARY KEY,
 Tipo VARCHAR(30) NOT NULL DEFAULT 'segnalazione',
 Risoluzione TEXT NULL,
 DataRisoluzione DATETIME NULL,
 CONSTRAINT chk_detail_report CHECK (Tipo='segnalazione'),
 FOREIGN KEY (IdSegnalazione, Tipo) REFERENCES SEGNALAZIONE(IdSegnalazione, Tipo)
) ENGINE=InnoDB;
CREATE TABLE PROPOSTA (
 IdSegnalazione INT UNSIGNED PRIMARY KEY,
 Tipo VARCHAR(30) NOT NULL DEFAULT 'proposta',
 SogliaSostegni INT UNSIGNED NOT NULL DEFAULT 100,
 CONSTRAINT chk_detail_proposal CHECK (Tipo='proposta'),
 CONSTRAINT chk_proposal_threshold CHECK (SogliaSostegni BETWEEN 1 AND 1000000),
 FOREIGN KEY (IdSegnalazione, Tipo) REFERENCES SEGNALAZIONE(IdSegnalazione, Tipo)
) ENGINE=InnoDB;
INSERT INTO DETTAGLIO_SEGNALAZIONE (IdSegnalazione) SELECT IdSegnalazione FROM SEGNALAZIONE WHERE Tipo='segnalazione';
INSERT INTO PROPOSTA (IdSegnalazione) SELECT IdSegnalazione FROM SEGNALAZIONE WHERE Tipo='proposta';
ALTER TABLE ALLEGATO ADD COLUMN Ruolo VARCHAR(10) NOT NULL DEFAULT 'prima',
 ADD CONSTRAINT chk_attachment_role CHECK (Ruolo IN ('prima','dopo')),
 ADD INDEX ix_attachment_role (IdSegnalazione, Ruolo, IdAllegato);
