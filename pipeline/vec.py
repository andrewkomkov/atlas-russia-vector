"""Raster thematic map -> colour-region polygons in pixel space."""
import numpy as np, cv2
from scipy import ndimage as ndi

MAXW = 2400
PALETTE_GAP = 6.0     # dE; a k-means centre closer to a legend colour repeats it
LINE_DT90 = 7.0       # px at MAXW wide; a class whose 90th distance-to-edge percentile is below is thin
LINE_LONG = 10        # a thin class is a line when its longest piece is this many times its width; dots are not
SPECK_SHARE = 3e-4    # of the sheet; a smaller blob enclosed by one class is a label remnant
WHITE_SPECK = 10      # paper white inside a fill is a label cluster up to this many specks in size
SPECK_DE = 15.0       # dE; a remnant is a blend of the fill around it, a real small class has its own colour
RIBBON_DE = 8.0       # dE; a thin stroke this close to a legend colour is a ribbon class, not ink

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

def clean(im, palette=None):
    """Erase thin strokes (labels, rivers, borders): mark them with a black-hat /
    top-hat test and refill from the nearest untouched pixel. With a palette (legend
    colours) a thin stroke of a legend colour is a ribbon class and stays."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    bh = cv2.morphologyEx(im, cv2.MORPH_BLACKHAT, k).max(2)
    th = cv2.morphologyEx(im, cv2.MORPH_TOPHAT, k).max(2)
    ink = (bh > 22) | (th > 40)
    if palette is not None and len(palette):
        lab = to_lab(im)
        d = np.min([np.linalg.norm(lab - p, axis=2) for p in np.asarray(palette, np.float32)], axis=0)
        ink &= d > RIBBON_DE
    ink = ink.astype(np.uint8)
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

def _refill(lab, bad):
    """Give every bad pixel the label of the nearest good one."""
    if not bad.any() or bad.all(): return lab
    idx = ndi.distance_transform_edt(bad, return_distances=False, return_indices=True)
    return lab[idx[0], idx[1]]

def drop_lines(lab, K, keep=()):
    """Classes that are nowhere thick (the state border band, antialias halos) are strokes,
    not areas: their pixels take the neighbouring class. Legend classes (keep) stay."""
    bad = np.zeros(lab.shape, bool)
    limit = LINE_DT90 * lab.shape[1] / MAXW            # a small inset draws its classes thinner
    for i in range(K):
        if i in keep: continue
        m = (lab == i).astype(np.uint8)
        if not m.any(): continue
        dt90 = np.percentile(cv2.distanceTransform(m, cv2.DIST_L2, 3)[m > 0], 90)
        if dt90 >= limit: continue
        st = cv2.connectedComponentsWithStats(m, connectivity=8)[2][1:]
        if st[:, 2:4].max() > LINE_LONG * 2 * dt90: bad |= m > 0
    return _refill(lab, bad)

def drop_specks(lab, cen, keep=(), white=()):
    """A small blob enclosed by a single class of a close colour (or paper white) is what is
    left of a label or a number: it takes the enclosing class. Legend classes keep their blobs."""
    K = len(cen)
    limit = SPECK_SHARE * lab.size
    bad = np.zeros(lab.shape, bool)
    k3 = np.ones((3, 3), np.uint8)
    for i in range(K):
        if i in keep and i not in white: continue
        n, cc, st, _ = cv2.connectedComponentsWithStats((lab == i).astype(np.uint8), connectivity=8)
        for c in np.nonzero(st[1:, cv2.CC_STAT_AREA] < limit * (WHITE_SPECK if i in white else 1))[0] + 1:
            x, y, w, h = st[c, :4]
            x0, y0 = max(0, x - 1), max(0, y - 1)
            sub = cc[y0:y + h + 1, x0:x + w + 1] == c
            ring = cv2.dilate(sub.astype(np.uint8), k3).astype(bool) & ~sub
            around = np.unique(lab[y0:y + h + 1, x0:x + w + 1][ring])
            if len(around) != 1: continue
            if i in white or np.linalg.norm(cen[i] - cen[around[0]]) < SPECK_DE:
                bad[y0:y + h + 1, x0:x + w + 1] |= sub
    return _refill(lab, bad)

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

def legend_classes(lab, K, region, scale):
    """Classes drawn as legend swatches: a thin ribbon or a few small dots of such a class is
    data, not a stroke. Found the way legend.swatches finds them, before any cleanup."""
    import legend
    l2 = lab if region is None else np.where(region > 0, 255, lab).astype(np.uint8)
    H, W = lab.shape
    doc = {'w': W * scale, 'f': [[i, 0, [(r * scale).ravel().tolist() for r in rings]] for i, rings in polygons(l2, K)]}
    return {s['ci'] for s in legend.swatches(doc)}

def process(im, region=None, level=0, palette=None, ribbons=True):
    """region: optional uint8 mask (same size as im) of 'inside the mapped territory';
    palette: optional Lab colours of the legend swatches (see quantize);
    ribbons: keep thin strokes of a legend colour (see clean)."""
    h0, w0 = im.shape[:2]
    s = min(1.0, MAXW / w0)
    if s < 1:
        im = cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        if region is not None: region = cv2.resize(region, (im.shape[1], im.shape[0]), interpolation=cv2.INTER_NEAREST)
    H, W = im.shape[:2]
    lab, cen = quantize(clean(im, palette if ribbons else None), K=(32, 20, 12)[level], palette=palette)
    K = len(cen)
    minarea = max(30, int(H * W * (1.2e-5, 5e-5, 2e-4)[level]))
    lab = smooth_labels(lab, K, minarea)
    white = [i for i, c in enumerate(cen) if c[0] > 96.5 and np.hypot(c[1], c[2]) < 4.5]
    keep = set(range(len(palette))) if palette is not None else set()
    keep |= legend_classes(lab, K, region, w0 / W)
    cleaned = drop_specks(drop_lines(lab, K, keep), cen, keep, white)
    if (cleaned != lab).any():                          # nearest-pixel refill leaves ragged edges
        lab = smooth_labels(cleaned, K, minarea)
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
