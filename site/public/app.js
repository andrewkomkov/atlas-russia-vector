// Векторный атлас России: каталог, просмотр на глобусе и в режиме «лист».
const $ = (id) => document.getElementById(id);
const BASEMAP = { light: 'https://tiles.openfreemap.org/styles/positron', dark: 'https://tiles.openfreemap.org/styles/dark' };
const ORIGINALS = 'o/';           // оригиналы отдаёт воркер из R2
const R = 6378137, SHEET_SPAN = 6.0e6;   // условный размер листа в метрах Меркатора

const state = { maps: [], byId: new Map(), cur: null, doc: null, lg: null, mode: 'geo', hidden: new Set(), tom: 0, q: '', onlyGeo: false, order: [] };

// ---------- проекция атласа (равнопромежуточная коническая), обратное преобразование
function invProj(P, X, Y) {
  const [n, G, lon0, k, tx, ty, rot] = P;
  const u = (X - tx) / k, v = -(Y - ty) / k, c = Math.cos(rot), s = Math.sin(rot);
  const x = c * u + s * v, y = -s * u + c * v;
  return [lon0 + (Math.atan2(x, -y) / n) * 180 / Math.PI, (G - Math.hypot(x, y)) * 180 / Math.PI];
}
// лист без привязки кладётся в условную область карты, чтобы MapLibre показал его без искажений
function sheetProj(w, h) {
  const S = SHEET_SPAN / Math.max(w, h);
  return (X, Y) => {
    const mx = (X - w / 2) * S, my = (h / 2 - Y) * S;
    return [mx / R * 180 / Math.PI, (2 * Math.atan(Math.exp(my / R)) - Math.PI / 2) * 180 / Math.PI];
  };
}
function toGeoJSON(doc, m, mode, precision = 4) {
  const geo = mode === 'geo';
  const f = geo ? (x, y) => invProj(m.geo, x, y) : sheetProj(doc.w, doc.h);
  const r = 10 ** precision, features = [];
  for (const [ci, inside, rings] of doc.f) {
    if (geo && !inside) continue;
    const coords = rings.map((flat) => {
      const ring = [];
      for (let i = 0; i < flat.length; i += 2) { const p = f(flat[i], flat[i + 1]); ring.push([Math.round(p[0] * r) / r, Math.round(p[1] * r) / r]); }
      ring.push(ring[0]);
      return ring;
    });
    features.push({ type: 'Feature', properties: { ci, c: doc.colors[ci], ...(labelOf(ci) ? { label: labelOf(ci) } : {}) }, geometry: { type: 'Polygon', coordinates: coords } });
  }
  return { type: 'FeatureCollection', features };
}

// подпись класса из расшифрованной легенды: «заголовок · подпись»
function labelOf(ci) {
  const t = state.lg?.labels?.[ci]; if (!t) return '';
  const g = state.lg.groups?.[ci];
  return g && g !== t ? `${g} · ${t}` : t;
}

// ---------- тема
const themeOf = () => { const t = document.documentElement.dataset.theme; return t === 'auto' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : t; };
try { const t = localStorage.getItem('theme'); if (t) document.documentElement.dataset.theme = t; } catch {}

// ---------- карта
const EMPTY = () => ({ version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': themeOf() === 'dark' ? '#0b1016' : '#e9e6dd' } }] });
const map = new maplibregl.Map({ container: 'map', style: BASEMAP[themeOf()], center: [98, 64], zoom: 2.2, attributionControl: { compact: true }, maxPitch: 60 });
map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');
let styleKey = 'geo:' + themeOf();

function setStyle(key, style) {
  return new Promise((res) => {
    if (styleKey === key && map.isStyleLoaded()) return res();
    styleKey = key;
    map.once('style.load', () => res());
    map.setStyle(style, { diff: false });
  });
}
function firstSymbol() { return map.getStyle().layers.find((l) => l.type === 'symbol')?.id; }

async function render() {
  const m = state.cur, doc = state.doc;
  if (!m || !doc) return;
  const geo = state.mode === 'geo';
  await setStyle((geo ? 'geo:' : 'sheet:') + themeOf(), geo ? BASEMAP[themeOf()] : EMPTY());
  if (state.cur !== m) return;                       // пока грузился стиль, выбрали другую карту
  for (const id of ['v-line', 'v-hl', 'v-fill', 'raster']) if (map.getLayer(id)) map.removeLayer(id);
  for (const id of ['v', 'raster']) if (map.getSource(id)) map.removeSource(id);
  map.setProjection({ type: geo && $('globe').checked ? 'globe' : 'mercator' });
  const before = geo ? firstSymbol() : undefined;
  if (!geo) {
    const f = sheetProj(doc.w, doc.h);
    map.addSource('raster', { type: 'image', url: `data/d/${m.id}.webp`, coordinates: [f(0, 0), f(doc.w, 0), f(doc.w, doc.h), f(0, doc.h)] });
    map.addLayer({ id: 'raster', type: 'raster', source: 'raster', paint: { 'raster-opacity': $('raster').value / 100, 'raster-fade-duration': 0 } });
  }
  const gj = toGeoJSON(doc, m, state.mode);
  map.addSource('v', { type: 'geojson', data: gj, tolerance: 0.2 });
  map.addLayer({ id: 'v-fill', type: 'fill', source: 'v', paint: { 'fill-color': ['get', 'c'], 'fill-opacity': $('opacity').value / 100, 'fill-antialias': false } }, before);
  map.addLayer({ id: 'v-line', type: 'line', source: 'v', layout: { visibility: $('outline').checked ? 'visible' : 'none' }, paint: { 'line-color': themeOf() === 'dark' ? '#000' : '#333', 'line-opacity': 0.45, 'line-width': 0.6 } }, before);
  map.addLayer({ id: 'v-hl', type: 'line', source: 'v', filter: ['==', ['get', 'ci'], -1], paint: { 'line-color': themeOf() === 'dark' ? '#fff' : '#111', 'line-width': 1.6 } }, before);
  applyHidden();
  // охват
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  for (const ft of gj.features) for (const p of ft.geometry.coordinates[0]) { if (p[0] < x0) x0 = p[0]; if (p[0] > x1) x1 = p[0]; if (p[1] < y0) y0 = p[1]; if (p[1] > y1) y1 = p[1]; }
  if (!geo) { const f = sheetProj(doc.w, doc.h); [x0, y1] = f(0, 0); [x1, y0] = f(doc.w, doc.h); }
  if (x0 < x1) {
    const wide = innerWidth > 860, globe = geo && $('globe').checked;
    const padding = wide ? { left: 400, right: 370, top: 40, bottom: 40 } : { left: 20, right: 20, top: 60, bottom: innerHeight * 0.48 };
    const cam = map.cameraForBounds([[x0, y0], [x1, y1]], { padding });
    // на глобусе высокие широты выглядят мельче, чем в Меркаторе: приближаем сильнее
    if (cam) map.easeTo({ center: cam.center, zoom: cam.zoom + (globe ? 0.45 : 0), pitch: 0, bearing: 0, duration: 900 });
  }
}
function applyHidden() {
  const f = state.hidden.size ? ['!', ['in', ['get', 'ci'], ['literal', [...state.hidden]]]] : null;
  for (const id of ['v-fill', 'v-line']) if (map.getLayer(id)) map.setFilter(id, f);
}

// наведение
map.on('mousemove', 'v-fill', (e) => {
  const ft = e.features?.[0]; if (!ft || !state.doc) return;
  const ci = ft.properties.ci;
  map.getCanvas().style.cursor = 'pointer';
  if (map.getLayer('v-hl')) map.setFilter('v-hl', ['==', ['get', 'ci'], ci]);
  const tip = $('tip'); tip.hidden = false;
  const name = state.lg?.labels?.[ci], group = state.lg?.groups?.[ci], pct = (state.doc.share[ci] * 100).toFixed(1).replace('.', ',');
  tip.innerHTML = `<i style="background:${ft.properties.c}"></i><span>${name ? `${group ? `<small>${esc(group)}</small>` : ''}<b>${esc(name)}</b><small>${pct} % листа</small>` : `${ft.properties.c} · ${pct} % листа`}</span>`;
  tip.style.left = Math.min(e.originalEvent.clientX + 14, innerWidth - 340) + 'px'; tip.style.top = e.originalEvent.clientY + 14 + 'px';
});
map.on('mouseleave', 'v-fill', () => { map.getCanvas().style.cursor = ''; $('tip').hidden = true; if (map.getLayer('v-hl')) map.setFilter('v-hl', ['==', ['get', 'ci'], -1]); });

// ---------- выбор карты
async function open(id, push = true) {
  const m = state.byId.get(id); if (!m) return;
  state.cur = m; state.doc = null; state.lg = null; state.hidden.clear();
  if (push) history.pushState(null, '', '#/' + id);
  document.title = `${m.title} — векторный атлас России`;
  $('info').hidden = false;
  $('crumbs').textContent = `Том ${m.tom} · ${m.section}`;
  $('title').textContent = m.title + (m.of > 1 ? ` (${m.n} из ${m.of})` : '');
  $('mode-geo').disabled = !m.geo;
  if (!m.geo) state.mode = 'sheet'; else if (!state.userMode) state.mode = 'geo'; else state.mode = state.userMode;
  const ext = (m.src.match(/\.[a-z0-9]+$/i) || ['.jpg'])[0];
  $('dl-orig').href = `${ORIGINALS}${m.id}${ext}`; $('dl-orig').download = `atlas-${m.id}${ext}`;
  $('dl-orig').textContent = `Оригинал · ${(m.osize / 1048576).toFixed(1)} МБ`;
  $('src').href = m.page;
  syncMode();
  document.querySelectorAll('.item.cur').forEach((e) => e.classList.remove('cur'));
  document.querySelector(`.item[data-id="${CSS.escape(id)}"]`)?.classList.add('cur');
  if (innerWidth <= 860) $('side').classList.add('hidden'), $('expand').hidden = false;
  $('legend').innerHTML = '<div class="empty">Загрузка слоя…</div>';
  let doc;
  let lg = null;
  try {
    [doc, lg] = await Promise.all([fetch(`data/v/${m.id}.json`).then((r) => r.json()), m.lg ? fetch(`data/l/${m.id}.json`).then((r) => r.json()).catch(() => null) : null]);
  } catch { toast('Не удалось загрузить векторный слой'); return; }
  if (state.cur !== m) return;
  state.doc = doc; state.lg = lg;
  legend();
  render();
}
function syncMode() {
  const m = state.cur, geo = state.mode === 'geo';
  $('mode-geo').classList.toggle('on', geo); $('mode-sheet').classList.toggle('on', !geo);
  $('row-raster').hidden = geo; $('globe-wrap').hidden = !geo;
  $('note').textContent = geo
    ? 'Полигоны привязаны к местности по контуру России. Показана только территория внутри контура.'
    : (m?.geo ? 'Лист целиком: оригинал и векторный слой поверх него, вместе с легендой.' : 'Для этого листа автоматическая привязка не подтвердилась, поэтому он показан в координатах листа.');
}
function legend() {
  const doc = state.doc, el = $('legend'); el.innerHTML = '';
  const used = new Set(doc.f.map((f) => f[0]));
  el.classList.toggle('named', !!state.lg);
  const named = (ci) => (labelOf(ci) ? 1 : 0);
  [...used].sort((a, b) => named(b) - named(a) || doc.share[b] - doc.share[a]).forEach((ci) => {
    const name = labelOf(ci), pct = (doc.share[ci] * 100).toFixed(1).replace('.', ',') + ' %';
    const b = document.createElement('button'); b.className = 'sw' + (name ? ' named' : '') + (state.hidden.has(ci) ? ' off' : ''); b.title = name || doc.colors[ci];
    const own = state.lg?.labels?.[ci], group = state.lg?.groups?.[ci];
    b.innerHTML = `<i style="background:${doc.colors[ci]}"></i>${name ? `<span>${esc(own)}${group ? `<small>${esc(group)}</small>` : ''}</span><em>${pct}</em>` : pct}`;
    b.onclick = () => { state.hidden.has(ci) ? state.hidden.delete(ci) : state.hidden.add(ci); b.classList.toggle('off'); applyHidden(); };
    b.onmouseenter = () => map.getLayer('v-hl') && map.setFilter('v-hl', ['==', ['get', 'ci'], ci]);
    b.onmouseleave = () => map.getLayer('v-hl') && map.setFilter('v-hl', ['==', ['get', 'ci'], -1]);
    el.append(b);
  });
}

// ---------- каталог
function filtered() {
  const q = state.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return state.maps.filter((m) => (!state.tom || m.tom === state.tom) && (!state.onlyGeo || m.geo) && q.every((w) => m._s.includes(w)));
}
const itemHTML = (m) => `<div class="item${state.cur === m ? ' cur' : ''}" data-id="${m.id}"><img loading="lazy" alt="" src="data/t/${m.id}.webp"><div><b>${esc(m.title)}</b><small>том ${m.tom}${m.of > 1 ? ` · ${m.n} из ${m.of}` : ''}${m.geo ? '<span class="badge">глобус</span>' : ''}${m.lg ? '<span class="badge alt">легенда</span>' : ''}</small></div></div>`;
const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
function list() {
  const ms = filtered(), el = $('list'); state.order = ms.map((m) => m.id);
  if (!ms.length) { el.innerHTML = '<div class="empty">Ничего не найдено</div>'; return; }
  if (state.q.trim()) { el.innerHTML = ms.slice(0, 300).map(itemHTML).join('') + (ms.length > 300 ? `<div class="empty">Показаны первые 300 из ${ms.length}</div>` : ''); return; }
  const secs = new Map();
  for (const m of ms) { const k = m.tom + '|' + m.section; if (!secs.has(k)) secs.set(k, []); secs.get(k).push(m); }
  const curKey = state.cur ? state.cur.tom + '|' + state.cur.section : null;
  el.innerHTML = [...secs].map(([k, arr]) => `<div class="sec${k === curKey ? ' open' : ''}" data-k="${esc(k)}"><button><span>${esc(arr[0].section)}</span><small>том ${arr[0].tom} · ${arr.length}</small></button><div class="items">${k === curKey ? arr.map(itemHTML).join('') : ''}</div></div>`).join('');
  el._secs = secs;
}
$('list').addEventListener('click', (e) => {
  const it = e.target.closest('.item'); if (it) return open(it.dataset.id);
  const sec = e.target.closest('.sec'); if (!sec) return;
  const items = sec.querySelector('.items');
  if (!items.childElementCount) items.innerHTML = $('list')._secs.get(sec.dataset.k).map(itemHTML).join('');
  sec.classList.toggle('open');
});
function chips() {
  const el = $('toms'); el.innerHTML = '';
  const mk = (t, label) => { const n = state.maps.filter((m) => !t || m.tom === t).length; const b = document.createElement('button'); b.className = 'chip' + (state.tom === t ? ' on' : ''); b.innerHTML = `<b>${label}</b><span>${n}</span>`; b.onclick = () => { state.tom = t; chips(); list(); }; el.append(b); };
  mk(0, 'Все'); for (const t of [1, 2, 3, 4]) mk(t, 'Том ' + t);
}

// ---------- управление
let qt; $('q').addEventListener('input', (e) => { clearTimeout(qt); qt = setTimeout(() => { state.q = e.target.value; list(); }, 120); });
$('onlygeo').onchange = (e) => { state.onlyGeo = e.target.checked; list(); };
$('mode-geo').onclick = () => { if (state.cur?.geo) { state.mode = state.userMode = 'geo'; syncMode(); render(); } };
$('mode-sheet').onclick = () => { state.mode = state.userMode = 'sheet'; syncMode(); render(); };
$('opacity').oninput = (e) => { $('opacity-v').textContent = e.target.value + '%'; if (map.getLayer('v-fill')) map.setPaintProperty('v-fill', 'fill-opacity', e.target.value / 100); };
$('raster').oninput = (e) => { $('raster-v').textContent = e.target.value + '%'; if (map.getLayer('raster')) map.setPaintProperty('raster', 'raster-opacity', e.target.value / 100); };
$('outline').onchange = (e) => map.getLayer('v-line') && map.setLayoutProperty('v-line', 'visibility', e.target.checked ? 'visible' : 'none');
$('globe').onchange = (e) => map.setProjection({ type: e.target.checked && state.mode === 'geo' ? 'globe' : 'mercator' });
$('legend-reset').onclick = () => { state.hidden.clear(); legend(); applyHidden(); };
$('collapse').onclick = () => { $('side').classList.add('hidden'); $('expand').hidden = false; };
$('expand').onclick = () => { $('side').classList.remove('hidden'); $('expand').hidden = true; };
$('theme').onclick = () => { const t = themeOf() === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = t; try { localStorage.setItem('theme', t); } catch {} render(); if (!state.cur) map.setStyle(BASEMAP[t]); };
$('share').onclick = async () => { try { await navigator.clipboard.writeText(location.href); toast('Ссылка скопирована'); } catch { toast(location.href); } };
$('dl-geojson').onclick = () => {
  const m = state.cur, doc = state.doc; if (!m || !doc) return;
  const gj = m.geo ? toGeoJSON(doc, m, 'geo', 4) : pixelGeoJSON(doc);
  gj.name = m.title; gj.source = m.page;
  gj.note = m.geo ? 'Координаты WGS 84 (долгота, широта). Свойство c — цвет класса на исходной карте.' : 'Лист без географической привязки: координаты в пикселях оригинала, ось Y направлена вверх.';
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(gj)], { type: 'application/geo+json' })); a.download = `atlas-${m.id}.geojson`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
};
function pixelGeoJSON(doc) {
  return { type: 'FeatureCollection', features: doc.f.map(([ci, , rings]) => ({ type: 'Feature', properties: { ci, c: doc.colors[ci] }, geometry: { type: 'Polygon', coordinates: rings.map((fl) => { const r = []; for (let i = 0; i < fl.length; i += 2) r.push([fl[i], doc.h - fl[i + 1]]); r.push(r[0]); return r; }) } })) };
}
const step = (d) => { const i = state.order.indexOf(state.cur?.id); const id = state.order[(i + d + state.order.length) % state.order.length]; if (id) open(id); };
$('prev').onclick = () => step(-1); $('next').onclick = () => step(1);
addEventListener('keydown', (e) => { if (e.target.tagName === 'INPUT') return; if (e.key === 'ArrowRight') step(1); if (e.key === 'ArrowLeft') step(-1); if (e.key === '/') { e.preventDefault(); $('q').focus(); } });
addEventListener('popstate', route);
let tt; function toast(s) { const t = $('toast'); t.textContent = s; t.hidden = false; clearTimeout(tt); tt = setTimeout(() => (t.hidden = true), 2600); }
function route() { const id = decodeURIComponent(location.hash.replace(/^#\/?/, '')); if (state.byId.has(id)) { if (state.cur?.id !== id) open(id, false); return true; } return false; }

// ---------- запуск
(async () => {
  const cat = await (await fetch('data/catalog.json')).json();
  state.maps = cat.maps;
  for (const m of state.maps) { m._s = `${m.title} ${m.section} том ${m.tom}`.toLowerCase(); state.byId.set(m.id, m); }
  const geo = state.maps.filter((m) => m.geo).length;
  $('stats').textContent = `${state.maps.length} карт · ${geo} на глобусе · 4 тома`;
  chips(); list();
  const start = () => { if (!route()) open(state.byId.has('2-383-1') ? '2-383-1' : (state.maps.find((m) => m.geo) || state.maps[0]).id, false); list(); document.querySelector('.item.cur')?.scrollIntoView({ block: 'center' }); };
  map.isStyleLoaded() ? start() : map.once('load', start);
})();
