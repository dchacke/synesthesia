"""Draw small pictures in pure Python and encode them as PNG, for the map's
timeline. Sublime's HTML can show them inline as data URIs."""

import base64
import struct
import zlib


class Canvas:
    """An RGB image you can fill rectangles on."""

    def __init__(self, width, height, background=(0, 0, 0)):
        self.width, self.height = width, height
        self.pixels = bytearray(bytes(background) * (width * height))

    def rect(self, x, y, w, h, color):
        x0, x1 = max(0, int(x)), min(self.width, int(x + w))
        y0, y1 = max(0, int(y)), min(self.height, int(y + h))
        if x0 >= x1:
            return
        row = bytes(color) * (x1 - x0)
        for yy in range(y0, y1):
            start = (yy * self.width + x0) * 3
            self.pixels[start:start + len(row)] = row

    def png(self):
        """The image as PNG bytes."""
        stride = self.width * 3
        raw = b''.join(b'\x00' + bytes(self.pixels[y * stride:(y + 1) * stride])
                       for y in range(self.height))

        def chunk(kind, data):
            body = kind + data
            return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body))
        header = struct.pack('>IIBBBBB', self.width, self.height, 8, 2, 0, 0, 0)
        return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header)
                + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))

    def data_uri(self):
        return 'data:image/png;base64,' + base64.b64encode(self.png()).decode('ascii')


def timeline(history, changes, now, span, width, height, bands, background):
    """Health over the last `span` seconds: a line through `history`, a list
    of (time, health), over faint bands of (lowest health, color), with a
    tick along the bottom for each of `changes`, a list of (time, color)."""
    canvas = Canvas(width, height, background)
    ordered = sorted(bands)  # each band reaches up to the next one's threshold
    for i, (threshold, color) in enumerate(ordered):
        ceiling = ordered[i + 1][0] if i + 1 < len(ordered) else 1.0
        top = height - 1 - int(ceiling * (height - 1))
        bottom = height - 1 - int(threshold * (height - 1))
        faint = tuple((c + 3 * b) // 4 for c, b in zip(color, background))
        canvas.rect(0, top, width, bottom - top + 1, faint)

    def x_of(t):
        return int((t - (now - span)) / span * (width - 1))

    def y_of(health):
        return height - 1 - int(max(0.0, min(1.0, health)) * (height - 1))

    thick = max(2, height // 30)
    points = [(x_of(t), y_of(h)) for t, h in history if t >= now - span]
    if history and (not points or points[0][0] > 0):  # where it stood before the window
        earlier = [h for t, h in history if t < now - span]
        if earlier:
            points.insert(0, (0, y_of(earlier[-1])))
    white = (255, 255, 255)
    for i, (x, y) in enumerate(points):  # a step chart: each value holds until the next
        last = i + 1 == len(points)
        x2 = width if last else points[i + 1][0]
        canvas.rect(x, y - thick // 2, x2 - x + thick, thick, white)
        if not last:
            y2 = points[i + 1][1]
            canvas.rect(x2, min(y, y2) - thick // 2, thick, abs(y2 - y) + thick, white)
    for t, color in changes:
        if t >= now - span:
            canvas.rect(x_of(t), height - height // 5, thick, height // 5, color)
    return canvas
