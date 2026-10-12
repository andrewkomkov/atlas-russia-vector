"""Build site/public/data/l/<id>.json (legend labels per colour class) from the vectors
and the cached OCR, and write the number of labelled classes into the catalog (field lg)."""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import catalog, legend
DATA = os.path.join(ROOT, 'data'); OUT = os.path.join(ROOT, 'site', 'public', 'data')

SMALL_SWATCH = 22   # sheet pixels; lower swatches mean small text, which only the enlarged reading gets right
MUCH_MORE = 1.25    # large text reads cleaner on the whole sheet: the enlarged reading must find this much more

def count(r):
    return len(r['labels']) + len(r.get('alts', {}))

def best(doc, whole, fine):
    """Decode the legend from the reading of the whole sheet or from the enlarged one."""
    r = legend.decode(doc, whole)
    if not fine: return r
    r2 = legend.decode(doc, fine)
    heights = sorted(s['h'] for s in legend.swatches(doc))
    small = bool(heights) and heights[len(heights) // 2] < SMALL_SWATCH
    return r2 if small or count(r2) >= max(count(r) + 2, MUCH_MORE * count(r)) else r

def main():
    os.makedirs(os.path.join(OUT, 'l'), exist_ok=True)
    files = {m['id']: m['file'] for m in catalog.parse(os.path.join(DATA, 'pages'))}
    cat = json.load(open(os.path.join(OUT, 'catalog.json')))
    n = tot = 0
    for m in cat['maps']:
        m.pop('lg', None)
        v = os.path.join(OUT, 'v', m['id'] + '.json')
        o = os.path.join(DATA, 'ocr', os.path.splitext(files[m['id']])[0] + '.json')
        dst = os.path.join(OUT, 'l', m['id'] + '.json')
        if os.path.exists(dst): os.remove(dst)
        if m.get('nv') or not (os.path.exists(v) and os.path.exists(o)): continue
        fine = os.path.join(DATA, 'ocr_legend', m['id'] + '.json')      # legend regions read at a larger scale
        r = best(json.load(open(v)), json.load(open(o)), json.load(open(fine)) if os.path.exists(fine) else None)
        found = count(r)
        if found < 2: continue                     # a single labelled rectangle is rarely a legend
        json.dump(r, open(dst, 'w'), ensure_ascii=False, separators=(',', ':'))
        m['lg'] = found; n += 1; tot += m['lg']
    json.dump(cat, open(os.path.join(OUT, 'catalog.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    for t in (1, 2, 3, 4):
        ms = [m for m in cat['maps'] if m['tom'] == t]
        print(f'том {t}: с подписями {sum("lg" in m for m in ms)} из {len(ms)}')
    print('всего карт с подписями', n, '; подписанных классов', tot)

if __name__ == '__main__':
    main()
