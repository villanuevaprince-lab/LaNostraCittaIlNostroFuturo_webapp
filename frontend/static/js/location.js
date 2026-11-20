// Le tessere OSM standard possono restituire 403. OpenFreeMap offre uno stile
// vettoriale integrabile; il geocoder resta nel backend e viene chiamato su richiesta.
const DEFAULT_CENTER = { lat: 45.4642, lng: 9.19 };

// Un numero valido per MapLibre: niente null, stringhe o NaN dentro coordinate e sorgenti.
function isValidNumber(value) {
  return typeof value === "number" && !Number.isNaN(value) && Number.isFinite(value);
}

function isValidLatLng(lat, lng) {
  return isValidNumber(lat) && isValidNumber(lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180;
}

// Lo stile Liberty di OpenFreeMap calcola l'altezza degli edifici 3D con ["get", "render_height"]
// senza un valore di riserva: sugli edifici senza quel dato MapLibre avvisa
// "Expected value to be of type number, but found null instead". Qui, appena lo stile è caricato,
// le proprietà numeriche fatte solo di un ["get", ...] ricevono un ripiego a 0.
const NUMERIC_STYLE_PROPERTIES = ["fill-extrusion-height", "fill-extrusion-base"];

function protectNumericStyle(map) {
  map.on("style.load", () => {
    (map.getStyle()?.layers || []).forEach((layer) => {
      if (layer.type !== "fill-extrusion") return;
      NUMERIC_STYLE_PROPERTIES.forEach((property) => {
        const value = map.getPaintProperty(layer.id, property);
        if (Array.isArray(value) && value.length === 2 && value[0] === "get" && typeof value[1] === "string") {
          map.setPaintProperty(layer.id, property, ["coalesce", ["get", value[1]], 0]);
        }
      });
    });
  });
}

function setupMap(element, { interactive = true, lat = DEFAULT_CENTER.lat, lng = DEFAULT_CENTER.lng, onMove } = {}) {
  if (!window.maplibregl) throw new Error("La libreria della mappa non è disponibile. Usa la ricerca dell'indirizzo.");
  if (!isValidLatLng(lat, lng)) ({ lat, lng } = DEFAULT_CENTER);
  const map = new maplibregl.Map({
    container: element,
    style: "https://tiles.openfreemap.org/styles/liberty",
    center: [lng, lat], zoom: interactive ? 12 : 15,
    interactive, attributionControl: true,
  });
  protectNumericStyle(map);
  if (interactive) map.addControl(new maplibregl.NavigationControl(), "top-left");
  let marker;
  const setPoint = (latitude, longitude, notify = false) => {
    if (!isValidLatLng(latitude, longitude)) return;
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
