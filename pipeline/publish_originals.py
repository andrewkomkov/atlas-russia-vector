"""Upload untouched originals to the R2 bucket as <id>.<ext> (resumable).
usage: publish_originals.py [--jobs N]"""
import os, sys, json, subprocess, argparse, threading
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import catalog
DATA = os.path.join(ROOT, 'data'); SITE = os.path.join(ROOT, 'site')
BUCKET = 'atlas-russia-originals'
DONE = os.path.join(DATA, 'r2_done.txt')
TYPES = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif'}
lock = threading.Lock()

def put(m):
    src = os.path.join(DATA, 'img', m['file'])
    ext = os.path.splitext(m['file'])[1].lower()
    key = m['id'] + ext
    if not os.path.exists(src): return 'missing'
    r = subprocess.run(['npx', 'wrangler', 'r2', 'object', 'put', f'{BUCKET}/{key}', '--file', src, '--content-type', TYPES.get(ext, 'application/octet-stream'), '--remote'],
                       cwd=SITE, capture_output=True, text=True)
    if r.returncode != 0:
        print('FAIL', key, (r.stderr or r.stdout)[-200:], flush=True); return 'fail'
    with lock: open(DONE, 'a').write(key + '\n')
    return 'ok'

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--jobs', type=int, default=6); ap.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()
    done = set(open(DONE).read().split()) if os.path.exists(DONE) else set()
    maps = [m for m in catalog.parse(os.path.join(DATA, 'pages')) if m['id'] + os.path.splitext(m['file'])[1].lower() not in done]
    if a.limit: maps = maps[:a.limit]
    res = {}
    with ThreadPoolExecutor(a.jobs) as ex:
        for i, r in enumerate(ex.map(put, maps), 1):
            res[r] = res.get(r, 0) + 1
            if i % 100 == 0: print(i, '/', len(maps), res, flush=True)
    print('already', len(done), 'now', res)

if __name__ == '__main__':
    main()
