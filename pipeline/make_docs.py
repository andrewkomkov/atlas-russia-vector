"""Render the README figures for one map: original, strokes removed, colour classes,
vector polygons, outline fit. usage: make_docs.py MAP_ID OUT_DIR"""
import os, sys, json, cv2, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import catalog, georef, vec
DATA = os.path.join(ROOT, 'data'); NE = os.path.join(DATA, 'ne', 'countries50.geojson')
mid, out = sys.argv[1], sys.argv[2]
m = next(x for x in catalog.parse(os.path.join(DATA, 'pages')) if x['id'] == mid)
im = cv2.imread(os.path.join(DATA, 'img', m['file']))
W = 1400; s = W / im.shape[1]
save = lambda name, a: cv2.imwrite(os.path.join(out, name), cv2.resize(a, None, fx=W / a.shape[1], fy=W / a.shape[1], interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 84])
save('step1-original.jpg', im)
cl = vec.clean(im); save('step2-clean.jpg', cl)
lab, cen = vec.quantize(cl)
pal = np.array([[int(h[5:7], 16), int(h[3:5], 16), int(h[1:3], 16)] for h in map(vec.lab2hex, cen)], np.uint8)
save('step3-classes.jpg', pal[lab])
g = georef.fit(im, NE)
save('step4-georef.jpg', georef.overlay(im, g['P'], NE))
doc = vec.process(im, georef.region_mask(g['P'], im.shape, NE) if g['ok'] else None)
r = vec.render(doc)
for ci, inside, rings in doc['f']:
    cv2.polylines(r, [np.array(q).reshape(-1, 2).astype(np.int32) for q in rings], True, (60, 60, 60), 1)
save('step5-vector.jpg', r)
# zoomed crop to show strokes removal
x0, y0, cw, ch = int(im.shape[1] * .05), int(im.shape[0] * .28), int(im.shape[1] * .26), int(im.shape[0] * .30)
crop = lambda a: a[y0:y0 + ch, x0:x0 + cw]
cv2.imwrite(os.path.join(out, 'zoom.jpg'), np.hstack([crop(im), np.full((ch, 12, 3), 255, np.uint8), crop(cl), np.full((ch, 12, 3), 255, np.uint8), crop(r)]), [cv2.IMWRITE_JPEG_QUALITY, 86])
print(g)
