from backend.database import database_cursor


def list_neighborhoods():
    with database_cursor() as cursor:
        cursor.execute("""SELECT IdQuartiere AS id, Nome AS nome, Municipio AS municipio
                          FROM QUARTIERE WHERE Attivo = TRUE ORDER BY Nome""")
        return cursor.fetchall()


def list_categories():
    with database_cursor() as cursor:
        cursor.execute("""SELECT IdCategoria AS id, Nome AS nome, Descrizione AS descrizione,
                                 Colore AS colore
                          FROM CATEGORIA WHERE Attiva = TRUE ORDER BY Nome""")
        return cursor.fetchall()


def valid_neighborhood(neighborhood_id):
    with database_cursor() as cursor:
        cursor.execute("SELECT 1 FROM QUARTIERE WHERE IdQuartiere = %s AND Attivo = TRUE",
                       (neighborhood_id,))
        return cursor.fetchone() is not None


def valid_categories(category_ids):
    if not category_ids:
        return True
    marks = ",".join(["%s"] * len(category_ids))
    with database_cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) AS totale FROM CATEGORIA WHERE Attiva = TRUE AND IdCategoria IN ({marks})",
                       tuple(category_ids))
        return cursor.fetchone()["totale"] == len(set(category_ids))
