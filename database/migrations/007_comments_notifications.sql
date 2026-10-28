-- Applicare dopo la migrazione 006, una sola volta.
ALTER TABLE COMMENTO ADD COLUMN IdCommentoPadre INT UNSIGNED NULL,
 ADD CONSTRAINT fk_comment_parent FOREIGN KEY (IdCommentoPadre) REFERENCES COMMENTO(IdCommento),
 ADD INDEX ix_comment_thread (IdSegnalazione, IdCommentoPadre, IdCommento);
CREATE TABLE NOTIFICA (
 IdNotifica BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 IdDestinatario INT UNSIGNED NOT NULL,
 IdSegnalazione INT UNSIGNED NOT NULL,
 IdCommento INT UNSIGNED NULL,
 Tipo VARCHAR(40) NOT NULL,
 Letta BOOLEAN NOT NULL DEFAULT FALSE,
 DataCreazione DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY (IdDestinatario) REFERENCES UTENTE(IdUtente),
 FOREIGN KEY (IdSegnalazione) REFERENCES SEGNALAZIONE(IdSegnalazione),
 FOREIGN KEY (IdCommento) REFERENCES COMMENTO(IdCommento),
 INDEX ix_notification_inbox (IdDestinatario, IdNotifica),
 INDEX ix_notification_unread (IdDestinatario, Letta, IdNotifica)
) ENGINE=InnoDB;
