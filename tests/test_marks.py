"""Sheet marks (specs/007-fauna-sheets): legend by swatch colour, unit growth, inks, page text."""
import os, sys, unittest
import numpy as np, cv2
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pipeline'))
import legend, marks

BLUE, PINK, WHITE = (200, 120, 60), (180, 120, 230), (255, 255, 255)   # BGR


def sheet():
    """Two fills side by side with a legend of two swatches below."""
    im = np.full((200, 300, 3), 255, np.uint8)
    im[20:120, 20:140] = BLUE
    im[20:120, 140:280] = PINK
    im[150:170, 20:50] = PINK            # first swatch: pink
    im[150:170, 100:130] = BLUE          # second swatch: blue
    return im


def vector(im):
    """A vector of the sheet: class 0 blue, class 1 pink, both inside the territory."""
    hexes = ['#%02x%02x%02x' % c[::-1] for c in (BLUE, PINK)]
    box = lambda x0, y0, x1, y1: [x0, y0, x1, y0, x1, y1, x0, y1]
    return {'w': im.shape[1], 'h': im.shape[0], 'colors': hexes,
            'f': [[0, 1, [box(20, 20, 139, 119)]], [1, 1, [box(140, 20, 279, 119)]]]}


class Legend(unittest.TestCase):
    def test_swatch_colour_picks_the_class_not_the_position(self):
        im = sheet()
        items = [{'key': 'a', 'swatch': [20, 150, 30, 20]}, {'key': 'b', 'swatch': [100, 150, 30, 20]}]
        by_class, lost = marks.legend_table(im, vector(im), items)
        self.assertEqual({ci: [it['key'] for it in its] for ci, its in by_class.items()}, {1: ['a'], 0: ['b']})
        self.assertEqual(lost, [])

    def test_swatch_of_a_colour_the_vector_lacks_is_lost(self):
        im = sheet()
        im[150:170, 200:230] = (20, 200, 20)
        _, lost = marks.legend_table(im, vector(im), [{'key': 'g', 'swatch': [200, 150, 30, 20]}])
        self.assertEqual([it['key'] for it in lost], ['g'])

    def test_layer_print_changes_with_the_colours(self):
        im = sheet()
        doc = vector(im)
        other = {**doc, 'colors': doc['colors'][::-1]}
        self.assertNotEqual(legend.layer_print(doc), legend.layer_print(other))


class Units(unittest.TestCase):
    def test_units_stop_at_the_colour_edge(self):
        im = sheet()
        units, keys = marks.grow_units(im, vector(im), [['1', 40, 60], ['2', 260, 100]], [])
        self.assertEqual(keys[units[60, 130] - 1], '1')
        self.assertEqual(keys[units[60, 150] - 1], '2')
        self.assertEqual(units[180, 150], -1)                     # paper outside the territory

    def test_land_without_a_seed_keeps_no_unit(self):
        im = sheet()
        doc = vector(im)
        doc['f'][1][2] = [[160, 20, 279, 20, 279, 119, 160, 119]]     # a gap of paper splits the land
        im[20:120, 140:160] = WHITE
        units, _ = marks.grow_units(im, doc, [['1', 40, 60]], [])
        self.assertEqual(units[60, 200], 0)

    def test_hand_area_overrides_the_growth(self):
        im = sheet()
        units, keys = marks.grow_units(im, vector(im), [['1', 40, 60]], [])
        units, keys = marks.paint_areas(units, keys, [{'key': '1а', 'xy': [30, 30, 60, 30, 60, 60, 30, 60]}])
        self.assertEqual(keys[units[45, 45] - 1], '1а')
        self.assertEqual(keys[units[100, 100] - 1], '1')

    def test_polygons_carry_the_unit_index(self):
        im = sheet()
        units, keys = marks.grow_units(im, vector(im), [['1', 40, 60], ['2', 260, 100]], [])
        got = {keys[u] for u, _, _ in marks.unit_polygons(units, len(keys))}
        self.assertEqual(got, {'1', '2'})


class Inks(unittest.TestCase):
    def test_short_blob_is_a_point_long_dashes_are_one_line(self):
        im = np.full((200, 300, 3), 255, np.uint8)
        cv2.circle(im, (50, 50), 5, (0, 0, 220), -1)
        for x in range(60, 260, 12): cv2.line(im, (x, 150), (x + 8, 150), (0, 0, 220), 2)
        pts, lines = marks.ink_features(im, {'kind': 'k', 'rgb': '#dc0000', 'de': 30, 'point': 20, 'join': 4})
        self.assertEqual(pts, [[50, 50]])
        self.assertEqual(len(lines), 1)
        xs = lines[0][0::2]
        self.assertGreater(max(xs) - min(xs), 180)


class PageText(unittest.TestCase):
    PAGE = ('<h3>X</h3><h4>ТУНДРОВЫЙ ТИП</h4><p><b>Арктотундровый 1)</b></p><p>Гагара, <em>пуночка</em>:</p>'
            '<p>1. Глупыш в морских: а) об. гага, <em>тупик; </em>б) моевка</p><p>г2.Куропатка</p><p>Стоп</p>')

    def test_units_variants_and_italics(self):
        u = marks.page_units(self.PAGE, '<h3>X', 'Стоп')
        self.assertEqual(sorted(u), ['1', '1а', '1б', 'г2'])
        self.assertEqual(u['1']['subtype'], 'Арктотундровый')
        self.assertEqual(u['1']['shared'], 'Гагара, пуночка')
        self.assertEqual(u['1а']['text'], 'Глупыш в морских: об. гага, тупик')
        self.assertEqual(u['1а']['italic'], ['тупик'])

    def test_a_fix_that_does_not_apply_fails(self):
        with self.assertRaises(ValueError):
            marks.page_units(self.PAGE, '<h3>X', 'Стоп', [['нет такого', 'x']])


if __name__ == '__main__':
    unittest.main()
