"""Download every zoomable image of the catalog into data/img/ (skips existing, 5 threads)."""
import os, sys, subprocess, urllib.parse
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import catalog
DATA = os.path.join(ROOT, 'data')

def get(m):
    fn = os.path.join(DATA, 'img', m['file'])
    if os.path.exists(fn) and os.path.getsize(fn) > 0: return 0
    url = 'https://nationalatlas.ru' + urllib.parse.quote(urllib.parse.urlparse(m['src']).path)
    r = subprocess.run(['curl', '-sS', '-f', '-m', '180', '-o', fn + '.part', url], capture_output=True)
    if r.returncode == 0:
        os.rename(fn + '.part', fn); return 1
    if b' 404' in r.stderr and m.get('alt'):          # large image removed from the source: keep the preview
        alt = os.path.join(DATA, 'img', m['altfile'])
        url = 'https://nationalatlas.ru' + urllib.parse.quote(urllib.parse.urlparse(m['alt']).path)
        if subprocess.run(['curl', '-sS', '-f', '-m', '180', '-o', alt, url], capture_output=True).returncode == 0: return 1
    print('FAIL', m['src'], r.stderr.decode()[:80], flush=True); return 0

def main():
    os.makedirs(os.path.join(DATA, 'img'), exist_ok=True)
    maps = catalog.parse(os.path.join(DATA, 'pages'))
    with ThreadPoolExecutor(5) as ex: n = sum(ex.map(get, maps))
    have = sum(os.path.exists(os.path.join(DATA, 'img', m['file'])) for m in maps)
    print('new', n, 'have', have, 'of', len(maps))

if __name__ == '__main__':
    main()
