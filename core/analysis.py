"""Judge a piece of source code and boil the verdict down to a single health
score between 0.0 (haunted) and 1.0 (radiant).

Bugs weigh far more than mess: tidy code with a syntax error sounds uneasy,
while correct but sprawling code merely sounds wistful.

Nothing in here imports sublime, so it runs under any Python.
"""

import math
import re
from dataclasses import dataclass

CLOSERS = {')': '(', ']': '[', '}': '{'}
BRACKET_RE = re.compile(r'[()\[\]{}]')
MARKER_RE = re.compile(r'\b(?:TODO|FIXME|XXX|HACK)\b')
NOT_NEWLINE_RE = re.compile(r'[^\n]')


@dataclass
class Report:
    health: float
    lines: int
    syntax_errors: int
    unbalanced_brackets: int
    long_lines: int
    deep_lines: int
    trailing_whitespace: int
    mixed_indentation: bool
    markers: int

    @property
    def bugs(self):
        return self.syntax_errors + self.unbalanced_brackets


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


def health(bugs, lines, long_lines, deep_lines, trailing_whitespace,
           mixed_indentation, markers):
    bug_factor = 1 / (1 + 1.5 * bugs)
    density = (long_lines + deep_lines + 0.5 * trailing_whitespace) / max(lines, 1)
    mess = 1 - math.exp(-4 * density)
    mess += 0.15 * mixed_indentation + 0.04 * min(markers, 5)
    tidiness = 1 - 0.5 * min(mess, 1)
    return bug_factor * tidiness


def examine(text, code=None, comments='', syntax_errors=0, tab_size=4,
            max_line_length=100, max_nesting=4, check_brackets=True):
    """Score `text`. `code` is the same text with strings and comments masked
    out (see `mask`); `comments` is the comment text, searched for TODOs;
    `syntax_errors` is how many spans the editor flagged as invalid."""
    if code is None:
        code = text
    tab_size = max(int(tab_size), 1)

    lines = 0
    long_lines = 0
    trailing = 0
    for line in text.split('\n'):
        if line.strip():
            lines += 1
        if len(line.expandtabs(tab_size)) > max_line_length:
            long_lines += 1
        if line != line.rstrip():
            trailing += 1

    deep_lines = 0
    tab_indented = space_indented = False
    for line in code.split('\n'):
        stripped = line.lstrip()
        if not stripped:
            continue
        indent = line[:len(line) - len(stripped)]
        if '\t' in indent:
            tab_indented = True
        elif len(indent) >= tab_size:
            space_indented = True
        width = len(indent.expandtabs(tab_size))
        # Lines aligned to an opening bracket rarely land on a tab stop, so
        # only count true indentation levels as nesting.
        if width % tab_size == 0 and width // tab_size > max_nesting:
            deep_lines += 1

    unbalanced = unbalanced_brackets(code) if check_brackets else 0
    markers = len(MARKER_RE.findall(comments))
    mixed = tab_indented and space_indented

    return Report(
        health=health(syntax_errors + unbalanced, lines, long_lines, deep_lines,
                      trailing, mixed, markers),
        lines=lines,
        syntax_errors=syntax_errors,
        unbalanced_brackets=unbalanced,
        long_lines=long_lines,
        deep_lines=deep_lines,
        trailing_whitespace=trailing,
        mixed_indentation=mixed,
        markers=markers,
    )
