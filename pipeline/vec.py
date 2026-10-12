"""Raster thematic map -> colour-region polygons in pixel space."""
import numpy as np, cv2
from scipy import ndimage as ndi

MAXW = 2400
PALETTE_GAP = 6.0     # dE; a k-means centre closer to a legend colour repeats it

def to_lab(im):
    lab = cv2.cvtColor(im, cv2.COLOR_BGR2Lab).astype(np.float32)
    lab[..., 0] *= 100 / 255.0; lab[..., 1:] -= 128
    return lab

def quantize(im, K=32, merge=7.0, seed=0, palette=None):
    """-> (label image, Lab centres). With a palette (legend colours) its colours are the
    first classes; k-means only adds the colours the legend does not have."""
    lab = to_lab(im)
    flat = lab.reshape(-1, 3)
    rng = np.random.default_rng(seed)
    samp = flat[rng.choice(len(flat), min(len(flat), 150000), replace=False)]
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 25, 0.5)
    cv2.setRNGSeed(seed)                             # k-means draws from OpenCV's own generator
    _, sl, cen = cv2.kmeans(samp, K, None, crit, 2, cv2.KMEANS_PP_CENTERS)
    w = np.bincount(sl.ravel(), minlength=K).astype(float)
    cen = cen.astype(float)
    # greedy merge of near-identical centres
    while True:
        d = np.linalg.norm(cen[:, None] - cen[None], axis=2); np.fill_diagonal(d, 1e9)
        i, j = np.unravel_index(d.argmin(), d.shape)
        if d[i, j] > merge or len(cen) <= 2: break
        cen[i] = (cen[i] * w[i] + cen[j] * w[j]) / (w[i] + w[j]); w[i] += w[j]
        cen = np.delete(cen, j, 0); w = np.delete(w, j)
    cen = cen[w > 0.0004 * w.sum()]
    if palette is not None and len(palette):
        pal = np.asarray(palette, float)
        far = np.linalg.norm(cen[:, None] - pal[None], axis=2).min(1) > PALETTE_GAP
        cen = np.vstack([pal, cen[far]])[:255]
    labels = np.empty(len(flat), np.uint8)
    c32 = cen.astype(np.float32)
    step = 4_000_000 // len(c32)                     # keeps the distance table near 50 MB
    for s in range(0, len(flat), step):
        ch = flat[s:s + step]
        labels[s:s + step] = ((ch[:, None] - c32[None]) ** 2).sum(2).argmin(1)
    return labels.reshape(im.shape[:2]), cen

def lab2hex(c):
    px = np.array([[[c[0] * 2.55, c[1] + 128, c[2] + 128]]], np.float32).clip(0, 255).astype(np.uint8)
    b, g, r = cv2.cvtColor(px, cv2.COLOR_Lab2BGR)[0, 0]
    return '#%02x%02x%02x' % (r, g, b)

def clean(im):
    """Erase thin strokes (labels, rivers, borders): mark them with a black-hat /
    top-hat test and refill from the nearest untouched pixel."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    bh = cv2.morphologyEx(im, cv2.MORPH_BLACKHAT, k).max(2)
    th = cv2.morphologyEx(im, cv2.MORPH_TOPHAT, k).max(2)
    ink = ((bh > 22) | (th > 40)).astype(np.uint8)
    ink = cv2.dilate(ink, np.ones((3, 3), np.uint8))
    if ink.mean() < 0.6:
        idx = ndi.distance_transform_edt(ink, return_distances=False, return_indices=True)
        im = im[idx[0], idx[1]]
    return cv2.medianBlur(im, 5)

def smooth_labels(lab, K, minarea):
    H, W = lab.shape
    best = np.zeros((H, W), np.uint8); win = np.zeros((H, W), np.uint8)
    for i in range(K):                               # majority vote in a 5 x 5 window, one class at a time
        v = cv2.blur((lab == i).astype(np.uint8) * 255, (5, 5))
        m = v > best
        best[m] = v[m]; win[m] = i
    lab = win
    bad = np.zeros((H, W), bool)
    for i in range(K):
        n, cc, st, _ = cv2.connectedComponentsWithStats((lab == i).astype(np.uint8), connectivity=4)
        small = np.nonzero(st[:, cv2.CC_STAT_AREA] < minarea)[0]
        small = small[small > 0]
        if len(small): bad |= np.isin(cc, small)
    if bad.any():
        idx = ndi.distance_transform_edt(bad, return_distances=False, return_indices=True)
        lab = lab[idx[0], idx[1]]
    return lab

def polygons(lab, K, eps=0.9, minarea=25):
    """-> list of (label, [rings]) ; ring = Nx2 int array (x,y), first ring outer."""
    out = []
    k3 = np.ones((3, 3), np.uint8)
    for i in range(K):
        m = (lab == i).astype(np.uint8)
        if not m.any(): continue
        m = cv2.dilate(m, k3)
        cs, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if hier is None: continue
        hier = hier[0]
        for ci, c in enumerate(cs):
            if hier[ci][3] != -1 or cv2.contourArea(c) < minarea: continue
            rings = [cv2.approxPolyDP(c, eps, True)[:, 0]]
            if len(rings[0]) < 3: continue
            h = hier[ci][2]
            while h != -1:
                if cv2.contourArea(cs[h]) >= minarea:
                    r = cv2.approxPolyDP(cs[h], eps, True)[:, 0]
                    if len(r) >= 3: rings.append(r)
                h = hier[h][0]
            out.append((i, rings))
    return out

def process(im, region=None, level=0, palette=None):
    """region: optional uint8 mask (same size as im) of 'inside the mapped territory';
    palette: optional Lab colours of the legend swatches (see quantize)."""
    h0, w0 = im.shape[:2]
    s = min(1.0, MAXW / w0)
    if s < 1:
        im = cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        if region is not None: region = cv2.resize(region, (im.shape[1], im.shape[0]), interpolation=cv2.INTER_NEAREST)
    H, W = im.shape[:2]
    lab, cen = quantize(clean(im), K=(32, 20, 12)[level], palette=palette)
    K = len(cen)
    lab = smooth_labels(lab, K, max(30, int(H * W * (1.2e-5, 5e-5, 2e-4)[level])))
    white = [i for i, c in enumerate(cen) if c[0] > 96.5 and np.hypot(c[1], c[2]) < 4.5]
    feats = []
    parts = [(1, region > 0), (0, region == 0)] if region is not None else [(0, None)]
    for inside, pm in parts:
        l2 = lab if pm is None else np.where(pm, lab, 255).astype(np.uint8)
        for i, rings in polygons(l2, K, eps=(0.9, 1.3, 2.0)[level]):
            if i in white: continue
            feats.append([i, inside, [np.round(r / s).astype(int).ravel().tolist() for r in rings]])
    share = np.bincount(lab.ravel(), minlength=K) / lab.size
    return {'w': w0, 'h': h0, 'colors': [lab2hex(c) for c in cen], 'share': [round(float(x), 4) for x in share], 'f': feats}

def render(doc, scale=1.0):
    img = np.full((int(doc['h'] * scale), int(doc['w'] * scale), 3), 255, np.uint8)
    for ci, inside, rings in sorted(doc['f'], key=lambda f: -len(f[2][0])):
        hx = doc['colors'][ci]; col = (int(hx[5:7], 16), int(hx[3:5], 16), int(hx[1:3], 16))
        cv2.fillPoly(img, [(np.array(r).reshape(-1, 2) * scale).astype(np.int32) for r in rings], col)
    return img
