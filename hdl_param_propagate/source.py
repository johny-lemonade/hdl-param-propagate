import bisect
import os
import re

SV_EXT = {'.sv', '.svh'}
V_EXT = {'.v', '.vh'}
VHDL_EXT = {'.vhd', '.vhdl'}
ALL_EXT = SV_EXT | V_EXT | VHDL_EXT

_V_LEX = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\\n])*"', re.S)
_VHDL_LEX = re.compile(r'--[^\n]*|/\*.*?\*/|"(?:""|[^"\n])*"|\'.\'', re.S)


def lang_of(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in SV_EXT:
        return 'sv'
    if ext in V_EXT:
        return 'v'
    if ext in VHDL_EXT:
        return 'vhdl'
    return None


def _mask(text, rx):

    def rep(m):
        s = m.group(0)
        if s[0] in '"\'':
            return s[0] + re.sub(r'[^\n]', ' ', s[1:-1]) + s[-1]
        return re.sub(r'[^\n]', ' ', s)

    return rx.sub(rep, text)


class Source:

    def __init__(self, path):
        self.path = path
        self.lang = lang_of(path)
        with open(path, encoding='utf-8', errors='surrogateescape',
                  newline='') as f:
            self.text = f.read()
        self.masked = _mask(self.text,
                            _VHDL_LEX if self.lang == 'vhdl' else _V_LEX)
        self.nl = '\r\n' if '\r\n' in self.text else '\n'
        self.edits = []
        self._lines = [0] + [m.end() for m in re.finditer('\n', self.text)]

    @property
    def is_vhdl(self):
        return self.lang == 'vhdl'

    def line(self, pos):
        return bisect.bisect_right(self._lines, pos)

    def where(self, pos):
        return f'{self.path}:{self.line(pos)}'

    def insert(self, pos, s):
        self.edits.append((pos, len(self.edits), s))

    def result(self):
        out = self.text
        for pos, _, s in sorted(self.edits, reverse=True):
            out = out[:pos] + s + out[pos:]
        return out


def skip_ws(m, i):
    n = len(m)
    while i < n and m[i].isspace():
        i += 1
    return i


def match_paren(m, i):
    depth = 0
    for j in range(i, len(m)):
        c = m[j]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                return j
    raise ValueError('unbalanced parenthesis')


def prev_token(m, i):
    j = i - 1
    while j >= 0 and m[j].isspace():
        j -= 1
    if j < 0:
        return ''
    if re.match(r'[\w$]', m[j]):
        k = j
        while k >= 0 and re.match(r'[\w$]', m[k]):
            k -= 1
        return m[k + 1:j + 1]
    return m[j]


def split_top(s, sep):
    parts, depth, cur = [], 0, 0
    for i, c in enumerate(s):
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
        elif c == sep and depth == 0:
            parts.append(s[cur:i])
            cur = i + 1
    parts.append(s[cur:])
    return parts
