-- 008: analisi IA locali (Ollama).
-- ANALISI_IA esiste già dalla 002; qui si aggiungono un indice per leggere le analisi di una
-- segnalazione e un vincolo sui valori di revisione usati dall'applicazione.
-- Richiede MySQL 8.0.16 o successivo (CHECK applicati). Non rilanciare se già applicata.

ALTER TABLE ANALISI_IA
  ADD INDEX idx_analisi_segnalazione (IdSegnalazione, TipoAnalisi);

ALTER TABLE ANALISI_IA
  ADD CONSTRAINT chk_analisi_revisione
  CHECK (StatoRevisione IN ('da_revisionare', 'confermata', 'respinta', 'non_necessaria'));
