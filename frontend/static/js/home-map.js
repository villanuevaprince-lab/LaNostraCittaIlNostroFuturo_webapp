// Mappa della homepage: un solo endpoint leggero e un layer GeoJSON (regge migliaia di punti).
const MAP_COLORS = { segnalazione: "#c2410c", proposta: "#1d4ed8" };
const TYPE_LABELS = { segnalazione: "Segnalazione", proposta: "Proposta" };

function mapPopup(item) {
  const box = document.createElement("div"); box.className = "map-popup";
  const title = document.createElement("h3"); title.textContent = item.titolo;
  const badge = document.createElement("span"); setStateBadge(badge, item);
  const kind = document.createElement("p"); kind.textContent = TYPE_LABELS[item.tipo] || item.tipo;
  const link = document.createElement("a"); link.href = `/reports/${item.id}`; link.textContent = "Apri il dettaglio";
  box.append(title, kind, badge, document.createElement("br"), link);
  return box;
}

function updateLegend(data) {
  ["segnalazione", "proposta"].forEach((type) => {
    const total = data.items.filter((item) => item.tipo === type).length;
    document.querySelector(`[data-map-count="${type}"]`).textContent = `(${total})`;
  });
  const missing = document.querySelector("#map-missing");
  missing.hidden = !data.senza_coordinate;
  missing.textContent = data.senza_coordinate === 1
    ? "1 contenuto senza posizione non è sulla mappa"
    : `${data.senza_coordinate} contenuti senza posizione non sono sulla mappa`;
}

async function loadHomeMap() {
  const container = document.querySelector("#home-map");
  const status = document.querySelector("#map-status");
  let data;
  try {
    const response = await fetch("/api/map-items", { credentials: "same-origin" });
    data = await response.json();
    if (!response.ok) throw new Error(data.error);
  } catch (error) {
    status.textContent = "Non è stato possibile caricare i punti della mappa. L'elenco qui sotto resta disponibile.";
    container.hidden = true;
    return;
  }
  updateLegend(data);
  if (!window.maplibregl) {
    status.textContent = "La mappa non è disponibile in questo momento: trovi tutti i contenuti nell'elenco qui sotto.";
    container.hidden = true;
    return;
  }
  const map = new maplibregl.Map({
    container, style: "https://tiles.openfreemap.org/styles/liberty",
    center: [9.19, 45.4642], zoom: 11.3, attributionControl: true, cooperativeGestures: true,
  });
  map.addControl(new maplibregl.NavigationControl(), "top-left");
  map.on("load", () => {
    map.addSource("map-items", { type: "geojson", data: {
      type: "FeatureCollection",
      features: data.items.map((item) => ({
        type: "Feature", properties: { id: item.id, tipo: item.tipo },
        geometry: { type: "Point", coordinates: [item.lng, item.lat] },
      })),
    } });
    map.addLayer({ id: "map-items", type: "circle", source: "map-items", paint: {
      "circle-radius": 7,
      "circle-color": ["match", ["get", "tipo"], "proposta", MAP_COLORS.proposta, MAP_COLORS.segnalazione],
      "circle-stroke-width": 2,
      "circle-stroke-color": ["match", ["get", "tipo"], "proposta", "#1e293b", "#ffffff"],
    } });
    const byId = new Map(data.items.map((item) => [item.id, item]));
    map.on("click", "map-items", (event) => {
      const item = byId.get(event.features[0].properties.id);
      if (!item) return;
      new maplibregl.Popup({ maxWidth: "280px" }).setLngLat([item.lng, item.lat]).setDOMContent(mapPopup(item)).addTo(map);
    });
    map.on("mouseenter", "map-items", () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", "map-items", () => { map.getCanvas().style.cursor = ""; });
    if (data.items.length) {
      const bounds = new maplibregl.LngLatBounds();
      data.items.forEach((item) => bounds.extend([item.lng, item.lat]));
      map.fitBounds(bounds, { padding: 48, maxZoom: 15, duration: 0 });
      status.textContent = `${data.items.length} contenuti sulla mappa. Seleziona un punto per i dettagli.`
        + (data.troncato ? " Sono mostrati i più recenti." : "");
    } else {
      status.textContent = "Ancora nessuna segnalazione o proposta con una posizione sulla mappa.";
    }
  });
}

loadHomeMap();
