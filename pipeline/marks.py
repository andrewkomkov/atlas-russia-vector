"""Sheet marks (specs/007-fauna-sheets): legend tables, unit numbers, ink symbols and hand
traced points and lines written down by a person in marks/<id>.json, turned into data here.
Every coordinate is in pixels of the original sheet, as in data/v/<id>.json."""
import json, re, html
import numpy as np, cv2
from scipy import ndimage as ndi
import vec

SWATCH_DE = 12.0        # dE; a swatch farther than this from every vector class has no class
SEED_R = 4              # px; radius of the marker painted at a seed point
EDGE_K = 8.0            # elevation per dE of colour step on the cleaned sheet
LINE_H = 50             # elevation of a grey outline stroke; hatching is drawn with the same ink
LINE_BH = 14            # black-hat depth of an outline stroke, L scaled to 0..255
LINE_CHROMA = 16        # an outline is grey; a river is blue and must not stop a unit
CLASS_H = 120           # elevation where the vector class changes
GEO_STEP = 2            # px; the path search runs on every second pixel
RELIEF_UNIT = 12.0      # relief at which a step costs twice a flat step
SNAP_DE = 8.0           # dE; a seed moves onto a pixel this close to its swatch colour
WATER_DE = 6.0          # dE; water floods over pixels this close to its sample
ISLAND_R = 120          # px; reach of the land added around a seed off the outline
LAND_HOLE = 4e-4        # share of the sheet; a smaller gap between land polygons is land
INK_MIN = 6             # px; smaller ink specks are print noise
INK_POINT = 30          # px; a shorter ink blob is a point symbol, a longer one a line
INK_JOIN = 5            # px; dashes closer than this are joined before thinning


def load(path):
    return json.load(open(path, encoding='utf-8'))


def hex2lab(h):
    px = np.array([[[int(h[5:7], 16), int(h[3:5], 16), int(h[1:3], 16)]]], np.uint8)
    return vec.to_lab(px)[0, 0].astype(float)


def raster(doc, inside_only=True):
    """Class index of every pixel from the vector, 255 where no polygon lies."""
    out = np.full((doc['h'], doc['w']), 255, np.uint8)
    for ci, inside, rings in sorted(doc['f'], key=lambda f: -len(f[2][0])):
        if inside_only and not inside: continue
        cv2.fillPoly(out, [np.array(r, np.int32).reshape(-1, 2) for r in rings], int(ci))
    return out


def swatch_colour(im, box):
    """Median Lab colour of the inner half of a swatch box (x, y, w, h)."""
    x, y, w, h = box
    mx, my = max(1, w // 4), max(1, h // 4)
    return np.median(vec.to_lab(im[y + my:y + h - my, x + mx:x + w - mx]).reshape(-1, 3), 0).astype(float)


def legend_table(im, doc, items):
    """-> ({class: [items]}, [items without a class]). The swatch colour picks the class, so a
    label never depends on where the recogniser put it. One class may carry several items:
    the legend printed them with one ink."""
    cen = np.array([hex2lab(c) for c in doc['colors']])
    by_class, lost = {}, []
    for it in items:
        if 'swatch' not in it: continue
        d = np.linalg.norm(cen - swatch_colour(im, it['swatch']), axis=1)
        ci = int(d.argmin())
        row = {**it, 'de': round(float(d[ci]), 1)}
        if d[ci] > SWATCH_DE: lost.append(row)
        else: by_class.setdefault(ci, []).append(row)
    return by_class, lost


def steps(img, r):
    """Largest difference across 2 r px in four directions, per pixel."""
    d = np.zeros(img.shape[:2], np.float32)
    for dy, dx in ((0, r), (r, 0), (r, r), (r, -r)):
        a = np.roll(img, (dy, dx), (0, 1)); b = np.roll(img, (-dy, -dx), (0, 1))
        d = np.maximum(d, np.linalg.norm((a - b).reshape(*img.shape[:2], -1), axis=2))
    return d


def elevation(im, cls, edge_k=EDGE_K, line_h=LINE_H, class_h=CLASS_H, tex_k=0.0):
    """Relief for the unit growth: colour steps of the cleaned sheet, grey outline strokes,
    the edges of the vector classes and, with tex_k, the edges of a hatching: the cleaned
    sheet has lost the hatch, the ink density around a pixel keeps it."""
    clean = vec.clean(im)
    lab = vec.to_lab(cv2.GaussianBlur(clean, (0, 0), 1.5))
    e = steps(lab, 2) * edge_k
    if tex_k:
        ink = cv2.GaussianBlur(np.abs(vec.to_lab(im) - vec.to_lab(clean)), (0, 0), 6)
        e = np.maximum(e, steps(ink, 6) * tex_k)
    raw = vec.to_lab(im)
    L = (raw[..., 0] * 2.55).astype(np.uint8)
    bh = cv2.morphologyEx(L, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    grey = (bh > LINE_BH) & (np.hypot(raw[..., 1], raw[..., 2]) < LINE_CHROMA)
    e = np.maximum(e, grey * line_h)
    if cls is not None:
        edge = (cls != np.roll(cls, 1, 0)) | (cls != np.roll(cls, 1, 1))
        e = np.maximum(e, cv2.dilate(edge.astype(np.uint8), np.ones((3, 3), np.uint8)) * class_h)
    return np.clip(e, 0, 254).astype(np.uint8)


def land_mask(cls, water, hole=LAND_HOLE):
    """Inside polygons of the vector without the classes found at the water sample points.
    A small gap without a polygon (white hatching, a lake) inside the land is land."""
    wet = {int(cls[y, x]) for x, y in water}
    off = (cls == 255) | np.isin(cls, list(wet))
    n, cc, st, _ = cv2.connectedComponentsWithStats(off.astype(np.uint8), connectivity=4)
    small = np.nonzero(st[:, cv2.CC_STAT_AREA] < hole * off.size)[0]
    return ~(off & ~np.isin(cc, small[small > 0]))


def sea_land(im, region, water, de=WATER_DE):
    """Land from the country outline instead of the vector classes: a hatching may quantise to
    the sea colour, and white glaciers have no polygon at all. Water is what is connected to a
    sample point through pixels of the sample colour."""
    lab = vec.to_lab(vec.clean(im))
    wet = np.zeros(region.shape, bool)
    for x, y in water:
        m = ((np.linalg.norm(lab - lab[y, x], axis=2) < de) & (region > 0)).astype(np.uint8)
        n, cc = cv2.connectedComponents(m, connectivity=4)
        if cc[y, x]: wet |= cc == cc[y, x]
    return (region > 0) & ~wet


def islands(im, land, points, sea, r=ISLAND_R, de=WATER_DE):
    """Land the country outline misses (a small island off by the georeference error): the
    pixels around a seed that is off land, up to the sea colour, when they end within r px."""
    lab = vec.to_lab(vec.clean(im))
    out = np.zeros(land.shape, bool)
    for x, y in points:
        if land[y, x]: continue
        y0, x0 = max(0, y - r), max(0, x - r)
        win = lab[y0:y + r + 1, x0:x + r + 1]
        dry = (np.linalg.norm(win - lab[sea[1], sea[0]], axis=2) >= de).astype(np.uint8)
        n, cc = cv2.connectedComponents(dry, connectivity=4)
        part = cc == cc[y - y0, x - x0]
        edge = part[0].any() or part[-1].any() or part[:, 0].any() or part[:, -1].any()
        if cc[y - y0, x - x0] and not edge:                # an island ends inside the window; a neighbour country does not
            out[y0:y + r + 1, x0:x + r + 1] |= part
    return out


def band_mask(im, band):
    """A thick line symbol of one ink (the state border): the thin parts of the ink that form a
    long piece. Areas of a close colour are wider than 2 r or short, and stay."""
    m = ink_mask(im, band).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * band.get('r', 6) + 1,) * 2)
    thin = ((m > 0) & ~(cv2.morphologyEx(m, cv2.MORPH_OPEN, k) > 0)).astype(np.uint8)
    n, cc, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(thin, np.ones((5, 5), np.uint8)), connectivity=8)
    long = np.nonzero(np.maximum(st[:, 2], st[:, 3]) >= band.get('span', 0.15) * im.shape[1])[0]
    return (thin > 0) & np.isin(cc, long[long > 0])


def snap(seeds, lab, ref, r, de=SNAP_DE):
    """Move every seed whose key has a reference colour to the nearest pixel of that colour
    within r px: a seed placed by eye next to a narrow area may miss it by a few pixels."""
    out = []
    for k, x, y in seeds:
        if k in ref:
            y0, x0 = max(0, y - r), max(0, x - r)
            win = np.linalg.norm(lab[y0:y + r + 1, x0:x + r + 1] - ref[k], axis=2) < de
            if win.any() and not win[y - y0, x - x0]:
                ys, xs = np.nonzero(win)
                i = int(np.argmin((ys + y0 - y) ** 2 + (xs + x0 - x) ** 2))
                x, y = int(xs[i] + x0), int(ys[i] + y0)
        out.append([k, x, y])
    return out


def geodesic(relief, grow, markers, step=GEO_STEP):
    """Every pixel of `grow` takes the marker nearest along a path inside `grow`; a step costs
    1 + (relief / RELIEF_UNIT)^2, so crossing an edge costs as much as a long walk. A sum and not
    the highest step (watershed): a cheap thin corridor can not carry a unit across the sheet."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    r = relief[::step, ::step].astype(np.float64); g = grow[::step, ::step]
    mk = cv2.dilate(markers.astype(np.uint16), np.ones((step, step), np.uint8))[::step, ::step].astype(np.int32)
    mk[~g] = 0
    idx = np.full(g.shape, -1, np.int64); idx[g] = np.arange(g.sum())
    a, b, w = [], [], []
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        h, wd = g.shape
        ys, ye = 0, h - dy
        xs, xe = max(0, -dx), wd - max(0, dx)
        i0 = idx[ys:ye, xs:xe]; i1 = idx[ys + dy:ye + dy, xs + dx:xe + dx]
        ok = (i0 >= 0) & (i1 >= 0)
        cost = (1 + (np.maximum(r[ys:ye, xs:xe], r[ys + dy:ye + dy, xs + dx:xe + dx]) / RELIEF_UNIT) ** 2) * np.hypot(dy, dx)
        a.append(i0[ok]); b.append(i1[ok]); w.append(cost[ok])
    n = int(g.sum())
    G = coo_matrix((np.concatenate(w), (np.concatenate(a), np.concatenate(b))), shape=(n, n)).tocsr()
    src = idx[mk > 0]
    lab_of = dict(zip(src.tolist(), mk[mk > 0].tolist()))
    small = np.zeros(g.shape, np.int32)
    if len(src):
        dist, _, sources = dijkstra(G, directed=False, indices=np.unique(src), min_only=True, return_predecessors=True)
        got = np.array([lab_of.get(int(s), 0) if s >= 0 else 0 for s in sources])
        got[~np.isfinite(dist)] = 0
        small[g] = got
    out = cv2.resize(small.astype(np.float32), (grow.shape[1], grow.shape[0]), interpolation=cv2.INTER_NEAREST).astype(np.int32)
    out[~grow] = 0
    hole = grow & (out == 0) & cv2.dilate((out > 0).astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    if hole.any():                                     # pixels of grow lost by the coarse grid
        i = ndi.distance_transform_edt(out == 0, return_distances=False, return_indices=True)
        out[hole] = out[i[0], i[1]][hole]
    return out


def grow_units(im, doc, seeds, water, use_classes=True, relief=None, band=None, region=None):
    """Seeds [[key, x, y]] -> (unit image: -1 off land, 0 no unit, n = keys[n - 1]; keys).
    Units grow over land only; a land part that holds no seed keeps no unit. Units do not grow
    along the band symbol (a unit of its colour would run around the country): the land under
    and next to the band takes the nearest unit afterwards."""
    cls = raster(doc)
    land = land_mask(cls, water) if region is None else sea_land(im, region, water)
    if region is not None and water:
        land |= islands(im, land, [(x, y) for k, x, y in seeds], water[0])
    zone = np.zeros(land.shape, bool)
    if band:
        z = band.get('zone', 14)                            # covers the dash-dot line drawn inside the band
        zone = cv2.dilate(band_mask(im, band).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * z + 1,) * 2)) > 0
    grow = land & ~zone
    keys = list(dict.fromkeys(k for k, _, _ in seeds))
    markers = np.zeros(cls.shape, np.int16)
    for k, x, y in seeds:
        cv2.circle(markers, (int(x), int(y)), SEED_R, keys.index(k) + 1, -1)
    markers[~grow] = 0
    out = geodesic(elevation(im, cls if use_classes else None, **(relief or {})), grow, markers)
    if zone.any():
        idx = ndi.distance_transform_edt(out == 0, return_distances=False, return_indices=True)
        near = out[idx[0], idx[1]]
        fill = land & zone
        out[fill] = near[fill]
    out[~land] = -1
    return out, keys


def paint_areas(units, keys, areas):
    """Outlines traced by hand ([{'key', 'xy'}]) override the grown units on land: a variant
    told apart by hatching only has no colour edge for the growth to stop at."""
    keys = list(keys)
    for a in areas:
        if a['key'] not in keys: keys.append(a['key'])
        m = np.zeros(units.shape, np.uint8)
        cv2.fillPoly(m, [np.array(a['xy'], np.int32).reshape(-1, 2)], 1)
        units[(m > 0) & (units >= 0)] = keys.index(a['key']) + 1
    return units, keys


def colour_seeds(doc, by_class, seeds, max_de=8.0, minarea=150, width=6):
    """Seeds for the vector polygons whose class carries a single legend item close in colour
    and holds no hand seed: the colour names the unit there. Variants told apart by hatching
    never get one."""
    out = []
    for ci, inside, rings in doc['f']:
        its = by_class.get(ci, [])
        if not inside or len(its) != 1 or its[0]['de'] > max_de or 'variant_of' in its[0]: continue
        r0 = np.array(rings[0]).reshape(-1, 2)
        x0, y0 = r0.min(0); x1, y1 = r0.max(0) + 1
        m = np.zeros((y1 - y0 + 2, x1 - x0 + 2), np.uint8)
        cv2.fillPoly(m, [np.array(r).reshape(-1, 2) - [x0 - 1, y0 - 1] for r in rings], 1)
        if m.sum() < minarea: continue
        if any(x0 <= x < x1 and y0 <= y < y1 and m[int(y) - y0 + 1, int(x) - x0 + 1] for _, x, y in seeds): continue
        dt = cv2.distanceTransform(m, cv2.DIST_L2, 3)
        if dt.max() < width: continue                      # a band: the state border shares the ink
        y, x = np.unravel_index(dt.argmax(), dt.shape)
        out.append([its[0]['key'], int(x + x0 - 1), int(y + y0 - 1)])
    return out


def unit_polygons(units, n, eps=1.2, minarea=40):
    """Unit image -> [[unit index, 1, rings]] in sheet pixels."""
    feats = []
    k3 = np.ones((3, 3), np.uint8)
    for u in range(1, n + 1):
        m = (units == u).astype(np.uint8)
        if not m.any(): continue
        cs, hier = cv2.findContours(cv2.dilate(m, k3), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if hier is None: continue
        hier = hier[0]
        for i, c in enumerate(cs):
            if hier[i][3] != -1 or cv2.contourArea(c) < minarea: continue
            rings = [cv2.approxPolyDP(c, eps, True)[:, 0]]
            h = hier[i][2]
            while h != -1:
                if cv2.contourArea(cs[h]) >= minarea: rings.append(cv2.approxPolyDP(cs[h], eps, True)[:, 0])
                h = hier[h][0]
            rings = [r for r in rings if len(r) >= 3]
            if rings: feats.append([u - 1, 1, [r.ravel().tolist() for r in rings]])
    return feats


def ink_mask(im, ink):
    """Pixels of one printing ink inside the ink box, minus the excluded boxes."""
    m = np.linalg.norm(vec.to_lab(im) - hex2lab(ink['rgb']), axis=2) < ink.get('de', 18)
    keep = np.zeros(m.shape, bool)
    x0, y0, x1, y1 = ink.get('box', [0, 0, im.shape[1], im.shape[0]])
    keep[y0:y1, x0:x1] = True
    for x0, y0, x1, y1 in ink.get('exclude', []): keep[y0:y1, x0:x1] = False
    return m & keep


def thin(m):
    """Zhang-Suen thinning of a bool mask."""
    s = np.pad(m.astype(np.uint8), 1)
    while True:
        changed = False
        for step in (0, 1):
            p2, p3, p4, p5 = s[:-2, 1:-1], s[:-2, 2:], s[1:-1, 2:], s[2:, 2:]
            p6, p7, p8, p9 = s[2:, 1:-1], s[2:, :-2], s[1:-1, :-2], s[:-2, :-2]
            nb = [p2, p3, p4, p5, p6, p7, p8, p9]
            b = sum(nb)
            a = sum(((nb[i] == 0) & (nb[(i + 1) % 8] == 1)).astype(np.uint8) for i in range(8))
            c = (p2 * p4 * p6 == 0) if step == 0 else (p2 * p4 * p8 == 0)
            d = (p4 * p6 * p8 == 0) if step == 0 else (p2 * p6 * p8 == 0)
            kill = (s[1:-1, 1:-1] == 1) & (b >= 2) & (b <= 6) & (a == 1) & c & d
            if kill.any():
                s[1:-1, 1:-1][kill] = 0; changed = True
        if not changed: return s[1:-1, 1:-1].astype(bool)


def trace(skel):
    """Skeleton -> polylines [[x, y, ...]], walked from the line ends; a loop starts anywhere."""
    pts = set(zip(*np.nonzero(skel)))
    nbr = lambda p: [(p[0] + dy, p[1] + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy or dx) and (p[0] + dy, p[1] + dx) in pts]
    out = []
    while pts:
        ends = [p for p in pts if len(nbr(p)) == 1]
        p = min(ends) if ends else min(pts)
        path = [p]; pts.discard(p)
        while True:
            nx = nbr(p)
            if not nx: break
            p = min(nx, key=lambda q: abs(q[0] - path[-1][0]) + abs(q[1] - path[-1][1]))
            path.append(p); pts.discard(p)
        if len(path) >= 2:
            a = cv2.approxPolyDP(np.array([[x, y] for y, x in path], np.int32).reshape(-1, 1, 2), 1.0, False)[:, 0]
            out.append(a.ravel().tolist())
    return out


def ink_features(im, ink):
    """One ink -> (points [[x, y]], lines [[x, y, ...]]). Dashes closer than `join` px are joined
    first: a joined piece shorter than `point` px is a point symbol, a longer one is thinned to a
    centre line. Deciding before the join turned every dash of a line into a point."""
    m = ink_mask(im, ink).astype(np.uint8)
    n, cc, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    small = np.nonzero(np.maximum(st[:, 2], st[:, 3]) < ink.get('min', INK_MIN))[0]
    m[np.isin(cc, small[small > 0])] = 0
    j = ink.get('join', INK_JOIN)
    joined = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * j + 1, 2 * j + 1)))
    size = ink.get('point', INK_POINT)
    pts, lines = [], []
    n2, cc2, st2, cen = cv2.connectedComponentsWithStats(joined, connectivity=8)
    for i in range(1, n2):
        x, y, w, h = st2[i, :4]
        if max(w, h) < size:
            if ink.get('as') != 'lines': pts.append([int(round(cen[i][0])), int(round(cen[i][1]))])
            continue
        if ink.get('as') == 'points': continue
        for l in trace(thin(cc2[y:y + h, x:x + w] == i)):
            l = np.array(l).reshape(-1, 2) + [x, y]
            if np.ptp(l, 0).max() >= size: lines.append(l.ravel().tolist())
    return pts, lines


# ---- page text ------------------------------------------------------------------------------

_TAG = re.compile(r'<[^>]+>')


def plain(s):
    return re.sub(r'\s+', ' ', html.unescape(_TAG.sub('', s))).strip()


def emphasised(s):
    """Names set in italics (<em>) inside a piece of page HTML."""
    out = []
    for e in re.findall(r'<em>(.*?)</em>', s, re.S):
        for w in re.split(r'[,;:]|\sи\s', plain(e)):
            w = re.sub(r'^(в|и|об\.)\s+', '', w.strip(' .')).strip(' .')
            w = re.sub(r'\s+в$', '', w)
            if len(w) >= 3 and not re.match(r'^(\d+|[абвг]\))', w): out.append(w)
    return out


_VARIANT = re.compile(r'(?:^|(?<=[\s;:>]))([абвг])\)\s*')


def page_units(page, start, stop, fixes=()):
    """Units of a page legend written as text between `start` and `stop`: <h4> type, <b> subtype,
    a paragraph of species shared by the subtype, units 'N. text: а) ...; б) ...'. `fixes` are
    [wrong, right] pairs for typos of the source page, kept in the marks file.
    -> {key: {'type', 'subtype', 'shared', 'text', 'italic'}} for N and every variant Nа."""
    a = page.find(start)
    body = re.sub(r'\s+', ' ', page[a:page.find(stop, a)])
    for wrong, right in fixes:
        if wrong not in body: raise ValueError(f'fix not applicable: {wrong}')
        body = body.replace(wrong, right)
    typ = sub = shared = ''
    units, cur = [], None
    for tag, h in re.findall(r'<(h4|p)[^>]*>(.*?)</\1>', body):
        t = plain(h)
        if not t: continue
        num = re.match(r'^(г?\d{1,2})\.\s*', t)
        if tag == 'h4':
            typ, sub, shared, cur = t.rstrip(' .'), '', '', None
        elif re.fullmatch(r'<b>.*</b>', h.strip()) and not num:
            sub, shared, cur = re.sub(r'\s*\d\)$', '', t).strip(), '', None
        elif num:
            cur = [num.group(1), h, typ, sub, shared]; units.append(cur)
        elif cur is not None and re.match(r'^[абвг]\)', t):
            cur[1] += ' ' + h
        elif not t.startswith('('):
            shared, cur = t, None
    out = {}
    for key, h, typ_, sub_, shared_ in units:
        h = re.sub(r'^\s*(<em>)?\s*г?\d{1,2}\.\s*(</em>)?\s*', '', h)
        pieces = _VARIANT.split(h)
        base = {'type': typ_, 'subtype': sub_, 'shared': shared_.rstrip(' :')}
        main = plain(pieces[0]).strip(' :;')
        out[key] = {**base, 'text': main, 'italic': emphasised(pieces[0])}
        for i in range(1, len(pieces) - 1, 2):
            out[key + pieces[i]] = {**base, 'text': main + ': ' + plain(pieces[i + 1]).strip(' ;'),
                                    'italic': out[key]['italic'] + emphasised(pieces[i + 1])}
    return out
