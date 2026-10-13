import os
import sys
import tempfile
import unittest
import wave
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import synth  # noqa: E402


class MoodTest(unittest.TestCase):
    def test_thresholds(self):
        names = [synth.mood(h)[0] for h in (1.0, 0.85, 0.7, 0.5, 0.3, 0.1, 0.0)]
        self.assertEqual(names, ['radiant', 'radiant', 'bright', 'wistful',
                                 'uneasy', 'haunted', 'haunted'])

    def test_every_chord_tone_has_a_ratio(self):
        for _, _, chord in synth.MOODS:
            for semitones in chord:
                self.assertIn(semitones, synth.RATIOS)


class RenderTest(unittest.TestCase):
    def test_chime_length_and_loudness(self):
        for health in (0.0, 0.5, 1.0):
            out = synth.render(health, 'chime', volume=0.4)
            self.assertEqual(len(out), int(synth.chime_seconds(health) * synth.RATE))
            self.assertAlmostEqual(max(map(abs, out)), 0.4)
            self.assertAlmostEqual(out[-1], 0.0, places=9)

    def test_pad_fades_in_and_out(self):
        out = synth.render(0.3, 'pad')
        self.assertEqual(len(out), int(synth.PAD_SECONDS * synth.RATE))
        self.assertEqual(out[0], 0.0)
        self.assertAlmostEqual(out[-1], 0.0, places=9)

    def test_same_seed_same_sound(self):
        self.assertEqual(synth.render(0.2, seed=3), synth.render(0.2, seed=3))
        self.assertNotEqual(synth.render(0.2, seed=3), synth.render(0.2, seed=4))


class FileTest(unittest.TestCase):
    def test_write_wav(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'a.wav')
            synth.write_wav(path, [0.0, 0.5, -0.5, 1.0])
            with wave.open(path) as w:
                self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()),
                                 (1, 2, synth.RATE, 4))
                self.assertEqual(w.readframes(4), b'\x00\x00\xff\x3f\x01\xc0\xff\x7f')
            self.assertEqual(os.listdir(directory), ['a.wav'])

    def test_render_file_quantizes_and_caches(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, 'cache')
            first = synth.render_file(0.51, 'chime', 0, 0.5, target)
            with mock.patch.object(synth, 'render') as render:
                second = synth.render_file(0.49, 'chime', 0, 0.5, target)
            self.assertEqual(first, second)
            render.assert_not_called()


if __name__ == '__main__':
    unittest.main()
