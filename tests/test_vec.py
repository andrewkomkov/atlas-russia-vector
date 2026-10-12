"""Legend palette in the colour quantisation (specs/004-legend-palette, FR-001)."""
import os, sys, unittest
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pipeline'))
import vec


def stripes(colours, width=60):
    """A sheet of vertical stripes, one BGR colour each."""
    im = np.zeros((120, width * len(colours), 3), np.uint8)
    for n, c in enumerate(colours): im[:, n * width:(n + 1) * width] = c
    return im


class Palette(unittest.TestCase):
    def test_close_colours_merge_without_a_palette(self):
        im = stripes([(60, 60, 200), (64, 66, 205), (200, 80, 40)])
        lab, cen = vec.quantize(im, K=8)
        self.assertEqual(lab[60, 30], lab[60, 90])

    def test_palette_keeps_close_colours_apart(self):
        im = stripes([(60, 60, 200), (64, 66, 205), (200, 80, 40)])
        pal = [vec.to_lab(im)[60, 30], vec.to_lab(im)[60, 90]]
        lab, cen = vec.quantize(im, K=8, palette=pal)
        self.assertEqual((lab[60, 30], lab[60, 90]), (0, 1))
        self.assertEqual(len(cen), 3)               # the third colour comes from k-means

    def test_same_sheet_gives_the_same_classes(self):
        rng = np.random.default_rng(1)
        im = rng.integers(0, 255, (120, 180, 3)).astype(np.uint8)
        first = vec.quantize(im, K=8)
        vec.quantize(stripes([(60, 60, 200), (200, 80, 40)]), K=4)      # another sheet in between
        again = vec.quantize(im, K=8)
        self.assertTrue(np.array_equal(first[0], again[0]) and np.array_equal(first[1], again[1]))


if __name__ == '__main__':
    unittest.main()
