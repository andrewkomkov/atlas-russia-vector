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


class Tidy(unittest.TestCase):
    def test_item_number_on_its_own_line_is_left_out(self):
        self.assertEqual(legend.tidy(['Еловые (Picea obovata,', '| 17', 'Betula) редколесья']),
                         'Еловые (Picea obovata, Betula) редколесья')

    def test_numeric_scale_keeps_numbers(self):
        self.assertEqual(legend.tidy(['5']), '5')
        self.assertEqual(legend.tidy(['1-3']), '1-3')

    def test_hyphenation_is_undone(self):
        self.assertEqual(legend.tidy(['северотаеж-', 'ные леса']), 'северотаежные леса')

    def test_lookalike_letters_are_fixed(self):
        self.assertEqual(legend.fix_word('cpeднетаежные'), 'среднетаежные')
        self.assertEqual(legend.fix_word('среднетаєжные'), 'среднетаежные')
        self.assertEqual(legend.fix_word('Рinus'), 'Pinus')

    def test_mixed_word_is_detected(self):
        self.assertTrue(legend.mixed('Еnoпice'))
        self.assertTrue(legend.mixed('Рідна'))
        self.assertFalse(legend.mixed('Сосновые'))


class StripNumbers(unittest.TestCase):
    def test_numbered_legend_loses_numbers(self):
        got = legend.strip_numbers(labels('19 • Сосновые леса', '20 Еловые леса', '21 Березовые леса', 'Степи'))
        self.assertEqual([t for t, _ in got.values()], ['Сосновые леса', 'Еловые леса', 'Березовые леса', 'Степи'])

    def test_numeric_scale_is_untouched(self):
        got = legend.strip_numbers(labels('1-3', '3-5', 'более 5'))
        self.assertEqual([t for t, _ in got.values()], ['1-3', '3-5', 'более 5'])


def swatch_doc(rows):
    """A sheet with a column of 40 x 20 swatches: rows = [(class, y)]."""
    box = lambda y: [100, y, 140, y, 140, y + 20, 100, y + 20]
    return {'w': 2700, 'h': 2000, 'f': [[ci, 0, [box(y)]] for ci, y in rows]}


def line(text, y, x=150, conf=1):
    return {'t': text, 'x': x, 'y': y, 'w': 12 * len(text), 'h': 18, 'c': conf}


class Decode(unittest.TestCase):
    def test_labels_and_inner_heading(self):
        doc = swatch_doc([(1, 100), (2, 140), (3, 220), (4, 260)])
        ocr = {'lines': [line('Леса', 101), line('Степи', 141), line('БОЛОТА', 181), line('Верховые', 221), line('Низинные', 261)]}
        got = legend.decode(doc, ocr)
        self.assertEqual(got['labels'], {'1': 'Леса', '2': 'Степи', '3': 'Верховые', '4': 'Низинные'})
        self.assertEqual(got['groups'], {'3': 'БОЛОТА', '4': 'БОЛОТА'})

    def test_class_with_two_different_items_gets_no_label(self):
        doc = swatch_doc([(1, 100), (1, 140), (2, 180), (3, 220)])
        ocr = {'lines': [line('Леса', 101), line('Степи', 141), line('Тундра', 181), line('Пустыни', 221)]}
        self.assertEqual(legend.decode(doc, ocr)['labels'], {'2': 'Тундра', '3': 'Пустыни'})
        self.assertEqual([a['t'] for a in legend.decode(doc, ocr)['alts']['1']], ['Леса', 'Степи'])

    def test_long_label_with_unsure_line_is_dropped(self):
        doc = swatch_doc([(1, 100), (2, 140), (3, 180)])
        ocr = {'lines': [line('Леса', 101), line('Се не про д рожногажные', 141, conf=0.3), line('Тундра', 181)]}
        self.assertEqual(legend.decode(doc, ocr)['labels'], {'1': 'Леса', '3': 'Тундра'})


class NumberedLegend(unittest.TestCase):
    def numbered(self):
        doc = swatch_doc([(1, 100), (2, 160), (3, 220), (3, 280)])
        ocr = {'lines': [
            line('Хвойные (Pinus sylvestris,', 92), line('16 Larix sibirica) леса', 106),
            line('Южные', 138, x=260), line('17', 162), line('Степи луговые', 162, x=180),
            line('18 Тундры кустарничковые', 221), line('19 Болота верховые', 281),
            line('20 Пустыни северные', 297),
        ]}
        return legend.decode(doc, ocr)

    def test_number_is_kept_apart_from_text(self):
        got = self.numbered()
        self.assertEqual(got['labels'], {'1': 'Хвойные (Pinus sylvestris, Larix sibirica) леса', '2': 'Степи луговые'})
        self.assertEqual(got['nums'], {'1': '16', '2': '17'})

    def test_caption_above_item_names_the_group(self):
        self.assertEqual(self.numbered()['groups'], {'2': 'Южные'})

    def test_one_colour_with_two_items_lists_both(self):
        alts = self.numbered()['alts']['3']
        self.assertEqual([(a['n'], a['t']) for a in alts], [('18', 'Тундры кустарничковые'), ('19', 'Болота верховые')])

    def test_text_is_cut_at_the_number_of_the_next_item(self):
        self.assertNotIn('Пустыни', self.numbered()['alts']['3'][1]['t'])


class Harmonise(unittest.TestCase):
    def test_rare_spelling_follows_the_frequent_one(self):
        texts = ['Betula nana', 'Betula exilis', 'Betula pendula', 'Befula lanata', 'Befula ermanii']
        self.assertEqual(legend.harmonise(texts)[3:], ['Betula lanata', 'Betula ermanii'])

    def test_different_words_are_left_alone(self):
        texts = ['Picea abies', 'Picea obovata', 'Picea ajanensis', 'Pinus pumila']
        self.assertEqual(legend.harmonise(texts), texts)


class Columns(unittest.TestCase):
    def test_column_broken_by_the_map_is_two_blocks(self):
        sw = legend.swatches(swatch_doc([(1, 100), (2, 140), (3, 180), (4, 900), (5, 940), (6, 980)]))
        cols, _, _ = legend.columns(sw)
        self.assertEqual([len(c) for c in cols], [3, 3])


if __name__ == '__main__':
    unittest.main()
