-- Eseguire una volta su Aiven dopo 002/003/004 e un backup.
-- Gli upload nuovi sono registrati qui insieme alla segnalazione, nella stessa transazione.
-- I file precedenti richiedono il backfill dal disco che li contiene.
CREATE TABLE IF NOT EXISTS ALLEGATO_CONTENUTO (
    IdAllegato INT UNSIGNED NOT NULL,
    Numero SMALLINT UNSIGNED NOT NULL,
    Dati MEDIUMBLOB NOT NULL,
    PRIMARY KEY (IdAllegato, Numero),
    CONSTRAINT fk_allegato_contenuto_allegato
        FOREIGN KEY (IdAllegato) REFERENCES ALLEGATO (IdAllegato)
        ON DELETE CASCADE
) ENGINE=InnoDB;
