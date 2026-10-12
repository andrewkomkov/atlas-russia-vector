"""Automatic georeferencing of all-Russia maps by matching the country outline.

The projection (equidistant conic, parameters fitted on tom2/383 and stored in
ref.json) is assumed; scale, shift and rotation are searched per image and the
projection is then refined. A fit is accepted only above the quality gate below.
"""
import json, os, numpy as np, cv2
from scipy.optimize import minimize
from geo import load_russia, fwd

HERE = os.path.dirname(os.path.abspath(__file__))
REF = json.load(open(os.path.join(HERE, 'ref.json')))['P']

# quality gate (constitution, principle II)
MIN_INLIER = 0.70      # share of outline points lying on an image edge of the same direction
MIN_LIFT = 0.40        # ... above the share expected by chance
MIN_INSIDE = 0.90      # share of the outline that falls inside the image
MIN_SPAN = 0.68        # outline width as a share of the image width; below it the match is an inset or one of several maps
MAX_ROT = 0.14         # rad, deviation from the reference rotation
TOL = 2.5              # px at the working width
WORK_W = 900
NB = 6                 # edge direction bins over 180 degrees

_rings = None
def rings(ne_path):
    """-> (rings, dense points, index of the next point along the ring)"""
    global _rings
    if _rings is None:
        rs = [r for r in load_russia(ne_path) if len(r) > 40]
        dense, nxt, off = [], [], 0
        for r in rs:                      # densify to ~0.15 deg
            seg = [np.linspace(r[i], r[i + 1], max(2, int(np.abs(r[i + 1] - r[i]).max() / 0.15) + 1))[:-1] for i in range(len(r) - 1)]
            d = np.vstack(seg); dense.append(d)
            nxt.append(off + (np.arange(len(d)) + 1) % len(d)); off += len(d)
        _rings = (rs, np.vstack(dense), np.concatenate(nxt))
    return _rings

def edge_maps(im):
    """Edges split by direction: uint8 [NB, H, W]; every edge pixel is put into
    its own bin and the nearest neighbouring bin."""
    s = WORK_W / im.shape[1]
    sm = cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    sm = cv2.medianBlur(cv2.morphologyEx(sm, cv2.MORPH_CLOSE, k), 3)
    e = np.zeros(sm.shape[:2], np.uint8)
    for c in range(3):
        e |= cv2.Canny(sm[..., c], 25, 70)
    f = cv2.GaussianBlur(sm, (0, 0), 1.0).astype(np.float32)
    gx, gy = cv2.Sobel(f, cv2.CV_32F, 1, 0), cv2.Sobel(f, cv2.CV_32F, 0, 1)
    ch = (gx ** 2 + gy ** 2).argmax(2)
    gx, gy = np.take_along_axis(gx, ch[..., None], 2)[..., 0], np.take_along_axis(gy, ch[..., None], 2)[..., 0]
    pos = (np.arctan2(gy, gx) % np.pi) / np.pi * NB          # normal direction, 0..NB
    b0 = np.floor(pos).astype(int) % NB
    b1 = np.where(pos - np.floor(pos) >= 0.5, b0 + 1, b0 - 1) % NB
    E = np.zeros((NB,) + e.shape, np.uint8)
    ys, xs = np.nonzero(e)
    E[b0[ys, xs], ys, xs] = 1; E[b1[ys, xs], ys, xs] = 1
    return E, s

def _proj(P, pts, nxt):
    x, y = fwd(P, pts[:, 0], pts[:, 1])
    tx, ty = x[nxt] - x, y[nxt] - y
    nb = np.floor(((np.arctan2(ty, tx) + np.pi / 2) % np.pi) / np.pi * NB).astype(int) % NB   # normal bin
    return x, y, nb

def _score(P, pts, nxt, dts, W, H):
    x, y, nb = _proj(P, pts, nxt)
    xi, yi = np.round(x).astype(int), np.round(y).astype(int)
    ok = (xi >= 0) & (xi < W) & (yi >= 0) & (yi < H)
    return ok, dts[nb[ok], yi[ok], xi[ok]]

def fit(im, ne_path):
    """-> dict(P=[7 params in original pixels], inlier, lift, inside, ok)"""
    rs, pts, nxt = rings(ne_path)
    E, s = edge_maps(im)
    _, H, W = E.shape
    dts = np.stack([cv2.distanceTransform((E[b] == 0).astype(np.uint8), cv2.DIST_L2, 3) for b in range(NB)])
    chance = float((dts <= TOL).mean())
    # --- coarse search at 1/3 of the working size: template matching per direction bin
    c = 3
    small = [cv2.GaussianBlur(cv2.resize(E[b] * 255, None, fx=1 / c, fy=1 / c, interpolation=cv2.INTER_AREA).astype(np.float32), (0, 0), 1.2) for b in range(NB)]
    h2, w2 = small[0].shape
    pad = int(0.25 * w2)
    small = [cv2.copyMakeBorder(m, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0) for m in small]
    P0 = np.array(REF, float); P0[3:6] = [1, 0, 0]
    cands = []
    for rot in np.radians([-6, -3, 0, 3, 6]):
        Pr = P0.copy(); Pr[6] += rot
        ux, uy, nb = _proj(Pr, pts, nxt)
        x0, y0 = ux.min(), uy.min()
        ux, uy = ux - x0, uy - y0
        ar = uy.max() / ux.max()
        for bw in np.geomspace(0.28 * w2, 1.35 * w2, 34):
            tw, th = int(bw) + 3, int(bw * ar) + 3
            if th >= small[0].shape[0] or tw >= small[0].shape[1]: continue
            k = bw / ux.max()
            acc, npts = None, 0
            for b in range(NB):
                sel = nb == b
                if not sel.any(): continue
                T = np.zeros((th, tw), np.float32)
                T[np.round(uy[sel] * k).astype(int) + 1, np.round(ux[sel] * k).astype(int) + 1] = 1
                r = cv2.matchTemplate(small[b], T, cv2.TM_CCORR); npts += T.sum()
                acc = r if acc is None else acc + r
            _, mx, _, loc = cv2.minMaxLoc(acc / npts)
            cands.append((mx, np.array([Pr[0], Pr[1], Pr[2], k * c, (loc[0] - pad + 1 - x0 * k) * c, (loc[1] - pad + 1 - y0 * k) * c, Pr[6]])))
    if not cands: return None
    cands.sort(key=lambda t: -t[0])
    picked = []                       # best candidates that differ in scale or place
    for mx, Pc in cands:
        if all(abs(np.log(Pc[3] / Q[3])) > 0.08 or np.hypot(Pc[4] - Q[4], Pc[5] - Q[5]) > 0.05 * W for Q in picked):
            picked.append(Pc)
        if len(picked) == 6: break
    # --- refine scale/shift/rotation, then let the cone constant move a little
    def cost(q, free, base, trunc):
        Q = base.copy(); Q[free] = q
        ok, d = _score(Q, pts, nxt, dts, W, H)
        pen = 400 * max(0.0, abs(Q[0] - REF[0]) - 0.04) + 400 * max(0.0, abs(Q[1] - REF[1]) - 0.05)
        return (np.minimum(d, trunc).sum() + trunc * (~ok).sum()) / len(pts) + pen
    def run(P, stages):
        for free, steps, trunc in stages:
            q0 = P[free]
            r = minimize(cost, q0, args=(free, P, trunc), method='Nelder-Mead',
                         options={'initial_simplex': q0 + np.vstack([np.zeros(len(free)), np.diag(steps)]), 'xatol': 1e-3, 'fatol': 1e-4, 'maxiter': 1500})
            P = P.copy(); P[free] = r.x
        ok, d = _score(P, pts, nxt, dts, W, H)
        return P, (float((d <= TOL).sum()) / len(pts))
    best = None
    for Pc in picked:
        Pc, sc = run(Pc, [([3, 4, 5, 6], [Pc[3] * .03, 6, 6, .02], 12), ([3, 4, 5, 6], [Pc[3] * .01, 2, 2, .006], 5)])
        if best is None or sc > best[1]: best = (Pc, sc)
    P, _ = run(best[0], [([0, 1, 3, 4, 5, 6], [.006, .006, best[0][3] * .008, 2, 2, .005], 4)])
    ok, d = _score(P, pts, nxt, dts, W, H)
    inside = float(ok.mean()); inlier = float((d <= TOL).mean()) if ok.any() else 0.0
    Pf = P.copy(); Pf[3:6] /= s
    px, _, _ = _proj(P, pts, nxt)
    span = float((px.max() - px.min()) / W)
    lift = inlier - chance
    # busy maps (relief, dense hatching) have a high chance level: accept a lower lift
    # there, but only for a near-perfect outline that spans most of the sheet
    strong = (inlier >= MIN_INLIER and lift >= MIN_LIFT) or (inlier >= 0.85 and lift >= 0.25 and span >= 0.60)
    good = bool(strong and inside >= MIN_INSIDE and span >= MIN_SPAN and abs(P[6] - REF[6]) <= MAX_ROT)
    return {'P': [float(v) for v in Pf], 'inlier': round(inlier, 3), 'lift': round(inlier - chance, 3),
            'inside': round(inside, 3), 'span': round(span, 3), 'ok': good}

def region_mask(P, shape, ne_path, grow=3):
    m = np.zeros(shape[:2], np.uint8)
    for r in load_russia(ne_path):
        x, y = fwd(P, r[:, 0], r[:, 1])
        cv2.fillPoly(m, [np.stack([x, y], 1).round().astype(np.int32)], 1)
    return cv2.dilate(m, np.ones((grow * 2 + 1, grow * 2 + 1), np.uint8))

def overlay(im, P, ne_path):
    vis = im.copy()
    for r in load_russia(ne_path):
        x, y = fwd(P, r[:, 0], r[:, 1])
        cv2.polylines(vis, [np.stack([x, y], 1).round().astype(np.int32)], True, (0, 0, 255), max(2, im.shape[1] // 900))
    return vis
