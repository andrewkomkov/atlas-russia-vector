"""Legend QA sheet: for random labelled maps, the legend area of the original with a
frame around each swatch and its number; the assigned labels are printed to stdout.
usage: qa_legend.py OUT.jpg [COUNT] [SEED]"""
import os, sys, json, random, cv2, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import catalog, legend
DATA = os.path.join(ROOT, 'data'); OUT = os.path.join(ROOT, 'site', 'public', 'data')
out = sys.argv[1]; count = int(sys.argv[2]) if len(sys.argv) > 2 else 8; seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1
files = {m['id']: m['file'] for m in catalog.parse(os.path.join(DATA, 'pages'))}
ids = sorted(f[:-5] for f in os.listdir(os.path.join(OUT, 'l'))); random.Random(seed).shuffle(ids)
tiles = []
for mid in ids[:count]:
    doc = json.load(open(os.path.join(OUT, 'v', mid + '.json'))); lg = json.load(open(os.path.join(OUT, 'l', mid + '.json')))
    im = cv2.imread(os.path.join(DATA, 'img', files[mid]))
    sw = [s for s in legend.swatches(doc) if str(s['ci']) in lg['labels']]
    x0 = max(0, min(s['x'] for s in sw) - 30); y0 = max(0, min(s['y'] for s in sw) - 60)
    x1 = min(im.shape[1], max(s['x'] + s['w'] * 7 for s in sw)); y1 = min(im.shape[0], max(s['y'] + s['h'] for s in sw) + 30)
    print('==', mid)
    seen = {}
    for s in sw:
        n = seen.setdefault(s['ci'], len(seen) + 1)
        cv2.rectangle(im, (s['x'], s['y']), (s['x'] + s['w'], s['y'] + s['h']), (0, 0, 255), 2)
        cv2.putText(im, str(n), (s['x'] - 26, s['y'] + s['h'] - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    for ci, n in seen.items():
        print(f"  {n}: {lg['groups'].get(str(ci), '')} | {lg['labels'][str(ci)]}")
    c = im[y0:y1, x0:x1]; k = min(940 / c.shape[1], 520 / c.shape[0], 1.0); c = cv2.resize(c, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    t = np.full((540, 950, 3), 255, np.uint8); t[18:18 + c.shape[0], :c.shape[1]] = c
    cv2.putText(t, mid, (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 0, 0), 1); tiles.append(t)
while len(tiles) % 2: tiles.append(np.full_like(tiles[0], 255))
cv2.imwrite(out, np.vstack([np.hstack(tiles[i:i + 2]) for i in range(0, len(tiles), 2)]), [cv2.IMWRITE_JPEG_QUALITY, 82])
