"""Legend swatches located by hand (specs/008-quaternary)."""
import os, sys, unittest
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pipeline'))
import swatch_table


def sheet(*fills):
    lab = np.zeros((40, 40 * len(fills), 3), np.float32)
    for i, c in enumerate(fills):
        lab[:, 40 * i:40 * (i + 1)] = c
        lab[18:21, 40 * i + 15:40 * i + 18] = (5, 0, 0)          # a printed index inside the swatch
    return lab


class SwatchTable(unittest.TestCase):
    def test_close_swatches_share_one_ink(self):
        lab = sheet((80, 10, 10), (81, 11, 10), (50, -20, 30))
        items = [('a', 20, 20), ('b', 60, 20), ('c', 100, 20)]
        self.assertEqual([codes for _, codes in swatch_table.inks(items, lab)], [['a', 'b'], ['c']])
        self.assertEqual(len(swatch_table.palette(items, lab)), 2)

    def test_printed_index_does_not_shift_the_colour(self):
        c, = swatch_table.palette([('a', 20, 20)], sheet((80, 10, 10)))
        self.assertTrue(np.allclose(c, (80, 10, 10)))

    def test_quaternary_legend_has_fifty_swatches(self):
        items = swatch_table.SHEETS['2-60-62-1']
        self.assertEqual(len(items), 50)
        self.assertEqual(len({code for code, _, _ in items}), 50)
        hx, hy = swatch_table.HALF
        self.assertTrue(all(hx <= x < 2900 - hx and 1640 <= y - hy and y + hy < 2099 for _, x, y in items))


if __name__ == '__main__':
    unittest.main()
