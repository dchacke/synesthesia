"""Judge a piece of source code and boil the verdict down to a single health
score between 0.0 (cursed) and 1.0 (beautiful).

Quality comes from structure: long functions, tangled branching, deep
nesting, duplicated code, long lines and general untidiness. It ranges from
1.0 down toward 0.3. Bugs (code the editor cannot parse, brackets that never
close) then divide it further, so broken code always sounds worse than ugly
code, and every additional bug sounds worse still.

Nothing in here imports sublime, so it runs under any Python.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass, field

CLOSERS = {')': '(', ']': '[', '}': '{'}
BRACKET_RE = re.compile(r'[()\[\]{}]')
MARKER_RE = re.compile(r'\b(?:TODO|FIXME|XXX|HACK)\b')
NOT_NEWLINE_RE = re.compile(r'[^\n]')
BLOCK_END_RE = re.compile(r'^(?:[}\])]|end\b)')
DUPLICATE_WINDOW = 4  # consecutive lines that count as a copied chunk
DUPLICATE_MIN_CHARS = 60  # ignore windows of boilerplate like "}\n}\n"
BROKEN = 3  # a file that doesn't parse counts as at least this many bugs


@dataclass
class Limits:
    line_length: int = 100
    nesting: int = 4
    function_lines: int = 40
    branches: int = 10


@dataclass
class Report:
    health: float
    quality: float
    lines: int
    syntax_errors: int = 0
    unbalanced_brackets: int = 0
    long_functions: int = 0
    complex_functions: int = 0
    deep_lines: int = 0
    duplicate_lines: int = 0
    long_lines: int = 0
    trailing_whitespace: int = 0
    mixed_indentation: bool = False
    markers: int = 0
    broken: int = 0  # files the language's own parser rejected
    total_bugs: int = None  # set when combining files
    sheet: list = field(default=None, repr=False, compare=False)  # the code as music; see score.py

    @property
    def bugs(self):
        if self.total_bugs is not None:
            return self.total_bugs
        found = self.syntax_errors + self.unbalanced_brackets
        return max(found, BROKEN) if self.broken else found


def mask(text, spans):
    """Blank out spans (string literals, comments) with spaces, keeping
    newlines so line numbers and indentation survive."""
    pieces = []
    last = 0
    for a, b in sorted(spans):
        a = max(a, last)
        if b <= a:
            continue
        pieces.append(text[last:a])
        pieces.append(NOT_NEWLINE_RE.sub(' ', text[a:b]))
        last = b
    pieces.append(text[last:])
    return ''.join(pieces)


def unbalanced_brackets(code):
    """Count brackets that never find their partner."""
    stack = []
    unbalanced = 0
    for match in BRACKET_RE.finditer(code):
        char = match.group()
        partner = CLOSERS.get(char)
        if partner is None:
            stack.append(char)
        elif partner in stack:
            # Openers skipped over on the way down were never closed.
            while stack.pop() != partner:
                unbalanced += 1
        else:
            unbalanced += 1
    return unbalanced + len(stack)


def function_extents(code_lines, starts, tab_size):
    """For each line where a function starts, the range of lines it spans:
    until the next line indented no deeper than the definition, including
    that line if it merely closes the block (`}`, `end`)."""
    extents = []
    for start in starts:
        if start >= len(code_lines):
            continue
        base = indentation(code_lines[start], tab_size)
        end = start + 1
        while end < len(code_lines):
            line = code_lines[end]
            if line.strip() and indentation(line, tab_size) <= base:
                if BLOCK_END_RE.match(line.strip()):
                    end += 1
                break
            end += 1
        while end - 1 > start and not code_lines[end - 1].strip():
            end -= 1  # trailing blank lines belong to nobody
        extents.append((start, end))
    return extents


def indent_unit(text, default=4):
    """The indentation step `text` uses, judged by how far its lines indent
    past the line before. Files that aren't open in a view need this, since
    Sublime only detects indentation when it opens a file. Returns `default`
    for tab-indented or barely indented text."""
    steps = Counter()
    previous = 0
    for line in text.split('\n'):
        if not line.strip():
            continue
        if line.startswith('\t'):
            return default
        width = len(line) - len(line.lstrip(' '))
        if width > previous:
            steps[width - previous] += 1
        previous = width
    usual = {step: n for step, n in steps.items() if step in (2, 3, 4, 8)}
    return max(usual, key=lambda step: (usual[step], -step)) if usual else default


def indentation(line, tab_size):
    return len(line[:len(line) - len(line.lstrip())].expandtabs(tab_size))


def duplicate_lines(lines):
    """Lines that repeat a chunk seen earlier in the file."""
    content = [(i, line.strip()) for i, line in enumerate(lines) if line.strip()]
    seen = set()
    duplicated = set()
    for k in range(len(content) - DUPLICATE_WINDOW + 1):
        window = tuple(text for _, text in content[k:k + DUPLICATE_WINDOW])
        if sum(map(len, window)) < DUPLICATE_MIN_CHARS:
            continue
        if window in seen:
            duplicated.update(i for i, _ in content[k:k + DUPLICATE_WINDOW])
        else:
            seen.add(window)
    return len(duplicated)


def quality(lines, function_excess, branch_excess, nesting_excess, duplicates,
            long_lines, trailing, mixed, markers):
    """1.0 for tidy code, falling toward 0.3 as smells pile up."""
    smell = (1.0 * function_excess + 3.0 * branch_excess + 1.0 * nesting_excess
             + 1.5 * duplicates + 0.5 * long_lines + 0.25 * trailing) / max(lines, 20)
    smell += 0.08 * mixed + 0.015 * min(markers, 10)
    return 0.3 + 0.7 * math.exp(-3 * smell)


def health(quality, bugs):
    """One bug in beautiful code sounds meh; three, awful; eight, cursed."""
    return quality / (1 + 0.8 * bugs)


def nesting(code_lines, extents, tab_size, limit):
    """(lines nested deeper than `limit`, how many levels too deep they are
    in all, whether tabs and spaces are mixed). Nesting counts from the
    function a line is in, so the module and class wrapped around it don't
    make ordinary code look deep."""
    base = [0] * len(code_lines)
    for start, end in sorted(extents):  # inner functions come later and win
        level = indentation(code_lines[start], tab_size) + tab_size
        for i in range(start + 1, end):
            base[i] = level
    deep = excess = 0
    tabs = spaces = False
    for line, floor in zip(code_lines, base):
        stripped = line.lstrip()
        if not stripped:
            continue
        indent = line[:len(line) - len(stripped)]
        tabs = tabs or '\t' in indent
        spaces = spaces or ('\t' not in indent and len(indent) >= tab_size)
        width = len(indent.expandtabs(tab_size))
        # Lines aligned to an opening bracket rarely land on a tab stop, so
        # only count true indentation levels as nesting.
        depth = (width - floor) // tab_size
        if width % tab_size == 0 and depth > limit:
            deep += 1
            excess += depth - limit
    return deep, excess, tabs and spaces


def function_smells(text_lines, extents, branches, limits):
    """(long functions, their lines past the limit, functions with too many
    branches, their branches past the limit)."""
    long_functions = function_excess = complex_functions = branch_excess = 0
    for start, end in extents:
        length = sum(1 for line in text_lines[start:end] if line.strip())
        count = sum(1 for b in branches if start <= b < end)
        if length > limits.function_lines:
            long_functions += 1
            function_excess += length - limits.function_lines
        if count > limits.branches:
            complex_functions += 1
            branch_excess += count - limits.branches
    return long_functions, function_excess, complex_functions, branch_excess


def examine(text, code=None, comments='', syntax_errors=0, functions=(),
            branches=(), tab_size=4, limits=None, check_brackets=True, broken=False):
    """Score `text`.

    code: the same text with strings and comments masked out (see `mask`).
    comments: the comment text, searched for TODOs.
    syntax_errors: how many spans the editor flagged as invalid.
    functions: line numbers where functions start.
    branches: line numbers of branching keywords (if, for, while, case,
        catch, and, or ...), one entry per keyword.
    broken: whether the language's own parser rejected the code.
    """
    limits = limits or Limits()
    code = text if code is None else code
    tab_size = max(int(tab_size), 1)
    text_lines = text.split('\n')
    code_lines = code.split('\n')

    extents = function_extents(code_lines, functions, tab_size)
    counts = dict(
        lines=sum(1 for line in text_lines if line.strip()),
        long_lines=sum(1 for line in text_lines
                       if len(line.expandtabs(tab_size)) > limits.line_length),
        trailing_whitespace=sum(1 for line in text_lines if line != line.rstrip()),
        duplicate_lines=duplicate_lines(text_lines),
        unbalanced_brackets=unbalanced_brackets(code) if check_brackets else 0,
        markers=len(MARKER_RE.findall(comments)),
        syntax_errors=syntax_errors,
        broken=int(broken),
    )
    counts['deep_lines'], nesting_excess, counts['mixed_indentation'] = nesting(
        code_lines, extents, tab_size, limits.nesting)
    counts['long_functions'], function_excess, counts['complex_functions'], branch_excess = \
        function_smells(text_lines, extents, branches, limits)
    q = quality(counts['lines'], function_excess, branch_excess, nesting_excess,
                counts['duplicate_lines'], counts['long_lines'], counts['trailing_whitespace'],
                counts['mixed_indentation'], counts['markers'])
    report = Report(health=1.0, quality=q, **counts)
    report.health = health(q, report.bugs)
    return report


def combine(reports):
    """Health of a whole project: quality averaged by size, and every bug in
    every file counted against it."""
    reports = list(reports)
    if not reports:
        return None
    weight = sum(max(r.lines, 1) for r in reports)
    q = sum(r.quality * max(r.lines, 1) for r in reports) / weight
    bugs = sum(r.bugs for r in reports)
    return Report(
        health=health(q, bugs),
        quality=q,
        lines=sum(r.lines for r in reports),
        syntax_errors=sum(r.syntax_errors for r in reports),
        unbalanced_brackets=sum(r.unbalanced_brackets for r in reports),
        long_functions=sum(r.long_functions for r in reports),
        complex_functions=sum(r.complex_functions for r in reports),
        deep_lines=sum(r.deep_lines for r in reports),
        duplicate_lines=sum(r.duplicate_lines for r in reports),
        long_lines=sum(r.long_lines for r in reports),
        trailing_whitespace=sum(r.trailing_whitespace for r in reports),
        mixed_indentation=any(r.mixed_indentation for r in reports),
        markers=sum(r.markers for r in reports),
        broken=sum(r.broken for r in reports),
        total_bugs=bugs,
    )
