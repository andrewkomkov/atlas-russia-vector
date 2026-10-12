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

def decode(doc, ocr):
    """-> {'labels': {ci: text}, 'groups': {ci: heading}}

    Every text line right of a swatch column goes to the swatch of that column that is
    nearest by height, so wrapped labels stay together whichever line the swatch sits on."""
    sw = swatches(doc)
    if not sw or not ocr: return {'labels': {}, 'groups': {}}
    lines = [dict(l) for l in ocr['lines'] if l['t'].strip()]
    for l in lines: l['cy'] = l['y'] + l['h'] / 2
    w0 = float(np.median([s['w'] for s in sw])); h0 = float(np.median([s['h'] for s in sw]))
    # columns of swatches by left edge
    cols = []
    for s in sorted(sw, key=lambda s: s['x']):
        if cols and abs(cols[-1][0]['x'] - s['x']) <= 0.5 * w0: cols[-1].append(s)
        else: cols.append([s])
    labels, groups, taken = {}, {}, set()
    for k, col in enumerate(cols):
        col.sort(key=lambda s: s['y'])
        left = col[0]['x'] + w0 * 0.8
        right = min([c[0]['x'] for c in cols[k + 1:] if c[0]['x'] > left + w0] + [col[0]['x'] + w0 * 9]) - 2
        mine = [(i, l) for i, l in enumerate(lines) if left <= l['x'] < right and l['x'] <= col[0]['x'] + w0 * 3.5 + (0 if True else 0)]
        # a line that starts further right is a second line of a label only if another line of the column starts near it
        centres = [s['y'] + s['h'] / 2 for s in col]
        pitch = float(np.median(np.diff(centres))) if len(col) > 1 else h0 * 2.2
        per = {i: [] for i in range(len(col))}
        for i, l in mine:
            j = int(np.argmin([abs(l['cy'] - c) for c in centres]))
            if abs(l['cy'] - centres[j]) <= max(0.62 * pitch, 0.8 * h0) and abs(l['cy'] - centres[j]) <= 2.6 * h0:
                per[j].append((i, l))
        for j, s in enumerate(col):
            got = sorted(per[j], key=lambda t: (t[1]['y'], t[1]['x']))
            if not got or not any(abs(l['cy'] - centres[j]) <= 0.9 * h0 for _, l in got): continue
            text = re.sub(r'\s+', ' ', ' '.join(l['t'].strip() for _, l in got))
            text = re.sub(r'(\w)- (\w)', r'\1\2', text).strip(' .;')      # undo hyphenation at line breaks
            if not text or len(text) > 240: continue
            taken.update(i for i, _ in got)
            if s['ci'] not in labels: labels[s['ci']] = (text, k)
    # heading: up to two free lines right above the top of the column
    for k, col in enumerate(cols):
        top = col[0]['y']; bx0, bx1 = col[0]['x'] - w0, col[0]['x'] + w0 * 5
        above = [l for i, l in enumerate(lines) if i not in taken and l['y'] + l['h'] <= top + 2 and top - (l['y'] + l['h']) <= h0 * 3.2
                 and min(l['x'] + l['w'], bx1) - max(l['x'], bx0) > 0.3 * min(l['w'], bx1 - bx0)
                 and len(l['t'].strip()) >= 4 and not _NUM.match(l['t'])]
        above = [l for l in above if l['h'] <= 2.4 * h0]
        above.sort(key=lambda l: l['y'])
        if above:
            pick = [above[-1]]
            # a second line counts only as the wider title right above the first one
            if len(above) > 1 and above[-2]['w'] > above[-1]['w'] and above[-2]['x'] <= above[-1]['x'] + w0 \
                    and above[-1]['y'] - (above[-2]['y'] + above[-2]['h']) < 1.5 * above[-1]['h']:
                pick.insert(0, above[-2])
            head = re.sub(r'\s+', ' ', ' '.join(l['t'].strip() for l in pick)).strip()
            if len(head) <= 140:
                for ci, (t, kk) in labels.items():
                    if kk == k: groups[ci] = head
    return {'labels': {str(ci): t for ci, (t, _) in labels.items()}, 'groups': {str(ci): g for ci, g in groups.items()}}
