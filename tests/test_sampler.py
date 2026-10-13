import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import sampler  # noqa: E402

LIBRARY = sampler.Library(os.path.join(ROOT, 'samples'))


class LibraryTest(unittest.TestCase):
    def test_every_recording_loads(self):
        for instrument, recordings in LIBRARY.manifest.items():
            for name in recordings:
                self.assertGreater(len(LIBRARY._recording(instrument, name)), sampler.RATE // 2)

    def test_plays_the_nearest_recording_at_the_asked_pitch(self):
        harp = LIBRARY.manifest['harp']
        note = LIBRARY.note('harp', freq=harp['D4'] * 2 ** (1 / 12), seconds=1.0)
        self.assertEqual(len(note), sampler.RATE)
        self.assertAlmostEqual(note[-1], 0.0, places=3)  # faded at the cut
        key = ('harp', 'D4', round(2 ** (1 / 12), 4), 1.0)
        self.assertIn(key, LIBRARY._notes)

    def test_unpitched_by_name(self):
        note = LIBRARY.note('gong', name='gongHit_p', ratio=2.0)
        self.assertAlmostEqual(len(note), len(LIBRARY._recording('gong', 'gongHit_p')) / 2, delta=2)


class ResampleTest(unittest.TestCase):
    def test_an_octave_up_halves_the_length(self):
        import array
        pcm = array.array('h', (int(10000 * math.sin(i / 10)) for i in range(1001)))
        self.assertEqual(len(sampler.resample(pcm, 2.0)), 500)
        self.assertAlmostEqual(sampler.resample(pcm, 1.0)[100], pcm[100] / 32768)


if __name__ == '__main__':
    unittest.main()
