"""Legend swatches located by hand (specs/008-quaternary): on these sheets each swatch carries a
printed index or a hatching, its polygon has holes, and legend.swatches finds none.
An item is (code printed in the swatch, x, y of its centre in data/img pixels)."""
import numpy as np

import legend

HALF = (11, 5)          # sampled box stays inside the swatch frame; the median ignores the letters

_COL = {'e': 317, 'ed': 465, 'd': 598, 'a': 730, 'l': 866, 'g': 1002, 'f': 1151, 'v': 1277, 'am': 1397,
        'm': 1513, 'mv': 1638, 'mn': 1765, 'mp': 1883, 'mt': 2005, 'mba': 2125, 'mg': 2245, 'vl': 2368}
_AGES = {'H': 1752, 'III': 1816, 'II': 1878, 'I': 1940, 'E': 1997}
_HAS = {'e': 'H', 'ed': 'H', 'd': 'H III II I E', 'a': 'H III II I E', 'l': 'H III II I E', 'g': 'H III II I',
        'f': 'H III II I', 'v': 'H III', 'am': 'H III II E', 'm': 'H III II I E', 'mv': 'H III', 'mn': 'H',
        'mp': 'H', 'mt': 'H', 'mba': 'H', 'mg': 'H III II', 'vl': 'H III I E'}

SHEETS = {
    '2-60-62-1': [(g + a, _COL[g], _AGES[a]) for g, ages in _HAS.items() for a in ages.split()]
                 + [('r', 2492, 1937)],
}


def sample(lab, items):
    hx, hy = HALF
    return [(code, np.median(lab[y - hy:y + hy + 1, x - hx:x + hx + 1].reshape(-1, 3), 0)) for code, x, y in items]


def inks(items, lab):
    """-> [(colour, [codes])] in table order; swatches closer than legend.SAME_COLOUR share one ink."""
    groups = []
    for code, c in sample(lab, items):
        for g in groups:
            if np.linalg.norm(c - g[0]) < legend.SAME_COLOUR:
                g[1].append(code); break
        else:
            groups.append((c, [code]))
    return groups


def palette(items, lab):
    return [c for c, _ in inks(items, lab)]
