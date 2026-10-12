// Векторный атлас России: каталог, просмотр на глобусе и в режиме «лист».
import { invProj, sheetProj } from './proj.js';

const $ = (id) => document.getElementById(id);
const BASEMAP = {
  light: 'https://tiles.openfreemap.org/styles/positron',
  dark: 'https://tiles.openfreemap.org/styles/dark',
};
const ORIGINALS = 'o/';           // оригиналы отдаёт воркер из R2
const WIDE = 860;                 // ширина окна, с которой панели стоят по бокам
const SEARCH_LIMIT = 300;
const START_MAP = '2-383-1';
const NO_VECTOR = {
  empty: 'На этом листе нет цветных областей: это таблица, график или карта из одних линий. Показан оригинал.',
  noise: 'Это снимок, рельефная или старинная карта. Цвет здесь меняется плавно, '
    + 'поэтому векторного слоя нет. Показан оригинал.',
};
const NOTE = {
  geo: 'Полигоны привязаны к местности по контуру России. Показана только территория внутри контура.',
  sheet: 'Лист целиком: оригинал и векторный слой поверх него, вместе с легендой.',
  unref: 'Для этого листа автоматическая привязка не подтвердилась, поэтому он показан в координатах листа.',
};

const state = {
  maps: [], byId: new Map(), order: [],
  cur: null, doc: null, lg: null,
  mode: 'geo', userMode: null,      // userMode: режим, который пользователь выбрал сам
  hidden: new Set(),
  tom: 0, q: '', onlyGeo: false,
  sections: new Map(),
};

const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const percent = (share) => (share * 100).toFixed(1).replace('.', ',');

// ---------- данные карты

// подпись класса из расшифрованной легенды: «заголовок · подпись»
function labelOf(ci) {
  const text = state.lg?.labels?.[ci];
  if (!text) return '';
  const group = state.lg.groups?.[ci];
  return group && group !== text ? `${group} · ${text}` : text;
}

function ringOf(flat, project, round) {
  const ring = [];
  for (let i = 0; i < flat.length; i += 2) {
    const p = project(flat[i], flat[i + 1]);
    ring.push([round(p[0]), round(p[1])]);
  }
  ring.push(ring[0]);
  return ring;
}

function toGeoJSON(doc, m, mode, precision = 4) {
  const geo = mode === 'geo';
  const project = geo ? (x, y) => invProj(m.geo, x, y) : sheetProj(doc.w, doc.h);
  const r = 10 ** precision;
  const round = (v) => Math.round(v * r) / r;
  const features = [];
  for (const [ci, inside, rings] of doc.f) {
    if (geo && !inside) continue;
    const properties = { ci, c: doc.colors[ci] };
    const label = labelOf(ci);
    if (label) properties.label = label;
    const coordinates = rings.map((flat) => ringOf(flat, project, round));
    features.push({ type: 'Feature', properties, geometry: { type: 'Polygon', coordinates } });
  }
  return { type: 'FeatureCollection', features };
}

// лист без привязки: координаты в пикселях оригинала, ось Y направлена вверх
function pixelGeoJSON(doc) {
  const project = (x, y) => [x, doc.h - y];
  const features = doc.f.map(([ci, , rings]) => ({
    type: 'Feature',
    properties: { ci, c: doc.colors[ci] },
    geometry: { type: 'Polygon', coordinates: rings.map((flat) => ringOf(flat, project, (v) => v)) },
  }));
  return { type: 'FeatureCollection', features };
}

// ---------- тема
function themeOf() {
  const t = document.documentElement.dataset.theme;
  if (t !== 'auto') return t;
  return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
const isDark = () => themeOf() === 'dark';
try {
  const saved = localStorage.getItem('theme');
  if (saved) document.documentElement.dataset.theme = saved;
} catch {}

// ---------- карта
const emptyStyle = () => ({
  version: 8,
  sources: {},
  layers: [{ id: 'bg', type: 'background', paint: { 'background-color': isDark() ? '#0b1016' : '#e9e6dd' } }],
});
const map = new maplibregl.Map({
  container: 'map',
  style: BASEMAP[themeOf()],
  center: [98, 64],
  zoom: 2.2,
  attributionControl: { compact: true },
  maxPitch: 60,
});
map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');
let styleKey = 'geo:' + themeOf();

function setStyle(key, style) {
  return new Promise((resolve) => {
    if (styleKey === key && map.isStyleLoaded()) return resolve();
    styleKey = key;
    map.once('style.load', () => resolve());
    map.setStyle(style, { diff: false });
  });
}
const firstSymbol = () => map.getStyle().layers.find((l) => l.type === 'symbol')?.id;
const highlight = (ci) => map.getLayer('v-hl') && map.setFilter('v-hl', ['==', ['get', 'ci'], ci]);

function clearLayers() {
  for (const id of ['v-line', 'v-hl', 'v-fill', 'raster']) if (map.getLayer(id)) map.removeLayer(id);
  for (const id of ['v', 'raster']) if (map.getSource(id)) map.removeSource(id);
}

function addRaster(m, doc) {
  const f = sheetProj(doc.w, doc.h);
  const coordinates = [f(0, 0), f(doc.w, 0), f(doc.w, doc.h), f(0, doc.h)];
  map.addSource('raster', { type: 'image', url: `data/d/${m.id}.webp`, coordinates });
  map.addLayer({
    id: 'raster', type: 'raster', source: 'raster',
    paint: { 'raster-opacity': $('raster').value / 100, 'raster-fade-duration': 0 },
  });
}

function addVector(gj, before) {
  map.addSource('v', { type: 'geojson', data: gj, tolerance: 0.2 });
  map.addLayer({
    id: 'v-fill', type: 'fill', source: 'v',
    paint: { 'fill-color': ['get', 'c'], 'fill-opacity': $('opacity').value / 100, 'fill-antialias': false },
  }, before);
  map.addLayer({
    id: 'v-line', type: 'line', source: 'v',
    layout: { visibility: $('outline').checked ? 'visible' : 'none' },
    paint: { 'line-color': isDark() ? '#000' : '#333', 'line-opacity': 0.45, 'line-width': 0.6 },
  }, before);
  map.addLayer({
    id: 'v-hl', type: 'line', source: 'v', filter: ['==', ['get', 'ci'], -1],
    paint: { 'line-color': isDark() ? '#fff' : '#111', 'line-width': 1.6 },
  }, before);
}

// охват слоя: [[запад, юг], [восток, север]] или null, если показывать нечего
function boundsOf(gj, doc, geo) {
  if (!geo) {
    const f = sheetProj(doc.w, doc.h);
    const [x0, y1] = f(0, 0);
    const [x1, y0] = f(doc.w, doc.h);
    return [[x0, y0], [x1, y1]];
  }
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const ft of gj.features) {
    for (const [x, y] of ft.geometry.coordinates[0]) {
      if (x < x0) x0 = x;
      if (x > x1) x1 = x;
      if (y < y0) y0 = y;
      if (y > y1) y1 = y;
    }
  }
  return x0 < x1 ? [[x0, y0], [x1, y1]] : null;
}

function fitTo(bounds, globe) {
  if (!bounds) return;
  const padding = innerWidth > WIDE
    ? { left: 400, right: 370, top: 40, bottom: 40 }
    : { left: 20, right: 20, top: 60, bottom: innerHeight * 0.48 };
  const cam = map.cameraForBounds(bounds, { padding });
  if (!cam) return;
  // на глобусе высокие широты выглядят мельче, чем в Меркаторе: приближаем сильнее
  map.easeTo({ center: cam.center, zoom: cam.zoom + (globe ? 0.45 : 0), pitch: 0, bearing: 0, duration: 900 });
}

async function render() {
  const m = state.cur, doc = state.doc;
  if (!m || !doc) return;
  const geo = state.mode === 'geo';
  const globe = geo && $('globe').checked;
  await setStyle((geo ? 'geo:' : 'sheet:') + themeOf(), geo ? BASEMAP[themeOf()] : emptyStyle());
  if (state.cur !== m) return;                       // пока грузился стиль, выбрали другую карту
  clearLayers();
  map.setProjection({ type: globe ? 'globe' : 'mercator' });
  if (!geo) addRaster(m, doc);
  const gj = toGeoJSON(doc, m, state.mode);
  addVector(gj, geo ? firstSymbol() : undefined);     // на подложке полигоны лежат под подписями
  applyHidden();
  fitTo(boundsOf(gj, doc, geo), globe);
}

function applyHidden() {
  const filter = state.hidden.size ? ['!', ['in', ['get', 'ci'], ['literal', [...state.hidden]]]] : null;
  for (const id of ['v-fill', 'v-line']) if (map.getLayer(id)) map.setFilter(id, filter);
}

// ---------- подсказка
function tipHTML(ci, color) {
  const share = `${percent(state.doc.share[ci])} % листа`;
  const name = state.lg?.labels?.[ci];
  const swatch = `<i style="background:${color}"></i>`;
  if (!name) {
    const why = state.lg ? 'нет подписи в легенде' : 'легенда не расшифрована';
    return `${swatch}<span><b>${share}</b><small>${why}</small></span>`;
  }
  const group = state.lg.groups?.[ci];
  const head = group ? `<small>${esc(group)}</small>` : '';
  return `${swatch}<span>${head}<b>${esc(name)}</b><small>${share}</small></span>`;
}

map.on('mousemove', 'v-fill', (e) => {
  const ft = e.features?.[0];
  if (!ft || !state.doc) return;
  const { ci, c } = ft.properties;
  map.getCanvas().style.cursor = 'pointer';
  highlight(ci);
  const tip = $('tip');
  tip.hidden = false;
  tip.innerHTML = tipHTML(ci, c);
  tip.style.left = Math.min(e.originalEvent.clientX + 14, innerWidth - 340) + 'px';
  tip.style.top = e.originalEvent.clientY + 14 + 'px';
});
map.on('mouseleave', 'v-fill', () => {
  map.getCanvas().style.cursor = '';
  $('tip').hidden = true;
  highlight(-1);
});

// ---------- выбор карты
function pickMode(m) {
  if (!m.geo || m.nv) return 'sheet';
  return state.userMode || 'geo';
}

function showInfo(m) {
  document.title = `${m.title} — векторный атлас России`;
  $('info').hidden = false;
  $('info').classList.toggle('plain', !!m.nv);
  $('crumbs').textContent = `Том ${m.tom} · ${m.section}`;
  $('title').textContent = m.title + (m.of > 1 ? ` (${m.n} из ${m.of})` : '');
  $('mode-geo').disabled = !m.geo || !!m.nv;
  const ext = (m.src.match(/\.[a-z0-9]+$/i) || ['.jpg'])[0];
  $('dl-orig').href = `${ORIGINALS}${m.id}${ext}`;
  $('dl-orig').download = `atlas-${m.id}${ext}`;
  $('dl-orig').textContent = `Оригинал · ${(m.osize / 1048576).toFixed(1)} МБ`;
  $('src').href = m.page;
}

function markCurrent(id) {
  document.querySelectorAll('.item.cur').forEach((e) => e.classList.remove('cur'));
  document.querySelector(`.item[data-id="${CSS.escape(id)}"]`)?.classList.add('cur');
}

async function loadLayer(m) {
  // лист без векторного слоя: только оригинал, размер листа берём из каталога
  if (m.nv) return [{ w: m.w, h: m.h, colors: [], share: [], f: [] }, null];
  const json = (url) => fetch(url).then((r) => r.json());
  const labels = m.lg ? json(`data/l/${m.id}.json`).catch(() => null) : null;
  return Promise.all([json(`data/v/${m.id}.json`), labels]);
}

async function open(id, push = true) {
  const m = state.byId.get(id);
  if (!m) return;
  state.cur = m;
  state.doc = null;
  state.lg = null;
  state.hidden.clear();
  state.mode = pickMode(m);
  if (push) history.pushState(null, '', '#/' + id);
  showInfo(m);
  syncMode();
  markCurrent(id);
  if (innerWidth <= WIDE) setSide(false);
  $('legend').innerHTML = m.nv ? '' : '<div class="empty">Загрузка слоя…</div>';
  let doc, lg;
  try {
    [doc, lg] = await loadLayer(m);
  } catch {
    toast('Не удалось загрузить векторный слой');
    return;
  }
  if (state.cur !== m) return;
  state.doc = doc;
  state.lg = lg;
  if (!m.nv) legend();
  render();
}

function noteFor(m, geo) {
  if (m?.nv) return NO_VECTOR[m.nv];
  if (geo) return NOTE.geo;
  return m?.geo ? NOTE.sheet : NOTE.unref;
}

function syncMode() {
  const geo = state.mode === 'geo';
  $('mode-geo').classList.toggle('on', geo);
  $('mode-sheet').classList.toggle('on', !geo);
  $('row-raster').hidden = geo;
  $('globe-wrap').hidden = !geo;
  $('note').textContent = noteFor(state.cur, geo);
}

function setMode(mode) {
  state.mode = state.userMode = mode;
  syncMode();
  render();
}

// ---------- список классов
function swatchButton(ci) {
  const doc = state.doc;
  const name = labelOf(ci);
  const share = percent(doc.share[ci]) + ' %';
  const b = document.createElement('button');
  b.className = 'sw' + (name ? ' named' : '') + (state.hidden.has(ci) ? ' off' : '');
  b.title = name || doc.colors[ci];
  const swatch = `<i style="background:${doc.colors[ci]}"></i>`;
  if (name) {
    const group = state.lg.groups?.[ci];
    const sub = group ? `<small>${esc(group)}</small>` : '';
    b.innerHTML = `${swatch}<span>${esc(state.lg.labels[ci])}${sub}</span><em>${share}</em>`;
  } else {
    b.innerHTML = swatch + share;
  }
  b.onclick = () => {
    if (!state.hidden.delete(ci)) state.hidden.add(ci);
    b.classList.toggle('off');
    applyHidden();
  };
  b.onmouseenter = () => highlight(ci);
  b.onmouseleave = () => highlight(-1);
  return b;
}

function legend() {
  const doc = state.doc, el = $('legend');
  el.innerHTML = '';
  el.classList.toggle('named', !!state.lg);
  const named = (ci) => (labelOf(ci) ? 1 : 0);
  const used = [...new Set(doc.f.map((f) => f[0]))];
  used.sort((a, b) => named(b) - named(a) || doc.share[b] - doc.share[a]);   // сначала классы с подписью
  el.append(...used.map(swatchButton));
}

// ---------- каталог
function filtered() {
  const words = state.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return state.maps.filter((m) => (!state.tom || m.tom === state.tom)
    && (!state.onlyGeo || m.geo)
    && words.every((w) => m.search.includes(w)));
}

function itemHTML(m) {
  const part = m.of > 1 ? ` · ${m.n} из ${m.of}` : '';
  const badges = (m.geo ? '<span class="badge">глобус</span>' : '')
    + (m.lg ? '<span class="badge alt">легенда</span>' : '')
    + (m.nv ? '<span class="badge alt">картинка</span>' : '');
  return `<div class="item${state.cur === m ? ' cur' : ''}" data-id="${m.id}">`
    + `<img loading="lazy" alt="" src="data/t/${m.id}.webp">`
    + `<div><b>${esc(m.title)}</b><small>том ${m.tom}${part}${badges}</small></div></div>`;
}

const sectionKey = (m) => m.tom + '|' + m.section;

function sectionHTML(key, items, isOpen) {
  const count = `том ${items[0].tom} · ${items.length}`;
  const head = `<button><span>${esc(items[0].section)}</span><small>${count}</small></button>`;
  const body = isOpen ? items.map(itemHTML).join('') : '';     // закрытый раздел заполняется при открытии
  return `<div class="sec${isOpen ? ' open' : ''}" data-k="${esc(key)}">${head}<div class="items">${body}</div></div>`;
}

function list() {
  const found = filtered(), el = $('list');
  state.order = found.map((m) => m.id);
  if (!found.length) {
    el.innerHTML = '<div class="empty">Ничего не найдено</div>';
    return;
  }
  if (state.q.trim()) {
    const more = found.length > SEARCH_LIMIT
      ? `<div class="empty">Показаны первые ${SEARCH_LIMIT} из ${found.length}</div>` : '';
    el.innerHTML = found.slice(0, SEARCH_LIMIT).map(itemHTML).join('') + more;
    return;
  }
  state.sections = Map.groupBy(found, sectionKey);
  const curKey = state.cur ? sectionKey(state.cur) : null;
  el.innerHTML = [...state.sections].map(([key, items]) => sectionHTML(key, items, key === curKey)).join('');
}

$('list').addEventListener('click', (e) => {
  const item = e.target.closest('.item');
  if (item) return open(item.dataset.id);
  const sec = e.target.closest('.sec');
  if (!sec) return;
  const items = sec.querySelector('.items');
  if (!items.childElementCount) items.innerHTML = state.sections.get(sec.dataset.k).map(itemHTML).join('');
  sec.classList.toggle('open');
});

function chips() {
  const el = $('toms');
  el.innerHTML = '';
  const chip = (tom, label) => {
    const count = state.maps.filter((m) => !tom || m.tom === tom).length;
    const b = document.createElement('button');
    b.className = 'chip' + (state.tom === tom ? ' on' : '');
    b.innerHTML = `<b>${label}</b><span>${count}</span>`;
    b.onclick = () => { state.tom = tom; chips(); list(); };
    el.append(b);
  };
  chip(0, 'Все');
  for (const tom of [1, 2, 3, 4]) chip(tom, 'Том ' + tom);
}

// ---------- управление
function setSide(shown) {
  $('side').classList.toggle('hidden', !shown);
  $('expand').hidden = shown;
}

let toastTimer;
function toast(text) {
  const t = $('toast');
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 2600);
}

function step(d) {
  const n = state.order.length;
  const id = state.order[(state.order.indexOf(state.cur?.id) + d + n) % n];
  if (id) open(id);
}

function downloadGeoJSON() {
  const m = state.cur, doc = state.doc;
  if (!m || !doc || m.nv) return;
  const gj = m.geo ? toGeoJSON(doc, m, 'geo', 4) : pixelGeoJSON(doc);
  gj.name = m.title;
  gj.source = m.page;
  gj.note = m.geo
    ? 'Координаты WGS 84 (долгота, широта). Свойство c — цвет класса на исходной карте.'
    : 'Лист без географической привязки: координаты в пикселях оригинала, ось Y направлена вверх.';
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(gj)], { type: 'application/geo+json' }));
  a.download = `atlas-${m.id}.geojson`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

function toggleTheme() {
  const t = isDark() ? 'light' : 'dark';
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem('theme', t); } catch {}
  if (state.cur) render(); else map.setStyle(BASEMAP[t]);
}

async function share() {
  try {
    await navigator.clipboard.writeText(location.href);
    toast('Ссылка скопирована');
  } catch {
    toast(location.href);
  }
}

// ползунок прозрачности: подпись рядом и свойство слоя
function bindOpacity(id, layer, property) {
  $(id).oninput = (e) => {
    $(id + '-v').textContent = e.target.value + '%';
    if (map.getLayer(layer)) map.setPaintProperty(layer, property, e.target.value / 100);
  };
}

let searchTimer;
$('q').addEventListener('input', (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { state.q = e.target.value; list(); }, 120);
});
$('onlygeo').onchange = (e) => { state.onlyGeo = e.target.checked; list(); };
$('mode-geo').onclick = () => { if (state.cur?.geo) setMode('geo'); };
$('mode-sheet').onclick = () => setMode('sheet');
bindOpacity('opacity', 'v-fill', 'fill-opacity');
bindOpacity('raster', 'raster', 'raster-opacity');
$('outline').onchange = (e) => {
  if (map.getLayer('v-line')) map.setLayoutProperty('v-line', 'visibility', e.target.checked ? 'visible' : 'none');
};
$('globe').onchange = (e) => {
  map.setProjection({ type: e.target.checked && state.mode === 'geo' ? 'globe' : 'mercator' });
};
$('legend-reset').onclick = () => { state.hidden.clear(); legend(); applyHidden(); };
$('collapse').onclick = () => setSide(false);
$('expand').onclick = () => setSide(true);
$('theme').onclick = toggleTheme;
$('share').onclick = share;
$('dl-geojson').onclick = downloadGeoJSON;
$('prev').onclick = () => step(-1);
$('next').onclick = () => step(1);

addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT') return;
  if (e.key === 'ArrowRight') step(1);
  if (e.key === 'ArrowLeft') step(-1);
  if (e.key === '/') { e.preventDefault(); $('q').focus(); }
});

// адрес вида #/2-383-1 открывает карту; возвращает false, если такой карты нет
function route() {
  const id = decodeURIComponent(location.hash.replace(/^#\/?/, ''));
  if (!state.byId.has(id)) return false;
  if (state.cur?.id !== id) open(id, false);
  return true;
}
addEventListener('popstate', route);

// ---------- запуск
function start() {
  if (!route()) {
    const first = state.byId.get(START_MAP) || state.maps.find((m) => m.geo) || state.maps[0];
    open(first.id, false);
  }
  list();
  document.querySelector('.item.cur')?.scrollIntoView({ block: 'center' });
}

(async () => {
  const catalog = await (await fetch('data/catalog.json')).json();
  state.maps = catalog.maps;
  for (const m of state.maps) {
    m.search = `${m.title} ${m.section} том ${m.tom}`.toLowerCase();
    state.byId.set(m.id, m);
  }
  const onGlobe = state.maps.filter((m) => m.geo).length;
  $('stats').textContent = `${state.maps.length} карт · ${onGlobe} на глобусе · 4 тома`;
  chips();
  list();
  if (map.isStyleLoaded()) start(); else map.once('load', start);
})();
