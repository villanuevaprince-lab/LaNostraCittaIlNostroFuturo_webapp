"""88 NIL vigenti del Comune di Milano (DS964, PGT 2030).

L'ID è quello del dataset pubblico, usato soltanto dalla modalità demo.
Nel DB esistente l'IdQuartiere è una chiave autonumerata distinta.
Fonte: https://dati.comune.milano.it/dataset/e8e765fc-d882-40b8-95d8-16ff3d39eb7c
"""

MILAN_NIL = (
    "Duomo", "Brera", "Giardini P.ta Venezia", "Guastalla",
    "Porta Vigentina - Porta Lodovica", "Porta Ticinese - Conca del Naviglio",
    "Magenta - S. Vittore", "Parco Sempione", "Porta Garibaldi - Porta Nuova",
    "Stazione Centrale - Ponte Seveso", "Isola", "Maciachini - Maggiolina",
    "Greco - Segnano", "Niguarda - Ca' Granda - Prato Centenaro - Q.re Fulvio Testi",
    "Bicocca", "Gorla - Precotto", "Adriano",
    "Cimiano - Rottole - Q.re Feltre", "Padova - Turro - Crescenzago",
    "Loreto - Casoretto - Nolo", "Buenos Aires - Porta Venezia - Porta Monforte",
    "Città Studi", "Lambrate - Ortica", "Parco Forlanini - Cavriano",
    "Corsica", "XXII Marzo", "P.ta Romana", "Umbria - Molise - Calvairate",
    "Ortomercato", "Taliedo - Morsenchio - Q.re Forlanini",
    "Monluè - Ponte Lambro", "Triulzo Superiore", "Rogoredo - Santa Giulia",
    "Chiaravalle", "Lodi - Corvetto", "Scalo Romana", "Morivione",
    "Vigentino - Q.re Fatima", "Quintosole", "Ronchetto delle Rane",
    "Gratosoglio - Q.re Missaglia - Q.re Terrazze",
    "Stadera - Chiesa Rossa - Q.re Torretta - Conca Fallata", "Tibaldi",
    "Porta Ticinese - Conchetta", "Moncucco - San Cristoforo", "Barona",
    "Cantalupa", "Ronchetto sul Naviglio - Q.re Lodovico il Moro",
    "Giambellino", "Porta Genova", "Porta Magenta", "Bande Nere",
    "Lorenteggio", "Muggiano", "Baggio - Q.re degli Olmi - Q.re Valsesia",
    "Forze Armate", "San Siro", "De Angeli - Monte Rosa", "Tre Torri",
    "Stadio - Ippodromi", "Quarto Cagnino", "Quinto Romano", "Figino",
    "Trenno", "Q.re Gallaratese - Q.re San Leonardo - Lampugnano",
    "QT 8", "Portello", "Pagano", "Sarpi", "Ghisolfa",
    "Villapizzone - Cagnola - Boldinasco", "Maggiore - Musocco - Certosa",
    "Cascina Merlata", "Roserio", "Stephenson",
    "Quarto Oggiaro - Vialba - Musocco", "Bovisa", "Farini", "Dergano",
    "Affori", "Bovisasca", "Comasina", "Bruzzano", "Parco Nord",
    "Parco delle Abbazie", "Parco dei Navigli", "Assiano",
    "Parco Bosco in Città",
)

assert len(MILAN_NIL) == 88 and len(set(MILAN_NIL)) == 88
