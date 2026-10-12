"""Contact sheet of accepted georeferences: outline drawn over each map.
usage: qa_georef.py OUT.jpg [ID_PREFIX] [START] [COUNT] [worst]
"worst" sorts accepted fits by rising quality, so the doubtful ones come first."""
import os, sys, json, glob, cv2, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import catalog, georef
DATA = os.path.join(ROOT, 'data'); NE = os.path.join(DATA, 'ne', 'countries50.geojson')
out, pref = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else '')
start, count = int(sys.argv[3]) if len(sys.argv) > 3 else 0, int(sys.argv[4]) if len(sys.argv) > 4 else 48
files = {m['id']: m['file'] for m in catalog.parse(os.path.join(DATA, 'pages'))}
metas = sorted((json.load(open(f)) for f in glob.glob(os.path.join(DATA, 'meta', pref + '*.json'))), key=lambda m: m['id'])
metas = [m for m in metas if 'geo' in m]
if 'worst' in sys.argv: metas.sort(key=lambda m: m['q']['lift'] + m['q']['inlier'])
metas = metas[start:start + count]
cols, cw, ch = 6, 320, 230
sheet = np.full(((len(metas) + cols - 1) // cols * ch, cols * cw, 3), 255, np.uint8)
for i, m in enumerate(metas):
    im = cv2.imread(os.path.join(DATA, 'img', files[m['id']]))
    v = georef.overlay(im, m['geo'], NE); s = min(cw / v.shape[1], (ch - 16) / v.shape[0])
    v = cv2.resize(v, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    y, x = i // cols * ch, i % cols * cw
    sheet[y + 16:y + 16 + v.shape[0], x:x + v.shape[1]] = v
    cv2.putText(sheet, f"{m['id']} {m['q']['inlier']}/{m['q']['lift']}", (x + 2, y + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 180), 1)
cv2.imwrite(out, sheet, [cv2.IMWRITE_JPEG_QUALITY, 80]); print(len(metas), 'maps')
