"""Read code as sheet music: one line, one step.

Each line's indentation decides how high it sits (deeper code climbs), a
stable hash of its text nudges the note so different lines make different
melodies while identical lines sound identical, and its length decides how
hard it's played. Blank lines are rests. Lines that start functions bring in
the bass, comments ring on a second instrument, and lines the editor flagged
as broken sound a dissonant cluster.
"""

import zlib
from collections import namedtuple

Line = namedtuple('Line', 'depth length kind key broken')  # kind: code, blank, comment, function


def read(text, code=None, functions=(), broken_lines=(), tab_size=4):
    """Lines of `text` as a list of Line. `code` is the text with strings and
    comments masked out, which tells comments from code."""
    code = text if code is None else code
    functions, broken_lines = set(functions), set(broken_lines)
    tab_size = max(int(tab_size), 1)
    sheet = []
    for number, (line, masked) in enumerate(zip(text.split('\n'), code.split('\n'))):
        stripped = line.strip()
        if not stripped:
            kind = 'blank'
        elif number in functions:
            kind = 'function'
        elif not masked.strip():
            kind = 'comment'
        else:
            kind = 'code'
        indent = len(line[:len(line) - len(line.lstrip())].expandtabs(tab_size))
        sheet.append(Line(indent // tab_size, len(stripped), kind,
                          zlib.crc32(stripped.encode('utf-8', 'replace')), number in broken_lines))
    return sheet


def first_difference(old, new):
    """The first line where two sheets differ, or None if they're the same."""
    for i, (a, b) in enumerate(zip(old, new)):
        if a != b:
            return i
    if len(old) != len(new):
        return min(len(old), len(new))
    return None


def changed_lines(old, new, limit=4):
    """Up to `limit` non-blank lines of `new` from the stretch that differs
    from `old`; for a new file, its first lines. If only blank lines changed
    or lines were deleted, the line next to the change."""
    playable = [line for line in new or [] if line.kind != 'blank']
    if old is None or not playable:
        return playable[:limit]
    start = first_difference(old, new)
    if start is None:
        return []
    end, old_end = len(new), len(old)
    while end > start and old_end > start and new[end - 1] == old[old_end - 1]:
        end, old_end = end - 1, old_end - 1  # the unchanged tail
    lines = [line for line in new[start:end] if line.kind != 'blank'][:limit]
    if not lines:
        lines = [line for line in new[max(0, start - 1):start + 1] if line.kind != 'blank'][:1]
    return lines
