"""Mappa della homepage: endpoint leggero, elementi senza coordinate, pagina."""
from decimal import Decimal
from unittest.mock import Mock

from backend.repositories.reports import list_map_items


def test_map_endpoint_is_public_and_light(client, monkeypatch):
    from backend import reports
    payload = {"items": [{"id": 3, "tipo": "proposta", "titolo": "Più alberi", "stato": "in_valutazione",
                          "lat": 45.47, "lng": 9.18}], "senza_coordinate": 2, "troncato": False}
    monkeypatch.setattr(reports, "list_map_items", Mock(return_value=payload))
    response = client.get("/api/map-items")
    assert response.status_code == 200 and response.get_json() == payload
    assert set(response.get_json()["items"][0]) == {"id", "tipo", "titolo", "stato", "lat", "lng"}


def test_map_query_skips_missing_coordinates_and_counts_them(fake_mysql):
    _, cursor = fake_mysql
    cursor.fetchall.return_value = [
        {"id": 9, "tipo": "segnalazione", "titolo": "Buca", "stato": "inviata",
         "lat": Decimal("45.464200"), "lng": Decimal("9.190000")}]
    cursor.fetchone.return_value = {"totale": 4}
    result = list_map_items()
    assert result == {"items": [{"id": 9, "tipo": "segnalazione", "titolo": "Buca", "stato": "inviata",
                                 "lat": 45.4642, "lng": 9.19}], "senza_coordinate": 4, "troncato": False}
    points_sql, count_sql = (call.args[0] for call in cursor.execute.call_args_list)
    assert "Latitudine IS NOT NULL AND s.Longitudine IS NOT NULL" in points_sql
    assert "Visibilita = 'pubblica'" in points_sql and "duplicate_of_id IS NULL" in points_sql
    assert "Descrizione" not in points_sql and "IdAutore" not in points_sql
    assert "Latitudine IS NULL OR s.Longitudine IS NULL" in count_sql


def test_map_query_reports_truncation(fake_mysql):
    _, cursor = fake_mysql
    row = {"id": 1, "tipo": "proposta", "titolo": "T", "stato": "approvata", "lat": Decimal("45.4"), "lng": Decimal("9.2")}
    cursor.fetchall.return_value = [row, {**row, "id": 2}, {**row, "id": 3}]
    cursor.fetchone.return_value = {"totale": 0}
    result = list_map_items(limit=2)
    assert len(result["items"]) == 2 and result["troncato"] is True
    assert cursor.execute.call_args_list[0].args[1] == (3,)


def test_homepage_has_map_legend_and_loading_state(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="home-map"' in html and 'id="map-status"' in html and "Caricamento della mappa" in html
    assert 'data-map-count="segnalazione"' in html and 'data-map-count="proposta"' in html
    assert "js/home-map.js" in html and "maplibre-gl.js" in html
