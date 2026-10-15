"""Fill a folder with a hundred Python files, some mediocre and some
decent, then heal them all to beautiful one at a time, like an agent working
through them, so you can watch Synesthete (in project mode, or the tiles)
follow along. It takes about a minute.

Usage: python3 tools/heal_demo.py FOLDER

It asks before healing, so you can open the folder in Sublime first. It
only writes files it made itself, under FOLDER.
"""

import os
import random
import sys
import time

# Synesthete checks for changes twice a second, so edits at least this far
# apart light up one at a time.
SHORTEST, LONGEST = 0.55, 0.7  # seconds between edits
PAUSE = 0.03  # how often the agent stops to think, for a second or two

FOLDERS = ['app/models', 'app/services', 'app/views', 'lib', 'lib/parsers', 'lib/storage',
           'scripts', 'tests']
NOUNS = ['invoice', 'order', 'user', 'account', 'payment', 'ticket', 'report', 'session',
         'message', 'product', 'review', 'coupon', 'shipment', 'refund', 'device', 'team',
         'project', 'comment', 'upload', 'token', 'event', 'schedule', 'quote', 'address']
FIELDS = ['amount', 'count', 'weight', 'score', 'price', 'size', 'total', 'age']
STATES = ['open', 'paid', 'closed', 'pending', 'failed', 'archived']


def clean(noun, field, state, other):
    """Tidy code: short functions, shallow nesting, no smells."""
    title = noun.capitalize()
    return '''"""{title}s: loading, summing and describing them."""


def load_{noun}s(rows):
    """The {noun}s among `rows`."""
    return [row for row in rows if row.get('kind') == '{noun}']


def is_{state}(item):
    return item.get('state') == '{state}'


def total_{field}(items):
    """The {field} of every {state} {noun}, added up."""
    return sum(item.get('{field}', 0) for item in items if is_{state}(item))


def describe(item):
    name = item.get('name', 'unnamed {noun}')
    return '{{}}: {{}} {field}'.format(name, item.get('{field}', 0))


class {title}Index:
    """{title}s by id, with their {other}s."""

    def __init__(self, items):
        self.by_id = {{item['id']: item for item in items}}

    def get(self, key):
        return self.by_id.get(key)

    def {other}s(self, key):
        item = self.get(key)
        return item.get('{other}s', []) if item else []
'''.format(title=title, noun=noun, field=field, state=state, other=other)


def tangled(noun, field, state, other):
    """What clean() replaces: everything in one function, nested deep."""
    pad = '    '
    body = []
    for depth, line in enumerate([
        'for row in rows:',
        "if row.get('kind') == '{noun}':",
        "if row.get('state') == '{state}':",
        "for {other} in row.get('{other}s', []):",
        "if {other}.get('{field}', 0) > 0:",
        "if {other}.get('active'):",
    ]):
        body.append(pad * (depth + 1) + line)
    deep = pad * 7
    body += [
        deep + "total = total + {other}.get('{field}', 0)",
        deep + "names.append(row.get('name', 'unnamed {noun}') + ': ' + str({other}.get('{field}', 0)) + ' {field}')",
        deep + "seen[row['id']] = seen.get(row['id'], 0) + 1",
        pad * 5 + 'else:',
        pad * 6 + 'skipped = skipped + 1',
        pad * 3 + 'else:',
        pad * 4 + 'skipped = skipped + 1',
    ]
    duplicate = [
        pad + 'if total < 0:',
        pad * 2 + "print('negative {field} for {noun}s, resetting it to zero for now')",
        pad * 2 + 'total = 0',
        pad + 'if skipped > 100:',
        pad * 2 + "print('skipped a lot of {noun}s, more than a hundred, check the input')",
    ]
    lines = (['"""{title}s."""   ', '', '', '# TODO: split this up', 'def process(rows):   ',
              pad + 'total = 0', pad + 'names = []   ', pad + 'seen = {{}}', pad + 'skipped = 0']
             + body + duplicate
             + [pad + '# FIXME: nobody knows what this returns   ',
                pad + "return {{'total': total, 'names': names, 'seen': seen, 'skipped': skipped, 'kind': '{noun}', 'state': '{state}'}}",
                '', ''])
    return '\n'.join(lines).format(title=noun.capitalize(), noun=noun, field=field,
                                   state=state, other=other)


def untidy(noun, field, state, other):
    """Decent code with a few smells sprinkled on: long lines, trailing
    whitespace, a TODO."""
    lines = clean(noun, field, state, other).split('\n')
    out = []
    for i, line in enumerate(lines):
        if line.strip() and i % 2 == 0:
            line += '  '
        out.append(line)
    out.insert(3, '# TODO: tidy up the {}s'.format(noun))
    out.append("SUMMARY = 'the {n}s, their {f}s, which ones are {s}, and every {o} that belongs to each of them'".format(
        n=noun, f=field, s=state, o=other))
    out.append("LEGACY = 'kept for old callers of the {n} module, who still read {f} from here, please do not remove'".format(
        n=noun, f=field))
    out.append("FORMAT = '{{name}} paid {{amount}} for {n} number {{id}} on {{date}}, and still owes {{balance}} on it, due by {{due}}'".format(n=noun))
    out.append('')
    return '\n'.join(out)


def plan(seed=7, count=100):
    """[(path, start, end)]: each file's first text and its healed one."""
    rng = random.Random(seed)
    files = []
    used = set()
    while len(files) < count:
        folder = rng.choice(FOLDERS)
        noun = rng.choice(NOUNS)
        variant = rng.randint(1, 9)
        path = os.path.join(folder, '{}_{}.py'.format(noun, variant) if variant > 1 else noun + '.py')
        if folder == 'tests':
            path = os.path.join(folder, 'test_{}_{}.py'.format(noun, variant))
        if path in used:
            continue
        used.add(path)
        args = (noun, rng.choice(FIELDS), rng.choice(STATES), rng.choice(NOUNS))
        if rng.random() < 0.5:
            files.append((path, tangled(*args), clean(*args)))  # mediocre
        else:
            files.append((path, untidy(*args), clean(*args)))  # decent
    return files


def write(root, path, text):
    full = os.path.join(root, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', encoding='utf-8') as f:
        f.write(text)


def main(root):
    files = plan()
    for path, start, _ in files:
        write(root, path, start)
    print('Wrote {} files to {}.'.format(len(files), root))
    if sys.stdin.isatty():
        input('Open it in Sublime (Listen to Project, Open Tiles), then press Return to heal… ')
    rng = random.Random(11)
    rng.shuffle(files)
    started = time.monotonic()
    for path, _, end in files:
        write(root, path, end)
        gap = rng.uniform(SHORTEST, LONGEST)
        if rng.random() < PAUSE:
            gap += rng.uniform(1.0, 2.0)
        time.sleep(gap)
    print('Healed {} files in {:.0f} seconds.'.format(len(files), time.monotonic() - started))


if __name__ == '__main__':
    main(*sys.argv[1:])
