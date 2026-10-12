"""Legend decoding: find legend swatches among the vector polygons, attach the text
recognised to the right of each swatch and the heading above the swatch column."""
import re
import numpy as np

def swatches(doc):
    """Rectangular polygons of a repeated size that lie outside the mapped territory."""
    k = doc['w'] / 2700.0
    cand = []
    for ci, inside, rings in doc['f']:
        if inside: continue
        r = np.array(rings[0]).reshape(-1, 2)
        x0, y0 = r.min(0); x1, y1 = r.max(0); w, h = x1 - x0, y1 - y0
        if not (18 * k <= w <= 150 * k and 10 * k <= h <= 80 * k and 0.8 <= w / h <= 4.5): continue
        x, y = r[:, 0], r[:, 1]
        area = abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))) / 2
        if area / (w * h) < 0.82 or len(rings) > 1: continue
        cand.append({'ci': ci, 'x': int(x0), 'y': int(y0), 'w': int(w), 'h': int(h)})
    if len(cand) < 3: return []
    # keep the dominant size group: swatches of one legend are drawn equal
    best = []
    for c in cand:
        g = [d for d in cand if abs(d['w'] - c['w']) <= 0.2 * c['w'] and abs(d['h'] - c['h']) <= 0.25 * c['h']]
        if len(g) > len(best): best = g
    return best if len(best) >= 3 else []

_NUM = re.compile(r'^[\d\s.,;:()\-–—/%°]+$')
MAX_LABEL = 120        # longer text is a paragraph glued to a swatch, not a label
_PLAIN = re.compile(r'^(нет|менее|более|свыше|от|до|прочие|другие|остальные)\b')   # usual lowercase starts
CAPITAL_SHARE = 0.7    # legends written with capitals: a lowercase start means a lost beginning

MIN_CONF = 0.4          # Vision reports 0.3, 0.5 or 1; a long label with a 0.3 line is mostly misread
MIXED_SHARE = 0.25     # more words left in two alphabets: the recognition failed
_ITEM = re.compile(r'^[|/\\•·.\s]*\d{1,3}[\s.•·|]*$')           # the number of a legend item on its own line
_LEAD = re.compile(r'^[|/\\•·.,;:\s]+')                          # stray marks before the text
_NUMBERED = re.compile(r'^\d{1,3}\s*[•·.|]*\s*(?=[A-ZА-ЯЁ(])')   # "19 • Сосновые ..."
_CYR, _LAT = re.compile(r'[а-яёА-ЯЁ]'), re.compile(r'[a-zA-Z]')
_FOREIGN = re.compile(r'[іїґІЇҐ]')                               # never used in Russian text
_LOOK = ('aceopxyABCEHKMOPTX', 'асеорхуАВСЕНКМОРТХ')             # Latin and Cyrillic look-alikes
_TO_CYR, _TO_LAT = str.maketrans(*_LOOK), str.maketrans(_LOOK[1], _LOOK[0])

def columns(sw):
    """Swatches grouped into columns by the left edge -> (columns, median width, median height)."""
    w0 = float(np.median([s['w'] for s in sw])); h0 = float(np.median([s['h'] for s in sw]))
    cols = []
    for s in sorted(sw, key=lambda s: s['x']):
        if cols and abs(cols[-1][0]['x'] - s['x']) <= 0.5 * w0: cols[-1].append(s)
        else: cols.append([s])
    for col in cols: col.sort(key=lambda s: s['y'])
    return cols, w0, h0

def regions(doc):
    """Boxes (x0, y0, x1, y1) that hold the text of every swatch column and its heading;
    the legend text is recognised inside them at a larger scale (ocr_legends.py)."""
    sw = swatches(doc)
    if not sw: return []
    cols, w0, h0 = columns(sw)
    out = []
    for k, col in enumerate(cols):
        x0 = col[0]['x']
        x1 = x0 + w0 * 14              # past the next column: a label may run under it, and a cut line reads badly
        y0 = col[0]['y'] - 3.5 * h0 - 10; y1 = col[-1]['y'] + col[-1]['h'] + 2.6 * h0 + 10
        out.append((max(0, int(x0 - 4)), max(0, int(y0)), min(doc['w'], int(x1)), min(doc['h'], int(y1))))
        # the caption above may span several columns: read its strip wider
        out.append((max(0, int(x0 - 6 * w0)), max(0, int(y0)), min(doc['w'], int(x1 + 6 * w0)), max(0, int(col[0]['y']))))
    return out

def fix_word(w):
    """Replace look-alike letters of the other alphabet inside a word: the recogniser mixes them."""
    w = w.replace('є', 'е').replace('Є', 'Е')
    cyr, lat = len(_CYR.findall(w)), len(_LAT.findall(w))
    if cyr and lat: w = w.translate(_TO_CYR if cyr >= lat else _TO_LAT)
    return w

def mixed(w):
    return bool(_FOREIGN.search(w) or (_CYR.search(w) and _LAT.search(w)))

def tidy(texts):
    """Lines of one swatch -> label text. The item number printed next to the swatch is left out."""
    texts = [t.strip() for t in texts]
    words = [t for t in texts if not _ITEM.match(t)] or texts      # a numeric scale: the numbers are the label
    text = re.sub(r'\s+', ' ', ' '.join(words))
    text = re.sub(r'(\w)- (\w)', r'\1\2', text)                    # undo hyphenation at line breaks
    text = _LEAD.sub('', text)
    return ' '.join(fix_word(w) for w in text.split()).strip(' .;|•·')

def strip_numbers(labels):
    """Legends with numbered items: drop the number in front of the text."""
    hit = {ci: _NUMBERED.sub('', v[0]) for ci, v in labels.items() if _NUMBERED.match(v[0])}
    if len(hit) < 3 or len(hit) < 0.5 * len(labels) or len(set(hit.values())) < 2: return labels
    return {ci: (hit.get(ci, v[0]), v[1]) for ci, v in labels.items()}

def drop_junk(labels):
    """labels: {ci: (text, column)} -> the same without paragraphs, symbols-only text and torn-off pieces."""
    ok = {ci: v for ci, v in labels.items() if len(v[0]) <= MAX_LABEL and re.search(r'[^\W_]', v[0])}
    ok = {ci: v for ci, v in ok.items() if sum(map(mixed, v[0].split())) <= MIXED_SHARE * len(v[0].split())}
    lower = {ci for ci, v in ok.items() if v[0][0].islower() and not _PLAIN.match(v[0])}
    upper = sum(v[0][0].isupper() for v in ok.values())     # labels that start with a digit do not vote
    if upper >= 3 and upper >= CAPITAL_SHARE * (upper + len(lower)):
        ok = {ci: v for ci, v in ok.items() if ci not in lower}
    return ok

def is_heading(line, centres, pitch, text_left, w0, h0):
    """A caption inside a swatch column: it takes a row of its own between two swatches
    and is written in capitals or centred."""
    below = [j for j, c in enumerate(centres) if c > line['cy']]
    if not below or below[0] == 0 or centres[below[0]] - centres[below[0] - 1] < 1.3 * pitch: return False
    t = line['t'].strip()
    letters = re.findall(r'[^\W\d_]', t)
    if len(letters) < 4 or t[0].isdigit() or t.count('(') != t.count(')') or any(map(mixed, t.split())): return False
    if len(letters) >= 5 and t == t.upper(): return True
    off_row = min(abs(line['cy'] - c) for c in centres) > 0.5 * h0
    return off_row and line['x'] > text_left + 1.2 * w0 and t[0].isupper()

def heading_above(col, lines, taken, w0, h0):
    """Up to two free lines right above the top swatch of a column -> caption or ''."""
    top = col[0]['y']; bx0, bx1 = col[0]['x'] - w0, col[0]['x'] + w0 * 5
    above = [l for i, l in enumerate(lines) if i not in taken and l['y'] + l['h'] <= top + 2
             and top - (l['y'] + l['h']) <= h0 * 3.2 and l['h'] <= 2.4 * h0
             and min(l['x'] + l['w'], bx1) - max(l['x'], bx0) > 0.3 * min(l['w'], bx1 - bx0)
             and len(l['t'].strip()) >= 4 and not _NUM.match(l['t'])]
    if not above: return ''
    above.sort(key=lambda l: l['y'])
    pick = [above[-1]]
    # a second line counts only as the wider title right above the first one
    if len(above) > 1 and above[-2]['w'] > above[-1]['w'] and above[-2]['x'] <= above[-1]['x'] + w0 \
            and above[-1]['y'] - (above[-2]['y'] + above[-2]['h']) < 1.5 * above[-1]['h']:
        pick.insert(0, above[-2])
    head = re.sub(r'\s+', ' ', ' '.join(l['t'].strip() for l in pick)).strip()
    # a short single word above a column is usually a place name from the map
    ok = 12 <= len(head) <= 140 and ' ' in head and not head[0].isdigit() and head.count('(') == head.count(')') and not any(map(mixed, head.split()))
    return head if ok else ''

def decode(doc, ocr):
    """-> {'labels': {ci: text}, 'groups': {ci: heading}}

    Every text line right of a swatch column goes to the swatch of that column that is
    nearest by height, so wrapped labels stay together whichever line the swatch sits on."""
    sw = swatches(doc)
    if not sw or not ocr: return {'labels': {}, 'groups': {}}
    lines = [dict(l) for l in ocr['lines'] if l['t'].strip()]
    for l in lines: l['cy'] = l['y'] + l['h'] / 2
    cols, w0, h0 = columns(sw)
    found, taken = [], set()              # found: (class, text, column, heading inside the column)
    for k, col in enumerate(cols):
        left = col[0]['x'] + w0 * 0.8
        right = min([c[0]['x'] for c in cols[k + 1:] if c[0]['x'] > left + w0] + [col[0]['x'] + w0 * 9]) - 2
        centres = [s['y'] + s['h'] / 2 for s in col]
        pitch = float(np.median(np.diff(centres))) if len(col) > 1 else h0 * 2.2
        mine = [(i, l) for i, l in enumerate(lines) if left <= l['x'] < right]
        on_row = [l['x'] for _, l in mine if not _ITEM.match(l['t']) and min(abs(l['cy'] - c) for c in centres) <= 0.5 * h0]
        text_left = float(np.median(on_row)) if on_row else col[0]['x'] + 1.2 * w0
        heads = [(i, l) for i, l in mine if l['x'] < col[0]['x'] + w0 * 6 and is_heading(l, centres, pitch, text_left, w0, h0)]
        taken.update(i for i, _ in heads)
        per = {j: [] for j in range(len(col))}
        for i, l in mine:
            if i in taken or l['x'] > col[0]['x'] + w0 * 3.5: continue
            j = int(np.argmin([abs(l['cy'] - c) for c in centres]))
            if abs(l['cy'] - centres[j]) <= max(0.62 * pitch, 0.8 * h0) and abs(l['cy'] - centres[j]) <= 2.6 * h0:
                per[j].append((i, l))
        for j, s in enumerate(col):
            got = sorted(per[j], key=lambda t: (t[1]['y'], t[1]['x']))
            if not got or not any(abs(l['cy'] - centres[j]) <= 0.9 * h0 for _, l in got): continue
            text = tidy([l['t'] for _, l in got])
            if not text: continue
            if len(text.split()) > 2 and min(l.get('c', 1) for _, l in got) < MIN_CONF: continue
            taken.update(i for i, _ in got)
            inner = [l['t'].strip() for _, l in heads if l['cy'] < s['y']]
            found.append((s['ci'], text, k, inner[-1] if inner else ''))
    # one colour class, several different legend items: the colours are too close to tell, no label
    texts = {}
    for ci, text, _, _ in found: texts.setdefault(ci, set()).add(text)
    labels = {ci: (text, k) for ci, text, k, _ in found if len(texts[ci]) == 1}
    labels = drop_junk(strip_numbers(labels))
    above = {k: heading_above(col, lines, taken, w0, h0) for k, col in enumerate(cols)}
    groups = {}
    for ci, text, k, inner in found:
        head = inner or above[k]
        if ci in labels and head: groups.setdefault(ci, set()).add(head)
    return {'labels': {str(ci): t for ci, (t, _) in labels.items()},
            'groups': {str(ci): g.pop() for ci, g in groups.items() if len(g) == 1}}
