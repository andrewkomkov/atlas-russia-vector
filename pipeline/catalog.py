"""Parse cached atlas pages into the list of maps (one entry per zoomable image)."""
import os, re, glob, html, json, sys

VOLUMES = {1: 'Общая характеристика территории', 2: 'Природа. Экология', 3: 'Население. Экономика', 4: 'История. Культура'}

def _txt(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s))).strip()

def parse(pages_dir):
    maps = []
    for fn in sorted(glob.glob(os.path.join(pages_dir, 'tom*__*.html'))):
        m = re.match(r'tom(\d)__(.+)\.html$', os.path.basename(fn))
        tom, slug = int(m.group(1)), m.group(2)
        h = open(fn, encoding='utf-8', errors='replace').read()
        zoom = re.findall(r'data-zoom-image="([^"]+)"', h)
        if not zoom: continue
        sec = re.search(r'<h2 class="pb-3 mb-4 font-italic border-bottom">(.*?)</h2>', h, re.S)
        tit = re.search(r'<h2 class="blog-post-title">(.*?)</h2>', h, re.S)
        section = _txt(sec.group(1)) if sec else ''
        title = _txt(tit.group(1)) if tit else ''
        if not title:
            t = re.search(r'<title>(.*?)</title>', h, re.S)
            title = _txt(t.group(1)).split(', Том')[0] if t else slug
        num = re.match(r'\d+', slug)
        # small preview shown on the page: used when the large image is gone from the source (404)
        small = dict((z, a) for a, z in re.findall(r'src="(/static/maps[^"]+)"\s+data-zoom-image="([^"]+)"', h))
        img_dir = os.path.join(os.path.dirname(os.path.abspath(pages_dir)), 'img')
        seen = []
        for z in zoom:
            if z not in seen: seen.append(z)
        for i, z in enumerate(seen, 1):
            name = lambda u: u.replace('/static/', '', 1).replace('/', '__')
            e = {'id': f'{tom}-{slug}-{i}', 'tom': tom, 'slug': slug, 'n': i, 'of': len(seen),
                 'section': section or VOLUMES[tom], 'title': title,
                 'page': f'https://nationalatlas.ru/tom{tom}/{slug}.html', 'src': 'https://nationalatlas.ru' + z,
                 'file': name(z), 'order': int(num.group()) if num else 9999}
            alt = small.get(z)
            if alt:
                e['alt'] = 'https://nationalatlas.ru' + alt; e['altfile'] = name(alt)
                if not os.path.exists(os.path.join(img_dir, e['file'])) and os.path.exists(os.path.join(img_dir, e['altfile'])):
                    e['src'], e['file'], e['small'] = e['alt'], e['altfile'], True
            maps.append(e)
    maps.sort(key=lambda m: (m['tom'], m['order'], m['slug'], m['n']))
    return maps

if __name__ == '__main__':
    ms = parse(sys.argv[1])
    print(len(ms), 'maps;', len({m['file'] for m in ms}), 'unique files')
    for t in VOLUMES: print('том', t, sum(m['tom'] == t for m in ms))
    print(json.dumps(ms[700], ensure_ascii=False))
