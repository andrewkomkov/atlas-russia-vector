"""Build site/public/data/a/<id>.json from marks/<id>.json (specs/007-fauna-sheets) and write
the field `mk` into the catalog. Runs after build_legends.py, which rewrites the catalog.
usage: build_marks.py [--only ID_PREFIX]"""
import os, sys, json, argparse
import numpy as np, cv2
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import catalog, georef, legend, marks

DATA = os.path.join(ROOT, 'data'); OUT = os.path.join(ROOT, 'site', 'public', 'data')
MARKS = os.path.join(ROOT, 'marks')
ITEM_FIELDS = ('key', 'label', 'text', 'group', 'kind', 'variant_of', 'de')


def legend_part(im, doc, lg):
    by_class, lost = marks.legend_table(im, doc, lg['items'])
    classes = {str(ci): [{k: it[k] for k in ITEM_FIELDS if k in it} for it in its] for ci, its in sorted(by_class.items())}
    return {'title': lg.get('title', ''), 'note': lg.get('note', ''), 'classes': classes,
            'lost': [it['key'] for it in lost]}


def unit_info(mk, keys, files_dir):
    """Text of every unit key: from the legend items of the marks file or from the page HTML."""
    u = mk['units']
    info = {}
    if 'page' in u:
        page = open(os.path.join(files_dir, u['page']['file']), encoding='utf-8').read()
        info = marks.page_units(page, u['page']['start'], u['page']['stop'], u['page'].get('fixes', ()))
    for it in mk.get('legend', {}).get('items', []):
        info.setdefault(it['key'], {k: it[k] for k in ('label', 'text', 'group') if k in it})
    for k, v in u.get('text', {}).items(): info[k] = v
    out = {}
    for k in keys:
        parts = [p.strip() for p in k.split(',')]       # '13а,б': one outline holds two variants
        if len(parts) > 1 and parts[0][-1:].isalpha():
            parts = [parts[0]] + [parts[0][:-1] + p for p in parts[1:]]
        got = [info[p] if p in info else {**info[p[:-1]], 'variant': 'нет на странице'}
               for p in parts if p in info or (p[-1:].isalpha() and p[:-1] in info)]
        if got: out[k] = got[0] if len(got) == 1 else {'parts': parts, 'items': got}
    return out


def units_part(im, doc, mk, files_dir):
    u = mk['units']
    seeds = list(u['seeds'])
    auto = []
    if u.get('by_colour'):
        by_class, _ = marks.legend_table(im, doc, mk['legend']['items'])
        auto = marks.colour_seeds(doc, by_class, seeds)
        if isinstance(u['by_colour'], list): auto = [s for s in auto if s[0] in u['by_colour']]
    if u.get('snap'):
        clean = marks.vec.clean(im)
        lab = marks.vec.to_lab(clean)
        ref = {it['key']: marks.swatch_colour(clean, it['swatch']) for it in mk['legend']['items'] if 'swatch' in it}
        seeds = marks.snap(seeds, lab, ref, u['snap'])
    region = None
    if u.get('outline'):                                  # land from the country outline, see marks.sea_land
        geo = json.load(open(os.path.join(DATA, 'meta', mk['id'] + '.json')))['geo']
        region = georef.region_mask(geo, im.shape, os.path.join(DATA, 'ne', 'countries50.geojson'), grow=u['outline'])
    img, keys = marks.grow_units(im, doc, seeds + auto, u.get('water', []), u.get('classes', True), u.get('relief'),
                                 u.get('band'), region)
    img, keys = marks.paint_areas(img, keys, u.get('areas', []))
    feats = marks.unit_polygons(img, len(keys))
    land = (img >= 0).sum()
    share = {k: round(float((img == i + 1).sum() / land), 5) for i, k in enumerate(keys)}
    info = unit_info(mk, keys, files_dir)
    return {'keys': keys, 'info': info, 'missing': [k for k in keys if k not in info],
            'share': share, 'none': round(float((img == 0).sum() / land), 5), 'seeds': len(seeds),
            'colour_seeds': len(auto), 'f': feats}


def one(mk, meta, im, files_dir):
    doc = json.load(open(os.path.join(OUT, 'v', mk['id'] + '.json')))
    out = {'id': mk['id'], 'made': mk.get('made', ''), 'source': mk.get('source', ''), 'w': doc['w'], 'h': doc['h'],
           'v': legend.layer_print(doc)}
    if 'legend' in mk: out['legend'] = legend_part(im, doc, mk['legend'])
    if 'units' in mk: out['units'] = units_part(im, doc, mk, files_dir)
    pts, lines = [], []
    for ink in mk.get('inks', []):
        p, l = marks.ink_features(im, ink)
        pts += [{'kind': ink['kind'], 'x': x, 'y': y} for x, y in p]
        lines += [{'kind': ink['kind'], 'xy': xy} for xy in l]
    pts += [{k: v for k, v in p.items() if k != 'xy'} | {'x': p['xy'][0], 'y': p['xy'][1]} for p in mk.get('points', [])]
    lines += mk.get('lines', [])
    if pts: out['points'] = pts
    if lines: out['lines'] = lines
    for k in ('species', 'kinds', 'italic'):
        if k in mk: out[k] = mk[k]
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--only', default='')
    a = ap.parse_args()
    os.makedirs(os.path.join(OUT, 'a'), exist_ok=True)
    files = {m['id']: m['file'] for m in catalog.parse(os.path.join(DATA, 'pages'))}
    cat = json.load(open(os.path.join(OUT, 'catalog.json')))
    built = {}
    for fn in sorted(os.listdir(MARKS)):
        if not fn.endswith('.json') or not fn.startswith(a.only): continue
        mk = marks.load(os.path.join(MARKS, fn))
        im = cv2.imread(os.path.join(DATA, 'img', files[mk['id']]))
        res = one(mk, None, im, os.path.join(DATA, 'pages'))
        json.dump(res, open(os.path.join(OUT, 'a', mk['id'] + '.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
        built[mk['id']] = res
        lg, un = res.get('legend', {}), res.get('units', {})
        print(mk['id'], '| legend classes', len(lg.get('classes', {})), 'lost', lg.get('lost', []),
              '| units', len(un.get('keys', [])), 'no text', un.get('missing', []), 'no unit', un.get('none', ''),
              '| points', len(res.get('points', [])), 'lines', len(res.get('lines', [])))
    names = {f[:-5] for f in os.listdir(os.path.join(OUT, 'a')) if f.endswith('.json')}
    for m in cat['maps']:
        m.pop('mk', None)
        if m['id'] in names: m['mk'] = 1
    json.dump(cat, open(os.path.join(OUT, 'catalog.json'), 'w'), ensure_ascii=False, separators=(',', ':'))


if __name__ == '__main__':
    main()
