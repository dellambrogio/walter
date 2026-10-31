"""Build a standalone local map of detected hikes (data/processed/hikes_map.html).

Usage: python3 app/prototype/build_hikes_map.py
Contains personal location data: open locally, don't publish.
"""
import json
from pathlib import Path

SRC = Path("data/processed/walks.geojson")
TOURS = Path("data/processed/swisstopo_tours.geojson")
ROUTES = Path("data/processed/schweizmobil_routes.geojson")
OUT = Path("data/processed/hikes_map.html")
KINDS = ["hike", "hike?", "long_walk", "hike_abroad?"]

walks = json.loads(SRC.read_text())
walks["features"] = [f for f in walks["features"] if f["properties"]["kind"] in KINDS]
empty = {"type": "FeatureCollection", "features": []}
tours = json.loads(TOURS.read_text()) if TOURS.exists() else empty
routes = json.loads(ROUTES.read_text()) if ROUTES.exists() else empty

html = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Walter hikes</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<style>
  :root { --bg:#fff; --fg:#1d1d1f; --muted:#6b6b70; --line:#e3e3e6; --sel:#f1f4f8; }
  @media (prefers-color-scheme: dark) { :root { --bg:#17181a; --fg:#ececee; --muted:#9a9aa0; --line:#2c2d30; --sel:#23262b; } }
  * { box-sizing:border-box; }
  body { margin:0; font:14px/1.4 system-ui, sans-serif; background:var(--bg); color:var(--fg); display:flex; height:100vh; }
  #side { width:360px; max-width:45vw; display:flex; flex-direction:column; border-right:1px solid var(--line); }
  #side header { padding:12px 16px; border-bottom:1px solid var(--line); }
  #side h1 { font-size:16px; margin:0 0 8px; }
  .filters label { display:inline-flex; align-items:center; gap:4px; margin:0 10px 4px 0; cursor:pointer; }
  .sw { width:12px; height:4px; border-radius:2px; display:inline-block; }
  #list { overflow:auto; flex:1; }
  .row { padding:8px 16px; border-bottom:1px solid var(--line); cursor:pointer; }
  .row:hover, .row.sel { background:var(--sel); }
  .row b { font-weight:600; } .row small { color:var(--muted); }
  #map { flex:1; }
  @media (max-width:700px) { body { flex-direction:column; } #side { width:100%; max-width:none; height:40vh; border-right:0; border-bottom:1px solid var(--line); } }
</style></head><body>
<div id="side"><header><h1>Detected hikes</h1><div class="filters" id="filters"></div>
<small id="count"></small></header><div id="list"></div></div>
<div id="map"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script>
const WALKS = __WALKS__;
const TOURS = __TOURS__;
const ROUTES = __ROUTES__;
const COLORS = {"hike":"#d7263d","hike?":"#f49d37","long_walk":"#3f88c5","hike_abroad?":"#8e44ad","tour":"#1b998b"};
const LABELS = {"hike":"Hike","hike?":"Hike? (too fast)","long_walk":"Long flat walk","hike_abroad?":"Abroad","tour":"swisstopo tour"};
const on = {"hike":true,"hike?":true,"long_walk":false,"hike_abroad?":false,"tour":true};

const map = L.map('map').setView([46.8, 8.2], 8);
const base = {
  "Swiss map": L.tileLayer('https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-farbe/default/current/3857/{z}/{x}/{y}.jpeg', {maxZoom:19, attribution:'© swisstopo'}),
  "Swiss map grey": L.tileLayer('https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-grau/default/current/3857/{z}/{x}/{y}.jpeg', {maxZoom:19, attribution:'© swisstopo'}),
  "Aerial": L.tileLayer('https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.swissimage/default/current/3857/{z}/{x}/{y}.jpeg', {maxZoom:19, attribution:'© swisstopo'}),
};
base["Swiss map grey"].addTo(map);
const trails = L.tileLayer('https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.swisstlm3d-wanderwege/default/current/3857/{z}/{x}/{y}.png', {maxZoom:19, opacity:0.7});
const smOfficial = L.tileLayer('https://wmts.geo.admin.ch/1.0.0/ch.astra.wanderland/default/current/3857/{z}/{x}/{y}.png', {maxZoom:19, opacity:0.8, attribution:'© FEDRO / SchweizMobil'});
const canvas = L.canvas();
const RCOL = {national:'#0b6e4f', regional:'#2a9d8f', local:'#8ab17d'};
const RW = {national:4, regional:3, local:2};
const routeLayers = {};
['local','regional','national'].forEach(lvl => {
  routeLayers[lvl] = L.geoJSON({type:'FeatureCollection', features: ROUTES.features.filter(f => f.properties.level===lvl)}, {
    renderer: canvas,
    style: {color: RCOL[lvl], weight: RW[lvl], opacity: 0.75, dashArray: lvl==='local' ? '4 4' : null},
    onEachFeature: (f, l) => { const p = f.properties;
      l.bindPopup(`<b>${p.nr} ${p.name}</b><br><small>SchweizMobil ${p.level} route · ${p.km} km · +${p.ascent_m} / −${p.descent_m} m<br>${p.from} → ${p.to}<br>fitness: ${p.fitness} · technique: ${p.technique}</small>`);
      l.on('mouseover', () => l.setStyle({weight: RW[lvl]+3, opacity: 1}));
      l.on('mouseout', () => l.setStyle({weight: RW[lvl], opacity: 0.75}));
    }});
});
routeLayers.national.addTo(map); routeLayers.regional.addTo(map);
L.control.layers(base, {
  "SchweizMobil national routes": routeLayers.national,
  "SchweizMobil regional routes": routeLayers.regional,
  "SchweizMobil local routes": routeLayers.local,
  "SchweizMobil (official map layer)": smOfficial,
  "Hiking trails (swissTLM3D)": trails,
}, {collapsed: false}).addTo(map);

const items = [];
WALKS.features.forEach(f => items.push({f, kind:f.properties.kind}));
TOURS.features.forEach(f => items.push({f, kind:"tour"}));
items.forEach(it => {
  it.layer = L.geoJSON(it.f, {style:{color:COLORS[it.kind], weight:5, opacity:0.9}});
  const p = it.f.properties;
  it.text = it.kind === "tour"
    ? `<b>${p.name}</b><br><small>swisstopo tour · ${p.distance_km} km · +${p.ascent_m} m · created ${(p.created||'').slice(0,10)}</small>`
    : `<b>${p.date}</b> · ${LABELS[it.kind]}<br><small>${p.km} km · ${p.hours} h · ${p.gain_m ?? '–'} m up · top ${p.top_m ?? '–'} m · ${p.kmh} km/h</small>`;
  it.layer.bindPopup(it.text);
  it.layer.on('click', () => select(it));
});
items.sort((a,b) => ((b.f.properties.date||b.f.properties.created||'') > (a.f.properties.date||a.f.properties.created||'') ? 1 : -1));

const fdiv = document.getElementById('filters');
Object.keys(LABELS).forEach(k => {
  const n = items.filter(i => i.kind===k).length; if (!n) return;
  const l = document.createElement('label');
  l.innerHTML = `<input type="checkbox" ${on[k]?'checked':''}><span class="sw" style="background:${COLORS[k]}"></span>${LABELS[k]} (${n})`;
  l.querySelector('input').onchange = e => { on[k] = e.target.checked; render(); };
  fdiv.appendChild(l);
});

const list = document.getElementById('list');
function select(it) {
  document.querySelectorAll('.row.sel').forEach(r => r.classList.remove('sel'));
  if (it.row) { it.row.classList.add('sel'); it.row.scrollIntoView({block:'nearest'}); }
  map.fitBounds(it.layer.getBounds(), {maxZoom:14, padding:[30,30]});
  it.layer.openPopup();
}
function render() {
  list.innerHTML = ''; const vis = [];
  items.forEach(it => {
    if (on[it.kind]) { it.layer.addTo(map); vis.push(it);
      const r = document.createElement('div'); r.className='row'; r.innerHTML = it.text;
      r.onclick = () => select(it); it.row = r; list.appendChild(r);
    } else { map.removeLayer(it.layer); it.row = null; }
  });
  document.getElementById('count').textContent = `${vis.length} shown`;
}
render();
</script></body></html>
"""
OUT.write_text(html.replace("__WALKS__", json.dumps(walks)).replace("__TOURS__", json.dumps(tours)).replace("__ROUTES__", json.dumps(routes)))
print(f"{len(walks['features'])} walks + {len(tours['features'])} tours + {len(routes['features'])} SchweizMobil routes -> {OUT}")
