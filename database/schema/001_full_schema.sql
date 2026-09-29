CREATE DATABASE IF NOT EXISTS nostra_citta
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE nostra_citta;

CREATE TABLE IF NOT EXISTS QUARTIERE (
  IdQuartiere INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  Nome VARCHAR(100) NOT NULL,
  Municipio TINYINT UNSIGNED NULL,
  Attivo BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT uq_quartiere_nome UNIQUE (Nome),
  CONSTRAINT chk_quartiere_municipio CHECK (Municipio IS NULL OR Municipio BETWEEN 1 AND 9)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS STATO_SEGNALAZIONE (
  Codice VARCHAR(30) PRIMARY KEY,
  Etichetta VARCHAR(60) NOT NULL,
  Ordine TINYINT UNSIGNED NOT NULL,
  StatoFinale BOOLEAN NOT NULL DEFAULT FALSE,
  CONSTRAINT uq_stato_ordine UNIQUE (Ordine)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS CATEGORIA (
  IdCategoria INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  Nome VARCHAR(100) NOT NULL,
  Descrizione VARCHAR(500) NULL,
  Colore CHAR(7) NOT NULL DEFAULT '#176B5B',
  Attiva BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT uq_categoria_nome UNIQUE (Nome),
  CONSTRAINT chk_categoria_colore CHECK (Colore REGEXP '^#[0-9A-Fa-f]{6}$')
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS UTENTE (
  IdUtente INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  IdQuartiere INT UNSIGNED NULL,
  Nome VARCHAR(100) NOT NULL,
  Cognome VARCHAR(100) NOT NULL,
  Email VARCHAR(254) NOT NULL,
  HashPassword VARCHAR(255) NOT NULL,
  DataRegistrazione DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  StatoAccount VARCHAR(30) NOT NULL DEFAULT 'attivo',
  DataCancellazione DATETIME NULL,
  CONSTRAINT uq_utente_email UNIQUE (Email),
  CONSTRAINT fk_utente_quartiere FOREIGN KEY (IdQuartiere) REFERENCES QUARTIERE (IdQuartiere),
  CONSTRAINT chk_utente_stato CHECK (StatoAccount IN ('attivo', 'bloccato', 'cancellato'))
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS MODERATORE (
  IdUtente INT UNSIGNED PRIMARY KEY,
  LivelloPermessi VARCHAR(50) NOT NULL,
  DataAbilitazione DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_moderatore_utente FOREIGN KEY (IdUtente) REFERENCES UTENTE (IdUtente),
  CONSTRAINT chk_moderatore_livello CHECK (LivelloPermessi IN ('base', 'amministratore'))
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS SEGNALAZIONE (
  IdSegnalazione INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  IdAutore INT UNSIGNED NOT NULL,
  IdQuartiere INT UNSIGNED NULL,
  Tipo VARCHAR(30) NOT NULL,
  Titolo VARCHAR(200) NOT NULL,
  Descrizione TEXT NOT NULL,
  DataCreazione DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  DataAggiornamento DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  Stato VARCHAR(30) NOT NULL DEFAULT 'nuova',
  Visibilita VARCHAR(30) NOT NULL DEFAULT 'pubblica',
  Latitudine DECIMAL(9,6) NULL,
  Longitudine DECIMAL(9,6) NULL,
  Indirizzo VARCHAR(255) NULL,
  CONSTRAINT fk_segnalazione_autore FOREIGN KEY (IdAutore) REFERENCES UTENTE (IdUtente),
  CONSTRAINT fk_segnalazione_quartiere FOREIGN KEY (IdQuartiere) REFERENCES QUARTIERE (IdQuartiere),
  CONSTRAINT fk_segnalazione_stato FOREIGN KEY (Stato) REFERENCES STATO_SEGNALAZIONE (Codice),
  CONSTRAINT chk_segnalazione_tipo CHECK (Tipo IN ('segnalazione', 'proposta')),
  CONSTRAINT chk_segnalazione_visibilita CHECK (Visibilita IN ('bozza', 'pubblica', 'nascosta', 'rimossa')),
  CONSTRAINT chk_segnalazione_latitudine CHECK (Latitudine IS NULL OR Latitudine BETWEEN -90 AND 90),
  CONSTRAINT chk_segnalazione_longitudine CHECK (Longitudine IS NULL OR Longitudine BETWEEN -180 AND 180),
  INDEX idx_segnalazione_home (Visibilita, Stato, DataCreazione),
  INDEX idx_segnalazione_autore (IdAutore),
  INDEX idx_segnalazione_quartiere (IdQuartiere),
  INDEX idx_segnalazione_coordinate (Latitudine, Longitudine),
  FULLTEXT INDEX ftx_segnalazione_testo (Titolo, Descrizione)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS ALLEGATO (
  IdAllegato INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  IdSegnalazione INT UNSIGNED NOT NULL,
  IdAutore INT UNSIGNED NOT NULL,
  TipoMedia VARCHAR(100) NOT NULL,
  RiferimentoFile VARCHAR(2048) NOT NULL,
  NomeOriginale VARCHAR(255) NULL,
  DimensioneByte INT UNSIGNED NULL,
  HashSHA256 CHAR(64) NULL,
  DescrizioneAccessibile TEXT NOT NULL,
  DataCaricamento DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_allegato_segnalazione FOREIGN KEY (IdSegnalazione) REFERENCES SEGNALAZIONE (IdSegnalazione),
  CONSTRAINT fk_allegato_autore FOREIGN KEY (IdAutore) REFERENCES UTENTE (IdUtente),
  CONSTRAINT uq_allegato_riferimento UNIQUE (RiferimentoFile),
  INDEX idx_allegato_segnalazione (IdSegnalazione)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS SEGNALAZIONE_CATEGORIA (
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

CREATE TABLE IF NOT EXISTS COMMENTO (
  IdCommento INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  IdAutore INT UNSIGNED NOT NULL,
  IdSegnalazione INT UNSIGNED NOT NULL,
  Testo TEXT NOT NULL,
  DataPubblicazione DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  Visibilita VARCHAR(30) NOT NULL DEFAULT 'pubblica',
  CONSTRAINT fk_commento_autore FOREIGN KEY (IdAutore) REFERENCES UTENTE (IdUtente),
  CONSTRAINT fk_commento_segnalazione FOREIGN KEY (IdSegnalazione) REFERENCES SEGNALAZIONE (IdSegnalazione),
  CONSTRAINT chk_commento_visibilita CHECK (Visibilita IN ('pubblica', 'nascosta', 'rimossa')),
  INDEX idx_commento_segnalazione (IdSegnalazione, Visibilita, DataPubblicazione)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS SOSTEGNO (
  IdSostegno INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  IdUtente INT UNSIGNED NOT NULL,
  IdSegnalazione INT UNSIGNED NOT NULL,
  DataEspressione DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  DataRitiro DATETIME NULL,
  CONSTRAINT uq_sostegno_utente_segnalazione UNIQUE (IdUtente, IdSegnalazione),
  CONSTRAINT fk_sostegno_utente FOREIGN KEY (IdUtente) REFERENCES UTENTE (IdUtente),
  CONSTRAINT fk_sostegno_segnalazione FOREIGN KEY (IdSegnalazione) REFERENCES SEGNALAZIONE (IdSegnalazione),
  INDEX idx_sostegno_classifica (IdSegnalazione, DataRitiro)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS STORICO_STATO (
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

CREATE TABLE IF NOT EXISTS VERIFICA_IDENTITA (
  IdVerifica INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  IdUtente INT UNSIGNED NOT NULL,
  Metodo VARCHAR(30) NOT NULL,
  RiferimentoVerifica VARCHAR(255) NOT NULL,
  DataVerifica DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  Esito VARCHAR(30) NOT NULL,
  CONSTRAINT fk_verifica_utente FOREIGN KEY (IdUtente) REFERENCES UTENTE (IdUtente),
  INDEX idx_verifica_utente (IdUtente, DataVerifica)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS BLOCCO (
  IdBlocco INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  IdUtenteBloccato INT UNSIGNED NOT NULL,
  IdModeratore INT UNSIGNED NOT NULL,
  Motivazione TEXT NOT NULL,
  DataInizio DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  DataFinePrevista DATETIME NULL,
  IdModeratoreRevoca INT UNSIGNED NULL,
  DataRevoca DATETIME NULL,
  MotivoRevoca TEXT NULL,
  CONSTRAINT fk_blocco_utente FOREIGN KEY (IdUtenteBloccato) REFERENCES UTENTE (IdUtente),
  CONSTRAINT fk_blocco_moderatore FOREIGN KEY (IdModeratore) REFERENCES MODERATORE (IdUtente),
  CONSTRAINT fk_blocco_moderatore_revoca FOREIGN KEY (IdModeratoreRevoca) REFERENCES MODERATORE (IdUtente),
  CONSTRAINT chk_blocco_date CHECK (DataFinePrevista IS NULL OR DataFinePrevista > DataInizio),
  INDEX idx_blocco_attivo (IdUtenteBloccato, DataRevoca, DataFinePrevista)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS ANALISI_IA (
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

CREATE TABLE IF NOT EXISTS EVENTO_LOG (
  IdEvento INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  IdEsecutore INT UNSIGNED NULL,
  TipoAzione VARCHAR(100) NOT NULL,
  DataOra DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  Esito VARCHAR(30) NOT NULL,
  Dettagli TEXT NOT NULL,
  IdUtenteBersaglio INT UNSIGNED NULL,
  IdSegnalazione INT UNSIGNED NULL,
  IdCommento INT UNSIGNED NULL,
  IdAllegato INT UNSIGNED NULL,
  IdSostegno INT UNSIGNED NULL,
  IdBlocco INT UNSIGNED NULL,
  IdVerifica INT UNSIGNED NULL,
  CONSTRAINT fk_evento_esecutore FOREIGN KEY (IdEsecutore) REFERENCES UTENTE (IdUtente),
  CONSTRAINT fk_evento_utente_bersaglio FOREIGN KEY (IdUtenteBersaglio) REFERENCES UTENTE (IdUtente),
  CONSTRAINT fk_evento_segnalazione FOREIGN KEY (IdSegnalazione) REFERENCES SEGNALAZIONE (IdSegnalazione),
  CONSTRAINT fk_evento_commento FOREIGN KEY (IdCommento) REFERENCES COMMENTO (IdCommento),
  CONSTRAINT fk_evento_allegato FOREIGN KEY (IdAllegato) REFERENCES ALLEGATO (IdAllegato),
  CONSTRAINT fk_evento_sostegno FOREIGN KEY (IdSostegno) REFERENCES SOSTEGNO (IdSostegno),
  CONSTRAINT fk_evento_blocco FOREIGN KEY (IdBlocco) REFERENCES BLOCCO (IdBlocco),
  CONSTRAINT fk_evento_verifica FOREIGN KEY (IdVerifica) REFERENCES VERIFICA_IDENTITA (IdVerifica),
  INDEX idx_evento_data (DataOra),
  INDEX idx_evento_esecutore (IdEsecutore)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS VARIAZIONE_LOG (
  IdEvento INT UNSIGNED NOT NULL,
  NomeCampo VARCHAR(100) NOT NULL,
  ValorePrecedente LONGTEXT NULL,
  ValoreSuccessivo LONGTEXT NULL,
  PRIMARY KEY (IdEvento, NomeCampo),
  CONSTRAINT fk_variazione_evento FOREIGN KEY (IdEvento) REFERENCES EVENTO_LOG (IdEvento) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS SESSIONE_WEB (
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
