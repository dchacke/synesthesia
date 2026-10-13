import os
import sys
import tempfile
import unittest
import wave
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import music, score  # noqa: E402
from core.sampler import Library  # noqa: E402

LIBRARY = Library(os.path.join(ROOT, 'samples'))
CODE = '''\
# A greeting.
def greet(name):
    if name:
        return 'Hello, ' + name

    return 'Hello'
'''
SHEET = score.read(CODE, CODE.replace('# A greeting.', ''), functions=[1], broken_lines=[3])


class StageTest(unittest.TestCase):
    def test_thresholds(self):
        names = [music.name(h) for h in (1.0, 0.9, 0.8, 0.65, 0.5, 0.35, 0.2, 0.1, 0.0)]
        self.assertEqual(names, ['beautiful', 'beautiful', 'good', 'decent', 'meh',
                                 'bad', 'awful', 'cursed', 'cursed'])

    def test_every_sound_is_in_the_library(self):
        for s in music.STAGES:
            for instrument, where in (s.melody, s.comment, s.bass[:2], s.function, s.broken):
                self.assertIn(instrument, LIBRARY.manifest)
                if isinstance(where, str):
                    self.assertIn(where, LIBRARY.manifest[instrument])


class ArrangeTest(unittest.TestCase):
    def test_lines_become_notes(self):
        events, seconds = music.arrange(SHEET, 0, 0)
        self.assertAlmostEqual(seconds, music.STEPS * music.STAGES[0].step)
        instruments = [e.instrument for e in events]
        self.assertEqual(instruments[0], 'cello')  # the bass opens the bar
        self.assertIn('glock', instruments)  # the comment
        self.assertIn('bass_pizz', instruments)  # the function
        self.assertEqual(instruments.count('bells'), 2)  # the broken line's cluster

    def test_blank_lines_are_rests(self):
        events, _ = music.arrange(SHEET, 0, 0)
        blank = SHEET.index(next(line for line in SHEET if line.kind == 'blank'))
        step = music.STAGES[0].step
        self.assertFalse([e for e in events[1:] if abs(e.time - blank * step) < step / 2])

    def test_identical_code_sounds_identical(self):
        self.assertEqual(music.arrange(SHEET, 2, 4), music.arrange(list(SHEET), 2, 4))

    def test_cursed_code_gets_a_singing_saw(self):
        saws = [e for e in music.arrange(SHEET * 2, 0, 6)[0] if e.instrument == 'saw']
        self.assertEqual(len(saws), 1)
        points = saws[0].sample
        self.assertLess(points[-1][1], points[-2][1])  # it sighs down at the end
        self.assertFalse([e for e in music.arrange(SHEET, 0, 5)[0] if e.instrument == 'saw'])

    def test_singing_saw(self):
        x = music.singing_saw(((0.0, 600.0), (0.5, 800.0)), 1.5)
        self.assertEqual(len(x), int(1.5 * music.RATE))
        self.assertEqual(x[0], 0.0)  # bowed in from silence
        self.assertLess(abs(x[-1]), 0.01)  # and out again
        self.assertLess(max(map(abs, x)), 1.2)

    def test_the_end_of_the_code_trails_off_into_rests(self):
        events, _ = music.arrange(SHEET, len(SHEET) - 2, 0)
        self.assertTrue(all(e.time < 2 * music.STAGES[0].step for e in events))

    def test_empty_code_still_has_a_bass(self):
        events, _ = music.arrange([], 0, 3)
        self.assertEqual(len(events), 1)

    def test_accents_from_changed_lines(self):
        lines = [line for line in SHEET if line.kind != 'blank']
        up = music.accent_events(1, 'up', lines)
        self.assertEqual(len(up), len(lines))
        self.assertEqual([e.freq for e in up], sorted(e.freq for e in up))
        down = music.accent_events(1, 'down', lines)
        self.assertEqual([e.freq for e in down], sorted((e.freq for e in down), reverse=True))
        self.assertNotEqual(music.accent_events(1, 'same', lines[:2]),
                            music.accent_events(1, 'same', lines[2:4]))

    def test_accents(self):
        for index in range(len(music.STAGES)):
            up = music.accent_events(index, 'up')
            self.assertLess(up[0].freq, up[-1].freq)
            self.assertEqual(len(music.accent_events(0, 'same')), 1)


class FileTest(unittest.TestCase):
    def test_bars_are_cached_by_content(self):
        with tempfile.TemporaryDirectory() as directory:
            seconds, first = music.bar_file(LIBRARY, SHEET, 0, 2, 0.3, directory)
            with mock.patch.object(music, 'render') as render:
                again = music.bar_file(LIBRARY, list(SHEET), 0, 2, 0.3, directory)
                self.assertEqual(again, (seconds, first))
            render.assert_not_called()
            other = score.read(CODE + 'x = 1\n')
            self.assertNotEqual(music.bar_file(LIBRARY, other, 0, 2, 0.3, directory)[1], first)
            with wave.open(first) as w:
                self.assertEqual((w.getnchannels(), w.getframerate()), (2, music.RATE))
                # It rings on into the next bar.
                self.assertGreater(w.getnframes() / music.RATE, seconds)

    def test_accent_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = music.accent_file(LIBRARY, 6, 'down', 0.5, directory)
            self.assertTrue(os.path.exists(path))

    def test_write_wav(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'a.wav')
            music.write_wav(path, [0.0, 1.0], [0.5, -0.5], volume=1.0)
            with wave.open(path) as w:
                self.assertEqual(w.readframes(2), b'\x00\x00\xff\x3f\xff\x7f\x01\xc0')


if __name__ == '__main__':
    unittest.main()
