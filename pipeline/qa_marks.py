"""QA picture of a sheet's marks: unit outlines with their keys, hand seeds, ink points and
lines over the original; legend swatches framed, the matched class colour beside each.
usage: qa_marks.py OUT.jpg ID [x0 y0 x1 y1] [SCALE]"""
import os, sys, json
import numpy as np, cv2
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import catalog, marks
DATA = os.path.join(ROOT, 'data'); OUT = os.path.join(ROOT, 'site', 'public', 'data')
KIND_BGR = [(0, 0, 230), (200, 0, 160), (0, 140, 0), (40, 40, 40), (30, 80, 140), (160, 0, 120), (0, 120, 200)]


def bgr(h):
    return (int(h[5:7], 16), int(h[3:5], 16), int(h[1:3], 16))


def main():
    out, mid = sys.argv[1], sys.argv[2]
    box = [int(v) for v in sys.argv[3:7]] if len(sys.argv) >= 7 else None
    scale = float(sys.argv[7]) if len(sys.argv) >= 8 else 1.0
    files = {m['id']: m['file'] for m in catalog.parse(os.path.join(DATA, 'pages'))}
    im = cv2.imread(os.path.join(DATA, 'img', files[mid]))
    doc = json.load(open(os.path.join(OUT, 'v', mid + '.json')))
    a = json.load(open(os.path.join(OUT, 'a', mid + '.json')))
    mk = marks.load(os.path.join(ROOT, 'marks', mid + '.json'))
    vis = (im * 0.75 + 64).astype(np.uint8)
    t = max(1, round(im.shape[1] / 1500))
    un = a.get('units')
    if un:
        tint = vis.copy()
        land = marks.land_mask(marks.raster(doc), mk['units'].get('water', []))
        tint[land] = (255, 0, 255)
        rng = np.random.default_rng(3)
        pal = rng.integers(40, 255, (len(un['keys']), 3))
        for ui, _, rings in un['f']:
            cv2.fillPoly(tint, [np.array(r, np.int32).reshape(-1, 2) for r in rings], [int(c) for c in pal[ui]])
        vis = cv2.addWeighted(vis, 0.6, tint, 0.4, 0)
        for ui, _, rings in un['f']:
            cv2.polylines(vis, [np.array(r, np.int32).reshape(-1, 2) for r in rings], True, (0, 0, 0), t)
        for ui, _, rings in un['f']:
            m = np.zeros(im.shape[:2], np.uint8)
            cv2.fillPoly(m, [np.array(rings[0], np.int32).reshape(-1, 2)], 1)
            if len(rings) > 1: cv2.fillPoly(m, [np.array(r, np.int32).reshape(-1, 2) for r in rings[1:]], 0)
            if m.sum() < 120: continue
            y, x = np.unravel_index(cv2.distanceTransform(m, cv2.DIST_L2, 3).argmax(), m.shape)
            cv2.putText(vis, un['keys'][ui], (int(x) - 8, int(y) + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5 * t, (255, 255, 255), 3 * t)
            cv2.putText(vis, un['keys'][ui], (int(x) - 8, int(y) + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5 * t, (180, 0, 0), t)
        for k, x, y in mk['units']['seeds']:
            cv2.circle(vis, (int(x), int(y)), 3 * t, (0, 160, 255), -1)
    kinds = sorted({p['kind'] for p in a.get('points', []) + a.get('lines', [])})
    for l in a.get('lines', []):
        cv2.polylines(vis, [np.array(l['xy'], np.int32).reshape(-1, 2)], False, KIND_BGR[kinds.index(l['kind']) % 7], 2 * t)
    for p in a.get('points', []):
        cv2.circle(vis, (p['x'], p['y']), 5 * t, KIND_BGR[kinds.index(p['kind']) % 7], 2 * t)
        if p.get('key'):
            cv2.putText(vis, str(p['key']), (p['x'] + 6, p['y'] - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45 * t, (0, 0, 0), t)
    for ci, its in a.get('legend', {}).get('classes', {}).items():
        for it in its:
            src = next(i for i in mk['legend']['items'] if i['key'] == it['key'])
            x, y, w, h = src['swatch']
            cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 0, 255), t)
            cv2.rectangle(vis, (x - w // 2 - 4, y), (x - 4, y + h), bgr(doc['colors'][int(ci)]), -1)
            cv2.putText(vis, f"{it['key']} {ci}", (x - w // 2 - 4, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4 * t, (0, 0, 200), t)
    for k in a.get('legend', {}).get('lost', []):
        x, y, w, h = next(i for i in mk['legend']['items'] if i['key'] == k)['swatch']
        cv2.rectangle(vis, (x, y), (x + w, y + h), (255, 0, 255), 2 * t)
    if box: vis = vis[box[1]:box[3], box[0]:box[2]]
    if scale != 1: vis = cv2.resize(vis, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    cv2.imwrite(out, vis, [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(out, vis.shape)


if __name__ == '__main__':
    main()
