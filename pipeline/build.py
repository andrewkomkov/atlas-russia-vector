"""Build site data: catalog.json, v/<id>.json (vectors), t/<id>.webp (thumbnails),
d/<id>.webp (display copy for the sheet view). Originals are published separately
(see publish_originals.py). Finished maps are skipped on re-run.

usage: build.py [--only ID_PREFIX] [--jobs N] [--force]
"""
import os, sys, json, argparse, time
from multiprocessing import Pool
import cv2
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import catalog, georef, vec

DATA = os.path.join(ROOT, 'data'); OUT = os.path.join(ROOT, 'site', 'public', 'data')
NE = os.path.join(DATA, 'ne', 'countries50.geojson')
MAX_BYTES = 1_400_000        # per vector file; coarser settings are tried above this

def one(m):
    meta_fn = os.path.join(DATA, 'meta', m['id'] + '.json')
    if os.path.exists(meta_fn) and not FORCE:
        return json.load(open(meta_fn))
    src = os.path.join(DATA, 'img', m['file'])
    im = cv2.imread(src) if os.path.exists(src) else None
    if im is None:
        return {'id': m['id'], 'missing': True}
    try:
        g = georef.fit(im, NE)
        region = georef.region_mask(g['P'], im.shape, NE) if g and g['ok'] else None
        for level in (0, 1, 2):
            doc = vec.process(im, region, level)
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
                'pal': [doc['colors'][i] for i in top], 'osize': os.path.getsize(src)}
        if g: meta['q'] = {k: g[k] for k in ('inlier', 'lift', 'inside', 'span')}
        if g and g['ok']: meta['geo'] = [round(v, 6) for v in g['P']]
    except Exception as e:                                   # keep the batch going, report at the end
        meta = {'id': m['id'], 'error': repr(e)[:200]}
        return meta
    json.dump(meta, open(meta_fn, 'w'))
    return meta

def main():
    global FORCE
    ap = argparse.ArgumentParser(); ap.add_argument('--only', default=''); ap.add_argument('--jobs', type=int, default=8); ap.add_argument('--force', action='store_true')
    a = ap.parse_args(); FORCE = a.force
    for d in ('v', 't', 'd'): os.makedirs(os.path.join(OUT, d), exist_ok=True)
    os.makedirs(os.path.join(DATA, 'meta'), exist_ok=True)
    maps = catalog.parse(os.path.join(DATA, 'pages'))
    todo = [m for m in maps if m['id'].startswith(a.only)]
    t = time.time(); metas = {}
    with Pool(a.jobs, initializer=_init, initargs=(a.force,)) as pool:
        for i, meta in enumerate(pool.imap_unordered(one, todo, chunksize=2), 1):
            metas[meta['id']] = meta
            if i % 50 == 0: print(i, '/', len(todo), round(time.time() - t), 's', flush=True)
    # catalog covers every map that has been built so far (not only this run)
    out, miss, err = [], 0, []
    for m in maps:
        fn = os.path.join(DATA, 'meta', m['id'] + '.json')
        if not os.path.exists(fn):
            miss += 1; continue
        e = dict(m)
        for k in ('order', 'file', 'alt', 'altfile'): e.pop(k, None)
        e.update(json.load(open(fn))); out.append(e)
    err = [x for x in metas.values() if 'error' in x]
    json.dump({'built': time.strftime('%Y-%m-%d'), 'volumes': catalog.VOLUMES, 'maps': out}, open(os.path.join(OUT, 'catalog.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    print('catalog', len(out), 'maps; georeferenced', sum('geo' in e for e in out), '; not built', miss, '; errors', len(err))
    for x in err[:20]: print('  ', x)

FORCE = False
def _init(force):
    global FORCE
    FORCE = force
    cv2.setNumThreads(1)

if __name__ == '__main__':
    main()
