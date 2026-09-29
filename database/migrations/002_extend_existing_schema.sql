-- Migrazione una tantum per il database creato con lo script iniziale fornito.
-- Eseguire prima un backup e poi database/seeds/001_reference_data.sql.
USE nostra_citta;

CREATE TABLE QUARTIERE (
  IdQuartiere INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  Nome VARCHAR(100) NOT NULL,
  Municipio TINYINT UNSIGNED NULL,
  Attivo BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT uq_quartiere_nome UNIQUE (Nome),
  CONSTRAINT chk_quartiere_municipio CHECK (Municipio IS NULL OR Municipio BETWEEN 1 AND 9)
) ENGINE=InnoDB;

CREATE TABLE STATO_SEGNALAZIONE (
  Codice VARCHAR(30) PRIMARY KEY,
  Etichetta VARCHAR(60) NOT NULL,
  Ordine TINYINT UNSIGNED NOT NULL,
  StatoFinale BOOLEAN NOT NULL DEFAULT FALSE,
  CONSTRAINT uq_stato_ordine UNIQUE (Ordine)
) ENGINE=InnoDB;

INSERT INTO STATO_SEGNALAZIONE (Codice, Etichetta, Ordine, StatoFinale) VALUES
  ('nuova', 'Nuova', 10, FALSE),
  ('aperta', 'Aperta', 20, FALSE),
  ('in_valutazione', 'In valutazione', 30, FALSE),
  ('in_lavorazione', 'In lavorazione', 40, FALSE),
  ('presa_in_carico', 'Presa in carico', 50, FALSE),
  ('risolta', 'Risolta', 60, TRUE),
  ('chiusa', 'Chiusa', 70, TRUE);

CREATE TABLE CATEGORIA (
  IdCategoria INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  Nome VARCHAR(100) NOT NULL,
  Descrizione VARCHAR(500) NULL,
  Colore CHAR(7) NOT NULL DEFAULT '#176B5B',
  Attiva BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT uq_categoria_nome UNIQUE (Nome),
  CONSTRAINT chk_categoria_colore CHECK (Colore REGEXP '^#[0-9A-Fa-f]{6}$')
) ENGINE=InnoDB;

ALTER TABLE UTENTE
  ADD COLUMN IdQuartiere INT UNSIGNED NULL AFTER IdUtente,
  ADD CONSTRAINT fk_utente_quartiere FOREIGN KEY (IdQuartiere) REFERENCES QUARTIERE (IdQuartiere),
  ADD CONSTRAINT chk_utente_stato CHECK (StatoAccount IN ('attivo', 'bloccato', 'cancellato'));

ALTER TABLE SEGNALAZIONE
  ADD COLUMN IdQuartiere INT UNSIGNED NULL AFTER IdAutore,
  ADD COLUMN DataAggiornamento DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER DataCreazione,
  ADD CONSTRAINT fk_segnalazione_quartiere FOREIGN KEY (IdQuartiere) REFERENCES QUARTIERE (IdQuartiere),
  ADD CONSTRAINT fk_segnalazione_stato FOREIGN KEY (Stato) REFERENCES STATO_SEGNALAZIONE (Codice),
  ADD CONSTRAINT chk_segnalazione_tipo CHECK (Tipo IN ('segnalazione', 'proposta')),
  ADD CONSTRAINT chk_segnalazione_visibilita CHECK (Visibilita IN ('bozza', 'pubblica', 'nascosta', 'rimossa')),
  ADD CONSTRAINT chk_segnalazione_latitudine CHECK (Latitudine IS NULL OR Latitudine BETWEEN -90 AND 90),
  ADD CONSTRAINT chk_segnalazione_longitudine CHECK (Longitudine IS NULL OR Longitudine BETWEEN -180 AND 180),
  ADD INDEX idx_segnalazione_home (Visibilita, Stato, DataCreazione),
  ADD INDEX idx_segnalazione_quartiere (IdQuartiere),
  ADD INDEX idx_segnalazione_coordinate (Latitudine, Longitudine),
  ADD FULLTEXT INDEX ftx_segnalazione_testo (Titolo, Descrizione);

ALTER TABLE ALLEGATO
  ADD COLUMN NomeOriginale VARCHAR(255) NULL AFTER RiferimentoFile,
  ADD COLUMN DimensioneByte INT UNSIGNED NULL AFTER NomeOriginale,
  ADD COLUMN HashSHA256 CHAR(64) NULL AFTER DimensioneByte,
  ADD CONSTRAINT uq_allegato_riferimento UNIQUE (RiferimentoFile),
  ADD INDEX idx_allegato_segnalazione (IdSegnalazione);

ALTER TABLE COMMENTO
  ADD CONSTRAINT chk_commento_visibilita CHECK (Visibilita IN ('pubblica', 'nascosta', 'rimossa')),
  ADD INDEX idx_commento_segnalazione (IdSegnalazione, Visibilita, DataPubblicazione);

ALTER TABLE SOSTEGNO
  ADD INDEX idx_sostegno_classifica (IdSegnalazione, DataRitiro);

ALTER TABLE BLOCCO
  ADD CONSTRAINT chk_blocco_date CHECK (DataFinePrevista IS NULL OR DataFinePrevista > DataInizio),
  ADD INDEX idx_blocco_attivo (IdUtenteBloccato, DataRevoca, DataFinePrevista);

ALTER TABLE EVENTO_LOG
  ADD INDEX idx_evento_data (DataOra),
  ADD INDEX idx_evento_esecutore (IdEsecutore);

CREATE TABLE SEGNALAZIONE_CATEGORIA (
  IdSegnalazione INT UNSIGNED NOT NULL,
  IdCategoria INT UNSIGNED NOT NULL,
  Origine VARCHAR(20) NOT NULL DEFAULT 'utente',
  Confidenza DECIMAL(5,4) NULL,
  PRIMARY KEY (IdSegnalazione, IdCategoria),
  CONSTRAINT fk_sc_segnalazione FOREIGN KEY (IdSegnalazione) REFERENCES SEGNALAZIONE (IdSegnalazione) ON DELETE CASCADE,
  CONSTRAINT fk_sc_categoria FOREIGN KEY (IdCategoria) REFERENCES CATEGORIA (IdCategoria),
  CONSTRAINT chk_sc_origine CHECK (Origine IN ('utente', 'ia', 'moderatore')),
  CONSTRAINT chk_sc_confidenza CHECK (Confidenza IS NULL OR Confidenza BETWEEN 0 AND 1),
  INDEX idx_sc_categoria (IdCategoria)
) ENGINE=InnoDB;

CREATE TABLE STORICO_STATO (
  IdStorico INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  IdSegnalazione INT UNSIGNED NOT NULL,
  StatoPrecedente VARCHAR(30) NULL,
  StatoSuccessivo VARCHAR(30) NOT NULL,
  IdAutoreModifica INT UNSIGNED NOT NULL,
  Motivazione VARCHAR(500) NULL,
  DataModifica DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_storico_segnalazione FOREIGN KEY (IdSegnalazione) REFERENCES SEGNALAZIONE (IdSegnalazione),
  CONSTRAINT fk_storico_stato_precedente FOREIGN KEY (StatoPrecedente) REFERENCES STATO_SEGNALAZIONE (Codice),
  CONSTRAINT fk_storico_stato_successivo FOREIGN KEY (StatoSuccessivo) REFERENCES STATO_SEGNALAZIONE (Codice),
  CONSTRAINT fk_storico_autore FOREIGN KEY (IdAutoreModifica) REFERENCES UTENTE (IdUtente),
  INDEX idx_storico_segnalazione (IdSegnalazione, DataModifica)
) ENGINE=InnoDB;

CREATE TABLE ANALISI_IA (
  IdAnalisi INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  IdSegnalazione INT UNSIGNED NOT NULL,
  IdAllegato INT UNSIGNED NULL,
  TipoAnalisi VARCHAR(40) NOT NULL,
  Modello VARCHAR(120) NOT NULL,
  VersioneModello VARCHAR(80) NULL,
  Esito VARCHAR(40) NOT NULL,
  Confidenza DECIMAL(5,4) NULL,
  Risultato JSON NULL,
  StatoRevisione VARCHAR(30) NOT NULL DEFAULT 'da_revisionare',
  IdModeratoreRevisione INT UNSIGNED NULL,
  DataAnalisi DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  DataRevisione DATETIME NULL,
  CONSTRAINT fk_analisi_segnalazione FOREIGN KEY (IdSegnalazione) REFERENCES SEGNALAZIONE (IdSegnalazione),
  CONSTRAINT fk_analisi_allegato FOREIGN KEY (IdAllegato) REFERENCES ALLEGATO (IdAllegato),
  CONSTRAINT fk_analisi_moderatore FOREIGN KEY (IdModeratoreRevisione) REFERENCES MODERATORE (IdUtente),
  CONSTRAINT chk_analisi_confidenza CHECK (Confidenza IS NULL OR Confidenza BETWEEN 0 AND 1),
  INDEX idx_analisi_revisione (StatoRevisione, DataAnalisi)
) ENGINE=InnoDB;

CREATE TABLE SESSIONE_WEB (
  IdSessione VARCHAR(128) PRIMARY KEY,
  Scadenza BIGINT UNSIGNED NOT NULL,
  Dati LONGTEXT NOT NULL,
  INDEX idx_sessione_scadenza (Scadenza)
) ENGINE=InnoDB;

CREATE OR REPLACE VIEW V_CLASSIFICA_SEGNALAZIONI AS
SELECT
  s.IdSegnalazione,
  s.Titolo,
  s.Tipo,
  s.Stato,
  s.IdQuartiere,
  s.DataCreazione,
  COUNT(so.IdSostegno) AS NumeroSostegni
FROM SEGNALAZIONE s
LEFT JOIN SOSTEGNO so
  ON so.IdSegnalazione = s.IdSegnalazione
 AND so.DataRitiro IS NULL
WHERE s.Visibilita = 'pubblica'
GROUP BY s.IdSegnalazione, s.Titolo, s.Tipo, s.Stato, s.IdQuartiere, s.DataCreazione;
