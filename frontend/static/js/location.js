// Geocoding solo dopo un'azione esplicita: niente autocomplete sul servizio pubblico.
function setupMap(element, { interactive = true, lat = 45.4642, lng = 9.19, onMove } = {}) {
  if (!window.L) throw new Error("La mappa non è disponibile. Ricarica la pagina.");
  const map = L.map(element, { scrollWheelZoom: false }).setView([lat, lng], interactive ? 12 : 15);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  let marker = null;
  const setPoint = (latitude, longitude, notify = false) => {
    if (!marker) {
      marker = L.marker([latitude, longitude], { draggable: interactive }).addTo(map);
      if (interactive) marker.on("dragend", () => {
        const position = marker.getLatLng();
        onMove(position.lat, position.lng);
      });
    } else marker.setLatLng([latitude, longitude]);
    map.setView([latitude, longitude], 16);
    if (notify && onMove) onMove(latitude, longitude);
  };
  if (interactive) map.on("click", (event) => setPoint(event.latlng.lat, event.latlng.lng, true));
  else setPoint(lat, lng);
  return { map, setPoint };
}
