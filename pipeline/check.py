"""Completeness check (SC-001, SC-002): every catalogued map has an original,
a vector file, a thumbnail and a display copy; exits 1 otherwise."""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import catalog
DATA = os.path.join(ROOT, 'data'); OUT = os.path.join(ROOT, 'site', 'public', 'data')
maps = catalog.parse(os.path.join(DATA, 'pages'))
cat = json.load(open(os.path.join(OUT, 'catalog.json')))['maps']
ids = {m['id'] for m in cat}
r2 = set(open(os.path.join(DATA, 'r2_done.txt')).read().split()) if os.path.exists(os.path.join(DATA, 'r2_done.txt')) else set()
bad = {'нет оригинала': [], 'нет в каталоге': [], 'нет вектора': [], 'нет миниатюры': [], 'нет копии для листа': [], 'оригинал не в R2': []}
for m in maps:
    i = m['id']
    if not os.path.exists(os.path.join(DATA, 'img', m['file'])): bad['нет оригинала'].append(i)
    if i not in ids: bad['нет в каталоге'].append(i)
    if not os.path.exists(os.path.join(OUT, 'v', i + '.json')): bad['нет вектора'].append(i)
    if not os.path.exists(os.path.join(OUT, 't', i + '.webp')): bad['нет миниатюры'].append(i)
    if not os.path.exists(os.path.join(OUT, 'd', i + '.webp')): bad['нет копии для листа'].append(i)
    if i + os.path.splitext(m['file'])[1].lower() not in r2: bad['оригинал не в R2'].append(i)
print('карт найдено обходом:', len(maps), '| в каталоге:', len(cat), '| с привязкой:', sum('geo' in m for m in cat))
for k, v in bad.items(): print(f'{k}: {len(v)}', v[:8] if v else '')
sys.exit(1 if any(bad.values()) else 0)
