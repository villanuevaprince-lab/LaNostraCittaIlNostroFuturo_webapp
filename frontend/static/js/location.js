// Le tessere OSM standard possono restituire 403. OpenFreeMap offre uno stile
// vettoriale integrabile; il geocoder resta nel backend e viene chiamato su richiesta.
function setupMap(element, { interactive = true, lat = 45.4642, lng = 9.19, onMove } = {}) {
  if (!window.maplibregl) throw new Error("La libreria della mappa non è disponibile. Usa la ricerca dell'indirizzo.");
  const map = new maplibregl.Map({
    container: element,
    style: "https://tiles.openfreemap.org/styles/liberty",
    center: [lng, lat], zoom: interactive ? 12 : 15,
    interactive, attributionControl: true,
  });
  if (interactive) map.addControl(new maplibregl.NavigationControl(), "top-left");
  let marker;
  const setPoint = (latitude, longitude, notify = false) => {
    if (!marker) {
      marker = new maplibregl.Marker({ draggable: interactive })
        .setLngLat([longitude, latitude]).addTo(map);
      if (interactive) marker.on("dragend", () => {
        const point = marker.getLngLat();
        onMove?.(point.lat, point.lng);
      });
    } else marker.setLngLat([longitude, latitude]);
    map.jumpTo({ center: [longitude, latitude], zoom: 16 });
    if (notify) onMove?.(latitude, longitude);
  };
  if (interactive) map.on("click", (event) => setPoint(event.lngLat.lat, event.lngLat.lng, true));
  else setPoint(lat, lng);
  return { map, setPoint };
}
