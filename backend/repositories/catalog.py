from backend.database import database_cursor, database_enabled, demo_store


def list_neighborhoods():
    if not database_enabled():
        return demo_store()["quartieri"]
    with database_cursor() as cursor:
        cursor.execute("""SELECT IdQuartiere AS id, Nome AS nome, Municipio AS municipio
                          FROM QUARTIERE WHERE Attivo = TRUE ORDER BY Nome""")
        return cursor.fetchall()


def list_categories():
    if not database_enabled():
        return demo_store()["categorie"]
    with database_cursor() as cursor:
        cursor.execute("""SELECT IdCategoria AS id, Nome AS nome, Descrizione AS descrizione,
                                 Colore AS colore
                          FROM CATEGORIA WHERE Attiva = TRUE ORDER BY Nome""")
        return cursor.fetchall()


def valid_neighborhood(neighborhood_id):
    if not database_enabled():
        return any(str(item["id"]) == str(neighborhood_id) for item in demo_store()["quartieri"])
    with database_cursor() as cursor:
        cursor.execute("SELECT 1 FROM QUARTIERE WHERE IdQuartiere = %s AND Attivo = TRUE",
                       (neighborhood_id,))
        return cursor.fetchone() is not None


def valid_categories(category_ids):
    if not database_enabled():
        allowed = {str(item["id"]) for item in demo_store()["categorie"]}
        return all(str(item) in allowed for item in category_ids)
    if not category_ids:
        return True
    marks = ",".join(["%s"] * len(category_ids))
    with database_cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) AS totale FROM CATEGORIA WHERE Attiva = TRUE AND IdCategoria IN ({marks})",
                       tuple(category_ids))
        return cursor.fetchone()["totale"] == len(set(category_ids))
