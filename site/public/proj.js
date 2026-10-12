// Проекция атласа (равнопромежуточная коническая). Формулы совпадают с pipeline/geo.py,
// совпадение проверяет tests/test_proj.py.
const DEG = 180 / Math.PI;
const EARTH_R = 6378137;
const SHEET_SPAN = 6.0e6;   // условный размер листа в метрах Меркатора

// пиксель оригинала -> [долгота, широта]; P = [n, G, lon0, k, tx, ty, rot]
export function invProj(P, X, Y) {
  const [n, G, lon0, k, tx, ty, rot] = P;
  const u = (X - tx) / k;
  const v = -(Y - ty) / k;
  const c = Math.cos(rot);
  const s = Math.sin(rot);
  const x = c * u + s * v;
  const y = -s * u + c * v;
  return [lon0 + (Math.atan2(x, -y) / n) * DEG, (G - Math.hypot(x, y)) * DEG];
}

// лист без привязки кладётся в условную область карты, чтобы MapLibre показал его без искажений
export function sheetProj(w, h) {
  const scale = SHEET_SPAN / Math.max(w, h);
  return (X, Y) => {
    const mx = (X - w / 2) * scale;
    const my = (h / 2 - Y) * scale;
    return [(mx / EARTH_R) * DEG, (2 * Math.atan(Math.exp(my / EARTH_R)) - Math.PI / 2) * DEG];
  };
}
