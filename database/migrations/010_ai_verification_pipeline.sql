-- 010: pipeline di verifica AI prima della pubblicazione.
-- Ogni nuova segnalazione o proposta resta non pubblica (Visibilita='bozza') finché la verifica
-- non la pubblica. StatoVerifica è separato da Stato (ciclo di vita civico) per non confondere
-- la verifica con lo stato 'in_valutazione' delle proposte esaminate dal comitato.
-- Richiede MySQL 8.0.16+ (CHECK) e 8.0.1+ (SKIP LOCKED). Applicare dopo 009, una sola volta:
--   python -m backend.apply_verification_migration

ALTER TABLE SEGNALAZIONE
  ADD COLUMN StatoVerifica VARCHAR(30) NOT NULL DEFAULT 'pubblicata',
  ADD COLUMN VersioneInvio SMALLINT UNSIGNED NOT NULL DEFAULT 1,
  ADD COLUMN Reinvii TINYINT UNSIGNED NOT NULL DEFAULT 0,
  ADD COLUMN Ricorsi TINYINT UNSIGNED NOT NULL DEFAULT 0,
  ADD COLUMN MotivazioneVerifica VARCHAR(1000) NULL,
  ADD CONSTRAINT chk_segnalazione_stato_verifica CHECK (StatoVerifica IN (
    'in_valutazione', 'in_attesa_modello', 'pubblicata', 'respinta_automatica',
    'respinta_moderatore', 'da_revisionare', 'in_ricorso')),
  ADD INDEX idx_segnalazione_verifica (StatoVerifica, IdSegnalazione);

-- I contenuti già pubblicati restano 'pubblicata' (default). Le bozze della vecchia verifica
-- sincrona erano in attesa del comitato: diventano 'da_revisionare'.
UPDATE SEGNALAZIONE SET StatoVerifica = 'da_revisionare' WHERE Visibilita = 'bozza';

-- Coda persistente: sopravvive ai riavvii, il worker la legge con FOR UPDATE SKIP LOCKED.
CREATE TABLE VERIFICA_JOB (
  IdJob BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  IdSegnalazione INT UNSIGNED NOT NULL,
  VersioneInvio SMALLINT UNSIGNED NOT NULL,
  Stato VARCHAR(30) NOT NULL DEFAULT 'in_coda',
  Tentativi TINYINT UNSIGNED NOT NULL DEFAULT 0,
  ProssimoTentativo DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  AttesoModello BOOLEAN NOT NULL DEFAULT FALSE,
  Worker VARCHAR(80) NULL,
  DataCreazione DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  DataInizio DATETIME NULL,
  DataFine DATETIME NULL,
  UltimoErrore VARCHAR(1000) NULL,
  CONSTRAINT fk_job_segnalazione FOREIGN KEY (IdSegnalazione) REFERENCES SEGNALAZIONE (IdSegnalazione),
  -- Un solo job per ogni invio (o reinvio) dello stesso contenuto.
  CONSTRAINT uq_job_invio UNIQUE (IdSegnalazione, VersioneInvio),
  CONSTRAINT chk_job_stato CHECK (Stato IN (
    'in_coda', 'in_elaborazione', 'completato', 'in_attesa_modello', 'da_revisionare')),
  INDEX idx_job_coda (Stato, ProssimoTentativo, IdJob)
) ENGINE=InnoDB;

-- Risposta del modello e decisione applicata dal codice (una sola per job).
CREATE TABLE VERIFICA_ESITO (
  IdEsito BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  IdJob BIGINT UNSIGNED NOT NULL,
  IdSegnalazione INT UNSIGNED NOT NULL,
  VersioneInvio SMALLINT UNSIGNED NOT NULL,
  Modello VARCHAR(120) NOT NULL,
  EsitoSuggerito VARCHAR(20) NULL,
  Decisione VARCHAR(20) NOT NULL,
  Confidenza DECIMAL(5,4) NULL,
  Motivazione VARCHAR(1000) NOT NULL,
  NoteModeratore TEXT NULL,
  Errore VARCHAR(1000) NULL,
  DataEsito DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_esito_job FOREIGN KEY (IdJob) REFERENCES VERIFICA_JOB (IdJob),
  CONSTRAINT fk_esito_segnalazione FOREIGN KEY (IdSegnalazione) REFERENCES SEGNALAZIONE (IdSegnalazione),
  CONSTRAINT uq_esito_job UNIQUE (IdJob),
  CONSTRAINT chk_esito_suggerito CHECK (EsitoSuggerito IS NULL OR EsitoSuggerito IN ('pubblica', 'respingi', 'revisione')),
  CONSTRAINT chk_esito_decisione CHECK (Decisione IN ('pubblica', 'respingi', 'revisione')),
  CONSTRAINT chk_esito_confidenza CHECK (Confidenza IS NULL OR Confidenza BETWEEN 0 AND 1),
  INDEX idx_esito_segnalazione (IdSegnalazione, IdEsito)
) ENGINE=InnoDB;

CREATE TABLE VERIFICA_VIOLAZIONE (
  IdViolazione BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  IdEsito BIGINT UNSIGNED NOT NULL,
  Categoria VARCHAR(30) NOT NULL,
  Gravita TINYINT UNSIGNED NOT NULL,
  Spiegazione VARCHAR(500) NOT NULL,
  Origine VARCHAR(20) NOT NULL DEFAULT 'modello',
  CONSTRAINT fk_violazione_esito FOREIGN KEY (IdEsito) REFERENCES VERIFICA_ESITO (IdEsito),
  CONSTRAINT chk_violazione_categoria CHECK (Categoria IN ('coerenza', 'scopo', 'linguaggio', 'plausibilita', 'altro')),
  CONSTRAINT chk_violazione_gravita CHECK (Gravita BETWEEN 1 AND 3),
  CONSTRAINT chk_violazione_origine CHECK (Origine IN ('modello', 'filtro_linguaggio')),
  INDEX idx_violazione_esito (IdEsito)
) ENGINE=InnoDB;

-- Storico di tutte le decisioni: modello, moderatori, utente (reinvio, ricorso) e sistema.
CREATE TABLE DECISIONE_VERIFICA (
  IdDecisione BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  IdSegnalazione INT UNSIGNED NOT NULL,
  VersioneInvio SMALLINT UNSIGNED NOT NULL,
  Origine VARCHAR(20) NOT NULL,
  Azione VARCHAR(30) NOT NULL,
  StatoPrecedente VARCHAR(30) NULL,
  StatoSuccessivo VARCHAR(30) NOT NULL,
  IdUtente INT UNSIGNED NULL,
  Ribaltamento BOOLEAN NOT NULL DEFAULT FALSE,
  Motivazione VARCHAR(1000) NULL,
  DataDecisione DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_decisione_segnalazione FOREIGN KEY (IdSegnalazione) REFERENCES SEGNALAZIONE (IdSegnalazione),
  CONSTRAINT fk_decisione_utente FOREIGN KEY (IdUtente) REFERENCES UTENTE (IdUtente),
  CONSTRAINT chk_decisione_origine CHECK (Origine IN ('modello', 'moderatore', 'utente', 'sistema')),
  INDEX idx_decisione_segnalazione (IdSegnalazione, IdDecisione)
) ENGINE=InnoDB;

-- Le notifiche di esito portano la motivazione leggibile.
ALTER TABLE NOTIFICA ADD COLUMN Messaggio VARCHAR(1000) NULL;
