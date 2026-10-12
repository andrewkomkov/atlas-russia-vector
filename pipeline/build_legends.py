"""Build site/public/data/l/<id>.json (legend labels per colour class) from the vectors
and the cached OCR, and write the number of labelled classes into the catalog (field lg)."""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import catalog, legend
DATA = os.path.join(ROOT, 'data'); OUT = os.path.join(ROOT, 'site', 'public', 'data')

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
        r = legend.decode(json.load(open(v)), json.load(open(o)))
        if len(r['labels']) < 2: continue          # a single labelled rectangle is rarely a legend
        json.dump(r, open(dst, 'w'), ensure_ascii=False, separators=(',', ':'))
        m['lg'] = len(r['labels']); n += 1; tot += m['lg']
    json.dump(cat, open(os.path.join(OUT, 'catalog.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    for t in (1, 2, 3, 4):
        ms = [m for m in cat['maps'] if m['tom'] == t]
        print(f'том {t}: с подписями {sum("lg" in m for m in ms)} из {len(ms)}')
    print('всего карт с подписями', n, '; подписанных классов', tot)

if __name__ == '__main__':
    main()
