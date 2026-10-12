"""Build site data: catalog.json, v/<id>.json (vectors), t/<id>.webp (thumbnails),
d/<id>.webp (display copy for the sheet view). Originals are published separately
(see publish_originals.py). Finished maps are skipped on re-run.

usage: build.py [--only ID_PREFIX] [--ids FILE] [--jobs N] [--force]
  --ids FILE: build only the maps whose ids are listed in the file
"""
import os, sys, json, argparse, time
from multiprocessing import Pool
import cv2
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import catalog, georef, legend, vec

DATA = os.path.join(ROOT, 'data'); OUT = os.path.join(ROOT, 'site', 'public', 'data')
NE = os.path.join(DATA, 'ne', 'countries50.geojson')
MAX_BYTES = 1_400_000        # per vector file; coarser settings are tried above this
# catalog fields the site reads; the rest of the page and build metadata stays in data/meta
CATALOG_FIELDS = ('id', 'tom', 'n', 'of', 'section', 'title', 'page', 'src', 'w', 'h', 'osize', 'geo', 'nv')
FORCE = False                # set in every worker by _init
MIN_POLYGONS = 6             # fewer polygons: a table, a chart or a line-only map
MAX_POLYGONS_UNREF = 1500    # more on a sheet without georeference: a photo, relief or an old plan

def no_vector(meta):
    """-> 'empty' | 'noise' | None: why the sheet is shown as a picture only."""
    if meta['nf'] < MIN_POLYGONS: return 'empty'
    if 'geo' not in meta and meta['nf'] > MAX_POLYGONS_UNREF: return 'noise'
    return None

def by_legend(im, region, level, doc, lab):
    """The layer with colour classes taken from the legend swatches of doc (the first pass).
    None when the legend has no more colours than the swatches have classes, when the second
    pass loses the legend (legend.keeps_legend) or turns the sheet into a picture (no_vector)."""
    pal = legend.palette(doc, lab)
    if len(pal) <= legend.swatch_classes(doc): return None
    doc2 = vec.process(im, region, level, palette=pal)
    geo = {} if region is None else {'geo': True}
    spoilt = no_vector({'nf': len(doc2['f']), **geo}) and not no_vector({'nf': len(doc['f']), **geo})
    return doc2 if legend.keeps_legend(doc, doc2) and not spoilt else None

def one(m):
    meta_fn = os.path.join(DATA, 'meta', m['id'] + '.json')
    if os.path.exists(meta_fn) and not FORCE:
        meta = json.load(open(meta_fn))
        # the vector file of a picture-only sheet is dropped; rebuild it if the rule no longer applies
        if no_vector(meta) or os.path.exists(os.path.join(OUT, 'v', m['id'] + '.json')): return meta
    src = os.path.join(DATA, 'img', m['file'])
    im = cv2.imread(src) if os.path.exists(src) else None
    if im is None:
        return {'id': m['id'], 'missing': True}
    try:
        g = georef.fit(im, NE)
        region = georef.region_mask(g['P'], im.shape, NE) if g and g['ok'] else None
        lab = None
        for level in (0, 1, 2):
            doc = vec.process(im, region, level)
            doc2 = None
            if legend.swatches(doc):
                if lab is None: lab = vec.to_lab(vec.clean(im))
                doc2 = by_legend(im, region, level, doc, lab)
            doc = doc2 or doc
            js = json.dumps(doc, separators=(',', ':'))
            if len(js) <= MAX_BYTES: break
        open(os.path.join(OUT, 'v', m['id'] + '.json'), 'w').write(js)
        h, w = im.shape[:2]
        s = 420 / w
        cv2.imwrite(os.path.join(OUT, 't', m['id'] + '.webp'), cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), [cv2.IMWRITE_WEBP_QUALITY, 72])
        s = min(1.0, 2600 / max(w, h))
        disp = im if s == 1 else cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        cv2.imwrite(os.path.join(OUT, 'd', m['id'] + '.webp'), disp, [cv2.IMWRITE_WEBP_QUALITY, 80])
        top = sorted(range(len(doc['colors'])), key=lambda i: -doc['share'][i])[:5]
        meta = {'id': m['id'], 'w': w, 'h': h, 'nf': len(doc['f']), 'level': level, 'bytes': len(js),
                'pal': [doc['colors'][i] for i in top], 'osize': os.path.getsize(src), 'legend': doc2 is not None}
        if g: meta['q'] = {k: g[k] for k in ('inlier', 'lift', 'inside', 'span')}
        if g and g['ok']: meta['geo'] = [round(v, 6) for v in g['P']]
    except Exception as e:                                   # keep the batch going, report at the end
        meta = {'id': m['id'], 'error': repr(e)[:200]}
        return meta
    json.dump(meta, open(meta_fn, 'w'))
    return meta

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--only', default=''); ap.add_argument('--ids', default='')
    ap.add_argument('--jobs', type=int, default=8); ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    ids = set(open(a.ids).read().split()) if a.ids else None
    for d in ('v', 't', 'd'): os.makedirs(os.path.join(OUT, d), exist_ok=True)
    os.makedirs(os.path.join(DATA, 'meta'), exist_ok=True)
    maps = catalog.parse(os.path.join(DATA, 'pages'))
    todo = [m for m in maps if m['id'].startswith(a.only) and (ids is None or m['id'] in ids)]
    t = time.time(); metas = {}
    with Pool(a.jobs, initializer=_init, initargs=(a.force,)) as pool:
        for i, meta in enumerate(pool.imap_unordered(one, todo, chunksize=2), 1):
            metas[meta['id']] = meta
            if i % 50 == 0: print(i, '/', len(todo), round(time.time() - t), 's', flush=True)
    # catalog covers every map that has been built so far (not only this run)
    out, miss = [], 0
    for m in maps:
        fn = os.path.join(DATA, 'meta', m['id'] + '.json')
        if not os.path.exists(fn):
            miss += 1; continue
        e = {**m, **json.load(open(fn))}
        why = no_vector(e)
        if why:
            e['nv'] = why
            v = os.path.join(OUT, 'v', m['id'] + '.json')
            if os.path.exists(v): os.remove(v)
        out.append({k: e[k] for k in CATALOG_FIELDS if k in e})
    err = [x for x in metas.values() if 'error' in x]
    json.dump({'built': time.strftime('%Y-%m-%d'), 'volumes': catalog.VOLUMES, 'maps': out}, open(os.path.join(OUT, 'catalog.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    print('catalog', len(out), 'maps; georeferenced', sum('geo' in e for e in out), '; picture only', sum('nv' in e for e in out),
          '; classes by legend', sum(bool(json.load(open(os.path.join(DATA, 'meta', e['id'] + '.json'))).get('legend')) for e in out),
          '; not built', miss, '; errors', len(err))
    for x in err[:20]: print('  ', x)

def _init(force):
    global FORCE
    FORCE = force
    cv2.setNumThreads(1)

if __name__ == '__main__':
    main()
