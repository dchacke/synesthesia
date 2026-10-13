import math
import os
import sys
import tempfile
import unittest
import wave
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import instruments, music  # noqa: E402


class StageTest(unittest.TestCase):
    def test_thresholds(self):
        names = [music.name(h) for h in (1.0, 0.9, 0.8, 0.65, 0.5, 0.35, 0.2, 0.1, 0.0)]
        self.assertEqual(names, ['beautiful', 'beautiful', 'good', 'decent', 'meh',
                                 'bad', 'awful', 'cursed', 'cursed'])

    def test_every_stage_has_a_composer(self):
        self.assertEqual(len(music.COMPOSERS), len(music.STAGES))

    def test_just_intonation(self):
        self.assertAlmostEqual(music.pitch(7) / music.pitch(0), 1.5)
        self.assertAlmostEqual(music.pitch(12), 2 * music.D3)
        self.assertAlmostEqual(music.pitch(0, 1200), 2 * music.D3)


class RenderTest(unittest.TestCase):
    def test_every_bar_and_accent_renders(self):
        for index in range(len(music.STAGES)):
            for kind in ('bar', 'up', 'down', 'same'):
                length, left, right = music.render(kind, index)
                self.assertEqual(len(left), len(right))
                self.assertAlmostEqual(max(max(map(abs, left)), max(map(abs, right))), 1.0)
                self.assertFalse(any(math.isnan(s) for s in left))
                if kind == 'bar':
                    self.assertGreater(length, 1.0)
                    self.assertGreater(len(left) / music.RATE, length)  # rings past the next bar

    def test_variants_differ(self):
        self.assertNotEqual(music.render('bar', 0, 0)[1], music.render('bar', 0, 1)[1])


class FileTest(unittest.TestCase):
    def test_write_wav(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'a.wav')
            music.write_wav(path, [0.0, 1.0], [0.5, -0.5], volume=1.0)
            with wave.open(path) as w:
                self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()),
                                 (2, 2, music.RATE, 2))
                self.assertEqual(w.readframes(2), b'\x00\x00\xff\x3f\xff\x7f\x01\xc0')
            self.assertEqual(os.listdir(directory), ['a.wav'])

    def test_render_file_caches(self):
        with tempfile.TemporaryDirectory() as directory:
            first = music.render_file('up', 3, 0, 0.5, directory)
            with mock.patch.object(music, 'render') as render:
                second = music.render_file('up', 3, 0, 0.5, directory)
            self.assertEqual(first, second)
            render.assert_not_called()


class InstrumentTest(unittest.TestCase):
    def test_pluck_is_in_tune(self):
        freq = 293.66
        samples = instruments.pluck(freq, t60=1.0, seed=1)[int(0.05 * instruments.RATE):int(0.35 * instruments.RATE)]

        def power(f):
            w = 2 * math.pi * f / instruments.RATE
            re = sum(s * math.cos(w * i) for i, s in enumerate(samples))
            im = sum(s * math.sin(w * i) for i, s in enumerate(samples))
            return re * re + im * im
        cents = max(range(-30, 31, 3), key=lambda c: power(freq * 2 ** (c / 1200)))
        self.assertLessEqual(abs(cents), 3)

    def test_notes_start_silent_and_peak_at_one(self):
        for samples in (instruments.pluck(440), instruments.strike(440, instruments.BELL),
                        instruments.bow(440, instruments.WATERPHONE, 1.0)):
            self.assertAlmostEqual(max(map(abs, samples)), 1.0)
            self.assertLess(abs(samples[0]), 0.05)


if __name__ == '__main__':
    unittest.main()
