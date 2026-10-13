import base64
import os
import sys
import unittest
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import analysis, mapview, picture  # noqa: E402


def report(health, lines, bugs=0):
    return analysis.Report(health=health, quality=health, lines=lines, syntax_errors=bugs)


class PictureTest(unittest.TestCase):
    def test_png(self):
        canvas = picture.Canvas(3, 2, (10, 20, 30))
        canvas.rect(1, 0, 5, 1, (255, 0, 0))  # clipped at the edge
        data = canvas.png()
        self.assertTrue(data.startswith(b'\x89PNG\r\n\x1a\n'))
        idat = data[data.index(b'IDAT') + 4:data.index(b'IEND') - 8]
        rows = zlib.decompress(idat)
        self.assertEqual(rows, b'\x00' + bytes((10, 20, 30, 255, 0, 0, 255, 0, 0))
                         + b'\x00' + bytes((10, 20, 30)) * 3)

    def test_timeline_draws_the_history_and_ticks(self):
        canvas = picture.timeline([(0, 0.2), (50, 0.9)], [(50, (255, 0, 0))], now=100,
                                  span=100, width=100, height=50, bands=[(0.0, (0, 0, 255))],
                                  background=(0, 0, 0))
        pixels = canvas.pixels

        def at(x, y):
            i = (y * 100 + x) * 3
            return tuple(pixels[i:i + 3])
        self.assertEqual(at(80, 50 - 1 - int(0.9 * 49)), (255, 255, 255))  # the line, late
        self.assertEqual(at(20, 50 - 1 - int(0.2 * 49)), (255, 255, 255))  # and early
        self.assertEqual(at(50, 48), (255, 0, 0))  # the tick
        self.assertTrue(base64.b64decode(canvas.data_uri().split(',')[1]).startswith(b'\x89PNG'))


class MapTest(unittest.TestCase):
    files = {'/p/a.py': report(1.0, 100), '/p/lib/b.py': report(0.2, 50, bugs=2),
             '/p/lib/c.py': report(0.7, 10)}

    def test_tiles_grouped_by_folder_and_linked(self):
        page = mapview.render(self.files, 0.8, {}, [], [], now=0, folders=['/p'])
        self.assertLess(page.index('>.<'), page.index('>lib<'))
        self.assertIn('subl:open_file {&quot;file&quot;: &quot;/p/lib/b.py&quot;}', page)
        self.assertIn('⚠ b.py', page)
        self.assertIn('width: 420px', page)  # the longest file

    def test_changes_light_up_and_fade(self):
        recent = mapview.render(self.files, 0.8, {'/p/a.py': (95, 'up')}, [], [], now=100)
        faded = mapview.render(self.files, 0.8, {'/p/a.py': (80, 'up')}, [], [], now=100)
        self.assertIn('border: 2px solid', recent)
        self.assertNotIn('border: 2px solid', faded)

    def test_timeline_appears_with_history(self):
        page = mapview.render(self.files, 0.8, {}, [(0, 0.8)], [(0, 'same')], now=10)
        self.assertIn('data:image/png;base64,', page)

    def test_too_many_files(self):
        files = {'/p/{}.py'.format(i): report(1.0, i + 1) for i in range(mapview.MAX_TILES + 5)}
        page = mapview.render(files, 1.0, {}, [], [], now=0)
        self.assertIn('and 5 smaller files', page)


if __name__ == '__main__':
    unittest.main()
