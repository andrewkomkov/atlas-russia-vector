"""Fit the atlas projection on the reference map tom2/383 from city control points.
usage: fit_ref.py data/img/maps2__383_1.jpg data/ne/countries50.geojson OUT_DIR
Writes OUT_DIR/ref.json (copy it to pipeline/ref.json) and OUT_DIR/fit.jpg for a visual check.
Control points are in pixels of a 2000 px wide preview, hence the 1.35 factor."""
import sys, json, numpy as np, cv2
from scipy.optimize import least_squares
sys.path.insert(0, sys.argv[0].rsplit('/', 1)[0])
from geo import *
img_path, ne_path, out = sys.argv[1:4]
G = """Калининград 122 262 54.71 20.51
Уэлен 1800 43 66.16 190.2
Анадырь 1806 188 64.73 177.5
Певек 1632 196 69.7 170.3
Хатанга 1122 466 71.98 102.5
Норильск 980 530 69.35 88.2
Якутск 1461 653 62.03 129.73
Магадан 1727 541 59.56 150.8
Салехард 819 513 66.53 66.6
Охотск 1653 611 59.36 143.2
Тура 1104 676 64.28 100.2
Верхоянск 1433 501 67.55 133.39
Палана 1825 455 59.08 159.95
Алдан 1449 762 58.6 125.4
Жиганск 1341 563 66.77 123.37
Туруханск 965 621 65.8 87.96
Хабаровск 1718 934 48.48 135.07
Сыктывкар 523 515 61.67 50.81
Пермь 517 637 58.0 56.25
Среднеколымск 1590 364 67.45 153.7
Зырянка 1607 425 65.73 150.9
Олёкминск 1366 741 60.37 120.42
Усть-Камчатск 1905 474 56.22 162.47
Махачкала 124 836 42.98 47.5
Владивосток 1727 1090 43.12 131.89
Иркутск 1140 994 52.29 104.3"""
rows = [l.split() for l in G.splitlines()]
names = [r[0] for r in rows]
px = np.array([[float(r[1]), float(r[2])] for r in rows]) * 1.35
ll = np.array([[float(r[4]), float(r[3])] for r in rows])
def res(P):
    x, y = fwd(P, ll[:, 0], ll[:, 1]); return np.concatenate([x - px[:, 0], y - px[:, 1]])
best = None
for p1, p2 in [(47, 62), (50, 70), (45, 67)]:
    n_, G_ = conic(p1, p2)
    r = least_squares(res, [n_, G_, 100, 2000, 1350, -500, 0], loss='soft_l1', f_scale=10, x_scale=[.1, .1, 5, 300, 300, 300, .05])
    if best is None or r.cost < best.cost: best = r
P = best.x
e = res(P); e = np.hypot(e[:len(px)], e[len(px):])
for nm, d in sorted(zip(names, e), key=lambda t: -t[1]): print(f'{nm:22s}{d:6.1f}')
print('P', P.tolist(), 'median', np.median(e))
im = cv2.imread(img_path)
json.dump({'P': P.tolist(), 'size': [im.shape[1], im.shape[0]]}, open(out + '/ref.json', 'w'))
vis = im.copy()
for r in load_russia(ne_path):
    x, y = fwd(P, r[:, 0], r[:, 1])
    cv2.polylines(vis, [np.stack([x, y], 1).round().astype(np.int32)], True, (0, 0, 255), 2)
cv2.imwrite(out + '/fit.jpg', cv2.resize(vis, None, fx=0.74, fy=0.74))
