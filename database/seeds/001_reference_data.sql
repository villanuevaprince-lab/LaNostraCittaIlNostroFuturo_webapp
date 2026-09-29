USE nostra_citta;

INSERT INTO STATO_SEGNALAZIONE (Codice, Etichetta, Ordine, StatoFinale) VALUES
  ('nuova', 'Nuova', 10, FALSE),
  ('aperta', 'Aperta', 20, FALSE),
  ('in_valutazione', 'In valutazione', 30, FALSE),
  ('in_lavorazione', 'In lavorazione', 40, FALSE),
  ('presa_in_carico', 'Presa in carico', 50, FALSE),
  ('risolta', 'Risolta', 60, TRUE),
  ('chiusa', 'Chiusa', 70, TRUE)
ON DUPLICATE KEY UPDATE
  Etichetta = VALUES(Etichetta),
  Ordine = VALUES(Ordine),
  StatoFinale = VALUES(StatoFinale);

INSERT INTO CATEGORIA (Nome, Descrizione, Colore) VALUES
  ('Ambiente', 'Verde pubblico, inquinamento e tutela ambientale.', '#2E7D32'),
  ('Mobilità urbana', 'Trasporto pubblico, traffico, ciclabilità e sicurezza stradale.', '#1565C0'),
  ('Decoro urbano', 'Rifiuti, pulizia, arredo urbano e manutenzione.', '#8D6E63'),
  ('Illuminazione', 'Lampioni e sicurezza dell’illuminazione pubblica.', '#F9A825'),
  ('Politiche giovanili', 'Spazi, attività e opportunità per i giovani.', '#6A1B9A'),
  ('Accessibilità', 'Barriere architettoniche e inclusione.', '#00838F'),
  ('Sicurezza', 'Situazioni di pericolo e prevenzione.', '#C62828')
ON DUPLICATE KEY UPDATE
  Descrizione = VALUES(Descrizione),
  Colore = VALUES(Colore),
  Attiva = TRUE;

INSERT INTO QUARTIERE (Nome, Municipio) VALUES
  ('Centro Storico', 1),
  ('Stazione Centrale - Gorla - Turro - Greco - Crescenzago', 2),
  ('Città Studi - Lambrate - Venezia', 3),
  ('Vittoria - Forlanini', 4),
  ('Vigentino - Chiaravalle - Gratosoglio', 5),
  ('Barona - Lorenteggio', 6),
  ('Baggio - De Angeli - San Siro', 7),
  ('Fiera - Gallaratese - Quarto Oggiaro', 8),
  ('Stazione Garibaldi - Niguarda', 9)
ON DUPLICATE KEY UPDATE Municipio = VALUES(Municipio), Attivo = TRUE;
