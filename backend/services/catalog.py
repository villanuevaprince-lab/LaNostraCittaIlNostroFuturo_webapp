from backend.repositories.catalog import list_categories, list_neighborhoods


def get_catalogs():
    return {"quartieri": list_neighborhoods(), "categorie": list_categories()}
