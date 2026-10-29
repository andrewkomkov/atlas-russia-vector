"""Completeness check (SC-001, SC-002): every catalogued map has an original,
a thumbnail, a display copy and a vector file; a picture-only sheet (field nv)
must have no vector file. Exits 1 otherwise."""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import catalog, legend
DATA = os.path.join(ROOT, 'data'); OUT = os.path.join(ROOT, 'site', 'public', 'data')
maps = catalog.parse(os.path.join(DATA, 'pages'))
cat = json.load(open(os.path.join(OUT, 'catalog.json')))['maps']
ids = {m['id'] for m in cat}
nv = {m['id'] for m in cat if m.get('nv')}
r2 = set(open(os.path.join(DATA, 'r2_done.txt')).read().split()) if os.path.exists(os.path.join(DATA, 'r2_done.txt')) else set()
bad = {'подписи от другого слоя': [], 'нет оригинала': [], 'нет в каталоге': [], 'нет вектора': [], 'лишний вектор': [], 'нет миниатюры': [], 'нет копии для листа': [], 'оригинал не в R2': []}
for m in maps:
    i = m['id']
    if not os.path.exists(os.path.join(DATA, 'img', m['file'])): bad['нет оригинала'].append(i)
    if i not in ids: bad['нет в каталоге'].append(i)
    has_v = os.path.exists(os.path.join(OUT, 'v', i + '.json'))
    if i in nv and has_v: bad['лишний вектор'].append(i)
    if i not in nv and not has_v: bad['нет вектора'].append(i)
    if not os.path.exists(os.path.join(OUT, 't', i + '.webp')): bad['нет миниатюры'].append(i)
    if not os.path.exists(os.path.join(OUT, 'd', i + '.webp')): bad['нет копии для листа'].append(i)
    if i + os.path.splitext(m['file'])[1].lower() not in r2: bad['оригинал не в R2'].append(i)
for d in ('l', 'a'):
    folder = os.path.join(OUT, d)
    for fn in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        v = os.path.join(OUT, 'v', fn)
        if not os.path.exists(v) or json.load(open(os.path.join(folder, fn))).get('v') != legend.layer_print(json.load(open(v))):
            bad['подписи от другого слоя'].append(d + '/' + fn[:-5])
by_legend = sum(bool(json.load(open(f)).get('legend')) for f in (os.path.join(DATA, 'meta', i + '.json') for i in ids) if os.path.exists(f))
print('карт найдено обходом:', len(maps), '| в каталоге:', len(cat), '| с привязкой:', sum('geo' in m for m in cat), '| только картинка:', len(nv), '| классы по легенде:', by_legend)
for k, v in bad.items(): print(f'{k}: {len(v)}', v[:8] if v else '')
sys.exit(1 if any(bad.values()) else 0)
