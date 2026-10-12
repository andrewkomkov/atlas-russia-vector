"""Legend label filter (specs/003-cleanup, FR-005 and FR-006)."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pipeline'))
import legend


def labels(*texts):
    return {i: (t, 0) for i, t in enumerate(texts)}


def kept(*texts):
    return [t for t, _ in legend.drop_junk(labels(*texts)).values()]


class DropJunk(unittest.TestCase):
    def test_paragraph_is_dropped(self):
        self.assertEqual(kept('Леса', 'Степи', 'а' * 121), ['Леса', 'Степи'])

    def test_symbols_only_is_dropped(self):
        self.assertEqual(kept('Леса', '— .'), ['Леса'])

    def test_torn_piece_is_dropped_in_capitalised_legend(self):
        self.assertEqual(kept('Леса', 'Степи', 'Тундра', 'ерритории СССР'), ['Леса', 'Степи', 'Тундра'])

    def test_usual_lowercase_start_is_kept(self):
        self.assertEqual(kept('Леса', 'Степи', 'Тундра', 'нет данных'), ['Леса', 'Степи', 'Тундра', 'нет данных'])

    def test_lowercase_legend_is_kept(self):
        self.assertEqual(kept('от 1 до 3', 'от 3 до 5', 'более 5'), ['от 1 до 3', 'от 3 до 5', 'более 5'])

    def test_numeric_scale_keeps_its_ends(self):
        self.assertEqual(kept('менее 1', '1-3', '3-5', 'более 5'), ['менее 1', '1-3', '3-5', 'более 5'])


if __name__ == '__main__':
    unittest.main()
