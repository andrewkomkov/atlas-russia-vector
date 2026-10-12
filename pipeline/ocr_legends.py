"""Recognise legend text at a larger scale: Vision shrinks a whole sheet and loses small
text, so every swatch column (legend.regions) is cut out, enlarged and read on its own.
Writes data/ocr_legend/<id>.json, lines in sheet pixels. Needs data/ocr_bin, macOS only.
usage: ocr_legends.py [--only ID_PREFIX] [--jobs N] [--force]"""
import os, sys, json, argparse, subprocess, tempfile
from concurrent.futures import ThreadPoolExecutor
import cv2
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import catalog, legend

DATA = os.path.join(ROOT, 'data'); SITE = os.path.join(ROOT, 'site', 'public', 'data')
OUT = os.path.join(DATA, 'ocr_legend'); OCR_BIN = os.path.join(DATA, 'ocr_bin')
SMALL_SWATCH = 22  # sheet pixels; a legend with lower swatches has small text: only such legends are read here
SCALE = 2          # enlargement of a legend piece before recognition
PIECE_H = 800      # sheet pixels; taller regions are cut into pieces
OVERLAP = 100      # sheet pixels shared by neighbouring pieces, more than a text line
FORCE = False

def pieces(regions):
    """Cut tall regions into overlapping pieces -> [(x0, y0, x1, y1)]."""
    out = []
    for x0, y0, x1, y1 in regions:
        if x1 - x0 < 20 or y1 - y0 < 20: continue
        y = y0
        while True:
            out.append((x0, y, x1, min(y1, y + PIECE_H)))
            if y + PIECE_H >= y1: break
            y += PIECE_H - OVERLAP
    return out

def overlap(a, b):
    """The same text read twice: the lines share most of the height and of the width."""
    oy = min(a['y'] + a['h'], b['y'] + b['h']) - max(a['y'], b['y'])
    ox = min(a['x'] + a['w'], b['x'] + b['w']) - max(a['x'], b['x'])
    return oy > 0.5 * min(a['h'], b['h']) and ox > 0.5 * min(a['w'], b['w'])

def merge(lines):
    """Drop repeats from overlapping pieces; the wider reading wins: the other one is cut by an edge."""
    kept = []
    for l in sorted(lines, key=lambda l: (-l['w'], -l['c'])):
        if not any(overlap(l, k) for k in kept): kept.append(l)
    return sorted(kept, key=lambda l: (l['y'], l['x']))

def read(im, boxes):
    """Recognise every box of the sheet -> lines in sheet pixels."""
    lines = []
    with tempfile.TemporaryDirectory() as tmp:
        names = []
        for i, (x0, y0, x1, y1) in enumerate(boxes):
            names.append(os.path.join(tmp, f'{i}.png'))
            big = cv2.resize(im[y0:y1, x0:x1], None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_CUBIC)
            cv2.imwrite(names[-1], big)
        subprocess.run([OCR_BIN] + names, env={**os.environ, 'OCR_OUT': tmp}, check=True, capture_output=True)
        for i, (x0, y0, _, _) in enumerate(boxes):
            fn = os.path.join(tmp, f'{i}.json')
            if not os.path.exists(fn): continue
            for l in json.load(open(fn))['lines']:
                lines.append({'t': l['t'], 'c': l['c'], 'x': x0 + l['x'] // SCALE, 'y': y0 + l['y'] // SCALE,
                              'w': l['w'] // SCALE, 'h': l['h'] // SCALE})
    return merge(lines)

def one(m):
    dst = os.path.join(OUT, m['id'] + '.json')
    vec = os.path.join(SITE, 'v', m['id'] + '.json')
    if (os.path.exists(dst) and not FORCE) or not os.path.exists(vec): return 0
    doc = json.load(open(vec))
    boxes = pieces(legend.regions(doc))
    if not boxes: return 0
    low = sorted(s['h'] for s in legend.swatches(doc))
    if low[len(low) // 2] >= SMALL_SWATCH: return 0        # large text: the whole-sheet reading is good
    im = cv2.imread(os.path.join(DATA, 'img', m['file']))
    if im is None: return 0
    json.dump({'lines': read(im, boxes)}, open(dst, 'w'), ensure_ascii=False, separators=(',', ':'))
    return 1

def main():
    global FORCE
    ap = argparse.ArgumentParser(); ap.add_argument('--only', default=''); ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args(); FORCE = a.force
    os.makedirs(OUT, exist_ok=True)
    todo = [m for m in catalog.parse(os.path.join(DATA, 'pages')) if m['id'].startswith(a.only)]
    done = 0
    with ThreadPoolExecutor(a.jobs) as pool:
        for i, n in enumerate(pool.map(one, todo), 1):
            done += n
            if i % 200 == 0: print(i, '/', len(todo), flush=True)
    print('legends read:', done, 'of', len(todo), 'maps')

if __name__ == '__main__':
    main()
