"""Crawl volumes 1-4 of nationalatlas.ru into data/pages/ (cached, sequential)."""
import re, sys, time, os, subprocess, urllib.parse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'pages'); BASE = 'https://nationalatlas.ru'

def get(path):
    fn = os.path.join(OUT, path.strip('/').replace('/', '__') or 'root')
    if os.path.exists(fn):
        return open(fn, encoding='utf-8', errors='replace').read()
    try:   # curl: the system Python has no CA bundle for this host
        html = subprocess.run(['curl', '-sS', '-f', '-m', '40', BASE + urllib.parse.quote(path)], capture_output=True, check=True).stdout.decode('utf-8', 'replace')
    except Exception as e:
        print('ERR', path, e, flush=True); return ''
    open(fn, 'w', encoding='utf-8').write(html); time.sleep(0.1)
    return html

def main():
    os.makedirs(OUT, exist_ok=True)
    seen, queue = set(), [f'/tom{t}/contents.html' for t in (1, 2, 3, 4)] + [f'/tom{t}/' for t in (1, 2, 3, 4)]
    while queue:
        p = queue.pop(0)
        if p in seen: continue
        seen.add(p)
        for h in re.findall(r'href="([^"#?]+)"', get(p)):
            h = urllib.parse.urljoin(p, h)
            if re.match(r'/tom[1-4]/[^/]*$', h) and (h.endswith('.html') or h.endswith('/')) and h not in seen:
                queue.append(h)
    print('pages', len(seen))

if __name__ == '__main__':
    main()
