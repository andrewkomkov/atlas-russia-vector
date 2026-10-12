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
_ITEM = re.compile(r'^[|/\\•·.\s]*(\d{1,3}[а-яa-z]?)[\s.•·|]*$')   # the number of a legend item on its own line
_LEAD = re.compile(r'^[|/\\•·.,;:\s]+')                          # stray marks before the text
_NUMBERED = re.compile(r'^(\d{1,3}[а-яa-z]?)\s*[•·.|*]*\s*(?=[A-ZА-ЯЁ(])')   # "19 • Сосновые ..."
_LEADNUM = re.compile(r'^[|/\\•·.\s]*(\d{1,3}[а-яa-z]?)[\s•·.|*]+(?=[^\W\d_]|\()')   # a number, then words
COLUMN_GAP = 8         # swatch heights; a wider gap inside a column is the map between two legend blocks
KEEP_SWATCHES = 0.9    # share of the swatches a layer built from the legend colours must still show
SAME_COLOUR = 3.5      # dE; swatches closer than this are printed with one ink
MAX_ALTS = 6           # more legend items of one colour: a list would not help
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
    blocks = []                          # a column broken by the map is two legend blocks
    for col in cols:
        col.sort(key=lambda s: s['y'])
        blocks.append([col[0]])
        for a, b in zip(col, col[1:]):
            if b['y'] - a['y'] > COLUMN_GAP * h0: blocks.append([b])
            else: blocks[-1].append(b)
    return blocks, w0, h0

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
    text = re.sub(r'(?<=[a-z])/(?=[a-z])', 'l', text)             # an italic l is read as a slash
    return ' '.join(fix_word(w) for w in text.split()).strip(' .;|•·')

def number_items(items):
    """Legends with numbered items: move the number in front of the text into item['num']."""
    lead = {id(it): _NUMBERED.match(it['text']) for it in items}
    numbered = [it for it in items if it['num'] or lead[id(it)]]
    rest = {it['text'] if it['num'] else _NUMBERED.sub('', it['text']) for it in numbered}
    if len(numbered) < 3 or len(numbered) < 0.5 * len(items) or len(rest) < 2:
        for it in items: it['num'] = ''
        return items
    for it in items:
        m = lead[id(it)]
        if m and not it['num']: it['num'], it['text'] = m.group(1), it['text'][m.end():]
    return items

def strip_numbers(labels):
    """{ci: (text, column)} with the item numbers removed (see number_items)."""
    items = number_items([{'ci': ci, 'text': t, 'k': k, 'num': ''} for ci, (t, k) in labels.items()])
    return {it['ci']: (it['text'], it['k']) for it in items}

def near(a, b):
    """Two words differ by one letter: replaced, added or lost."""
    if a == b or abs(len(a) - len(b)) > 1: return False
    if len(a) == len(b): return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b): a, b = b, a
    return any(a == b[:i] + b[i + 1:] for i in range(len(b)))

def misread(a, b):
    """The words differ by the pair f/t only: an italic t is often read as f."""
    return len(a) == len(b) and {frozenset(p) for p in zip(a, b) if p[0] != p[1]} == {frozenset('ft')}

def harmonise(texts):
    """Latin names repeat inside a legend: a rare spelling one letter away from a frequent
    one is a misreading ("Befula" among many "Betula"). -> texts with rare spellings fixed."""
    words = re.findall(r'[A-Za-z]{5,}', ' '.join(texts))
    freq = {w: words.count(w) for w in set(words)}
    fix = {}
    for w, n in freq.items():
        better = [v for v, k in freq.items() if k >= 3 and near(w, v) and (k >= 2 * n or (k > n and misread(w, v)))]
        if better: fix[w] = max(better, key=freq.get)
    if not fix: return list(texts)
    return [re.sub(r'[A-Za-z]{5,}', lambda m: fix.get(m.group(), m.group()), t) for t in texts]

def palette(doc, lab):
    """Lab colours of the legend swatches, one per printing ink: lab is the cleaned sheet
    in Lab (vec.to_lab). Swatches closer than SAME_COLOUR share a colour."""
    out = []
    for s in swatches(doc):
        mx, my = int(s['w'] * 0.25), int(s['h'] * 0.25)
        box = lab[s['y'] + my:s['y'] + s['h'] - my, s['x'] + mx:s['x'] + s['w'] - mx].reshape(-1, 3)
        if not len(box): continue
        c = np.median(box, 0)
        if all(np.linalg.norm(c - o) >= SAME_COLOUR for o in out): out.append(c)
    return out

def swatch_classes(doc):
    """How many colour classes the legend swatches of the layer have."""
    return len({s['ci'] for s in swatches(doc)})

def keeps_legend(before, after):
    """The layer built from the legend colours is worth keeping: the swatches are still
    found and they got more classes than in the first pass."""
    return (len(swatches(after)) >= KEEP_SWATCHES * len(swatches(before))
            and swatch_classes(after) > swatch_classes(before))

def drop_junk(labels):
    """labels: {ci: (text, column)} -> the same without paragraphs, symbols-only text and torn-off pieces."""
    ok = {ci: v for ci, v in labels.items() if len(v[0]) <= MAX_LABEL and re.search(r'[^\W_]', v[0])}
    ok = {ci: v for ci, v in ok.items() if sum(map(mixed, v[0].split())) <= MIXED_SHARE * len(v[0].split())}
    lower = {ci for ci, v in ok.items() if v[0][0].islower() and not _PLAIN.match(v[0])}
    upper = sum(v[0][0].isupper() for v in ok.values())     # labels that start with a digit do not vote
    if upper >= 3 and upper >= CAPITAL_SHARE * (upper + len(lower)):
        ok = {ci: v for ci, v in ok.items() if ci not in lower}
    return ok

def is_heading(line, centres, pitch, text_left, text_right, w0, h0):
    """A caption inside a swatch column. It stands between two swatches, off their rows,
    and is written in capitals or is a short centred phrase."""
    below = [j for j, c in enumerate(centres) if c > line['cy']]
    if not below or below[0] == 0: return False
    t = line['t'].strip()
    letters = re.findall(r'[^\W\d_]', t)
    if len(letters) < 4 or t[0].isdigit() or t.count('(') != t.count(')') or any(map(mixed, t.split())): return False
    off_row = min(abs(line['cy'] - c) for c in centres) > 0.5 * h0
    own_row = centres[below[0]] - centres[below[0] - 1] >= 1.3 * pitch
    if len(letters) >= 5 and t == t.upper(): return off_row or own_row
    centred = line['x'] > text_left + 1.2 * w0 and line['x'] + line['w'] / 2 < text_right
    plain = t[0].isupper() and len(t.split()) <= 3 and not re.search(r'[,;()\d]', t)
    return off_row and centred and plain

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

def line_number(t):
    """(item number, the rest of the line) for a line that is or starts with a number, else ('', line)."""
    m = _ITEM.match(t)
    if m: return m.group(1), ''
    m = _LEADNUM.match(t)
    return (m.group(1), t[m.end():]) if m else ('', t)

def is_numbered(items):
    """The legend numbers its items: most swatches have a number of their own next to them."""
    nums = [n for it in items for n in [next((line_number(l['t'])[0] for l in it['lines'] if line_number(l['t'])[0]), '')] if n]
    return len(nums) >= 3 and len(nums) >= 0.5 * len(items) and len(set(nums)) >= 0.8 * len(nums)

def caption_of(parts, centre, w0, h0):
    """The top line of an item is a group caption: short, plain, above the swatch row and
    indented against the label that starts on the next line. -> index of the line or None."""
    if len(parts) < 2 or parts[0][1]: return None
    l, t = parts[0][0], parts[0][0]['t'].strip()
    nxt = next(((p[0], p[2]) for p in parts[1:] if p[2]), None)
    plain = t[:1].isupper() and len(t.split()) <= 2 and not re.search(r'[,;()\d]', t)
    if not nxt or not plain or not nxt[1][:1].isupper(): return None
    text_x = nxt[0]['x'] + (nxt[0]['w'] * (1 - len(nxt[1]) / max(1, len(nxt[0]['t'].strip()))) if nxt[0]['t'].strip() != nxt[1] else 0)
    return 0 if centre - l['cy'] >= 0.7 * h0 and l['x'] > text_x + 0.5 * w0 else None

def own_lines(lines, centre, w0, h0):
    """Lines of a numbered item without the numbers -> (lines, item number, caption line).
    The first number is the item's own. A line with another number belongs to the next
    item, whose swatch was not found: the text is cut there."""
    parts = [(l, *line_number(l['t'].strip())) for l in lines]
    head = None
    if caption_of(parts, centre, w0, h0) is not None: head, parts = parts[0][0], parts[1:]
    first = next((n for n, p in enumerate(parts) if p[1]), None)
    if first is None: return [l for l, _, _ in parts], '', head
    before = parts[:first]
    on_row = any(abs(l['cy'] - centre) <= 0.6 * h0 for l, _, _ in before)
    if on_row and parts[first][0]['cy'] - centre > h0:           # the swatch row has text, the number is a row lower
        return [l for l, _, _ in before], '', head
    own = parts[first][1]
    out = [l for l, _, _ in before]
    for l, num, rest in parts[first:]:
        if num and num != own: break
        if rest: out.append({**l, 't': rest})
    return out, own, head

def read_items(doc, ocr):
    """Legend items: [{'ci': class, 'text', 'num': item number, 'k': column, 'group': heading}].

    Every text line right of a swatch column goes to the swatch of that column that is
    nearest by height, so wrapped labels stay together whichever line the swatch sits on."""
    sw = swatches(doc)
    if not sw or not ocr: return []
    lines = [dict(l) for l in ocr['lines'] if l['t'].strip()]
    for l in lines: l['cy'] = l['y'] + l['h'] / 2
    cols, w0, h0 = columns(sw)
    items, taken = [], set()
    for k, col in enumerate(cols):
        left = col[0]['x'] + w0 * 0.8
        beside = [c[0]['x'] for c in cols if c[0]['x'] > left + w0 and c[0]['y'] <= col[-1]['y'] and c[-1]['y'] >= col[0]['y']]
        right = min(beside + [col[0]['x'] + w0 * 9]) - 2
        centres = [s['y'] + s['h'] / 2 for s in col]
        pitch = float(np.median(np.diff(centres))) if len(col) > 1 else h0 * 2.2
        mine = [(i, l) for i, l in enumerate(lines) if left <= l['x'] < right]
        on_row = [l['x'] for _, l in mine if not _ITEM.match(l['t']) and min(abs(l['cy'] - c) for c in centres) <= 0.5 * h0]
        text_left = float(np.median(on_row)) if on_row else col[0]['x'] + 1.2 * w0
        ends = [l['x'] + l['w'] for _, l in mine if min(abs(l['cy'] - c) for c in centres) <= 0.5 * h0]
        text_right = max(ends) if ends else right
        heads = [(i, l) for i, l in mine
                 if l['x'] < col[0]['x'] + w0 * 6 and is_heading(l, centres, pitch, text_left, text_right, w0, h0)]
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
            taken.update(i for i, _ in got)
            inner = [(l['cy'], l['t'].strip()) for _, l in heads if l['cy'] < s['y']]
            items.append({'ci': s['ci'], 'k': k, 'head': max(inner) if inner else None, 'centre': centres[j],
                          'lines': [l for _, l in got]})
    above = {k: heading_above(col, lines, taken, w0, h0) for k, col in enumerate(cols)}
    numbered = is_numbered(items)
    caption = {}                          # column -> (height, caption) found above a numbered item, valid downwards
    for it in items:
        lines, it['num'], head = own_lines(it['lines'], it['centre'], w0, h0) if numbered else (it['lines'], '', None)
        if head: caption[it['k']] = (head['cy'], head['t'].strip())
        heads = [h for h in (it['head'], caption.get(it['k'])) if h]
        it['group'] = max(heads)[1] if heads else above[it['k']]         # the nearest caption above wins
        it['text'] = tidy([l['t'] for l in lines])
        if len(it['text'].split()) > 2 and min(l.get('c', 1) for l in lines) < MIN_CONF: it['text'] = ''
    items = [it for it in items if it['text']]
    for it, text in zip(items, harmonise([it['text'] for it in items])): it['text'] = text
    keep = drop_junk({n: (it['text'], it['k']) for n, it in enumerate(items)})
    return [it for n, it in enumerate(items) if n in keep]

def decode(doc, ocr):
    """-> {'labels': {ci: text}, 'nums': {ci: item number}, 'groups': {ci: heading},
           'alts': {ci: [{'n': number, 't': text, 'g': heading}]}}

    A class with one legend item gets a label. A class shared by several different items
    (the legend prints them with one ink and tells them apart by number) gets the list."""
    by_class = {}
    for it in read_items(doc, ocr):
        seen = by_class.setdefault(it['ci'], [])
        if not any(o['text'] == it['text'] and o['num'] == it['num'] for o in seen): seen.append(it)
    out = {'labels': {}, 'nums': {}, 'groups': {}, 'alts': {}}
    for ci, its in by_class.items():
        ci = str(ci)
        if len({it['text'] for it in its}) == 1:
            out['labels'][ci] = its[0]['text']
            if len(its) == 1 and its[0]['num']: out['nums'][ci] = its[0]['num']
            heads = {it['group'] for it in its if it['group']}
            if len(heads) == 1: out['groups'][ci] = heads.pop()
        elif len(its) <= MAX_ALTS:
            out['alts'][ci] = [{'n': it['num'], 't': it['text'], 'g': it['group']} for it in its]
    return {k: v for k, v in out.items() if v or k in ('labels', 'groups')}
