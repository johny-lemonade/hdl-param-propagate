import re
import sys

from .edit import append_item, line_indent, positional_append
from .source import match_paren, prev_token, skip_ws, split_top

_UNIT = re.compile(r'(?<![\w$`])(module|macromodule|interface|program)\s+'
                   r'(?:(?:automatic|static)\s+)?([A-Za-z_][\w$]*)')
_END = {
    'module': 'endmodule',
    'macromodule': 'endmodule',
    'interface': 'endinterface',
    'program': 'endprogram'
}
_KEYWORDS = {
    'if', 'else', 'for', 'while', 'case', 'begin', 'end', 'assign', 'always',
    'initial', 'function', 'task', 'return', 'module', 'wire', 'reg', 'logic',
    'input', 'output', 'inout', 'generate', 'endgenerate', 'assert', 'property'
}
_PARAM_NAME = r'([A-Za-z_][\w$]*)\s*(?:\[[^\]]*\]\s*)*=(?!=)'
_INST_NAME = re.compile(r'([A-Za-z_][\w$]*|\\\S+)\s*(?:\[[^\]]*\]\s*)*\(')
_HASH_VALUE = re.compile(r"[\w$.']+")


class VModule:
    lang_family = 'v'

    def __init__(self, src, name, start, name_end, end):
        self.src, self.name, self.start, self.name_end, self.end = src, name, start, name_end, end
        m = src.masked
        i = skip_ws(m, name_end)
        while m.startswith('import',
                           i) and not re.match(r'[\w$]', m[i + 6:i + 7]):
            i = skip_ws(m, m.index(';', i) + 1)
        self.param_open = self.param_close = None
        if m.startswith('#', i):
            k = skip_ws(m, i + 1)
            if m.startswith('(', k):
                self.param_open, self.param_close = k, match_paren(m, k)
                i = skip_ws(m, self.param_close + 1)
        self.port_open = i if m.startswith('(', i) else None
        if self.port_open is not None:
            i = skip_ws(m, match_paren(m, i) + 1)
        self.hdr_end = i
        self.body = (self.hdr_end + 1, end)

    @property
    def where(self):
        return self.src.where(self.start)

    def _body_decls(self):
        b0, b1 = self.body
        for d in re.finditer(r'(?<![\w$])(parameter|localparam)\b([^;]*);',
                             self.src.masked[b0:b1]):
            yield d.group(1), d.group(2), b0 + d.start()

    def param_names(self):
        if self.param_open is not None:
            items = split_top(
                self.src.masked[self.param_open + 1:self.param_close], ',')
        else:
            items = [
                it for kind, txt, _ in self._body_decls()
                if kind == 'parameter' for it in split_top(txt, ',')
            ]
        names = []
        for it in items:
            x = re.search(_PARAM_NAME, it)
            if x:
                names.append(x.group(1))
        return names

    def has_param(self, name):
        pat = r'(?<![\w$.])' + re.escape(name) + r'\s*(?:\[[^\]]*\]\s*)*=(?!=)'
        if self.param_open is not None and \
                re.search(pat, self.src.masked[self.param_open + 1:self.param_close]):
            return 'parameter'
        for kind, txt, _ in self._body_decls():
            if re.search(pat, txt):
                return kind
        return None

    def add_param(self, spec):
        src, m = self.src, self.src.masked
        item = spec.verilog_decl(src.lang)
        if self.param_open is not None:
            append_item(src, self.param_open, self.param_close, item, ',', '=')
            return
        body_params = [p for k, _, p in self._body_decls() if k == 'parameter']
        if body_params:
            pos = body_params[0]
            ind = line_indent(src, pos)
            sep = src.nl + ind if ind is not None else ' '
            src.insert(pos, f'{item};{sep}')
            return
        pos = self.port_open if self.port_open is not None else self.hdr_end
        while pos > self.name_end and m[pos - 1].isspace():
            pos -= 1
        src.insert(pos, f' #({src.nl}    {item}{src.nl})')


def parse(src):
    m = src.masked
    mods = []
    for x in _UNIT.finditer(m):
        if prev_token(m, x.start()) in ('virtual', 'extern',
                                        'pure') or x.group(2) == 'class':
            continue
        e = re.compile(r'(?<![\w$])' + _END[x.group(1)] + r'(?![\w$])').search(
            m, x.end())
        end = e.end() if e else len(m)
        try:
            mods.append(VModule(src, x.group(2), x.start(), x.end(), end))
        except ValueError:
            print(
                f'warning: {src.where(x.start())}: cannot parse the header of {x.group(2)}',
                file=sys.stderr)
    return mods


def find_instances(src, target, modules):
    m = src.masked
    flags = 0 if target.lang_family == 'v' else re.I
    rx = re.compile(r'(?<![\w$.`:\\])' + re.escape(target.name) + r'(?![\w$])',
                    flags)
    for x in rx.finditer(m):
        pt = prev_token(m, x.start())
        if pt in ('module', 'macromodule', 'interface', 'program', 'bind',
                  '::'):
            continue
        if pt == ':' and prev_token(m, m.rfind(':', 0,
                                               x.start())).startswith('end'):
            continue
        i = skip_ws(m, x.end())
        pm = simple = None
        try:
            if m.startswith('#', i):
                k = skip_ws(m, i + 1)
                if m.startswith('(', k):
                    pm = (k, match_paren(m, k))
                    i = skip_ws(m, pm[1] + 1)
                else:
                    v = _HASH_VALUE.match(m, k)
                    if not v:
                        continue
                    simple = (k, v.end())
                    i = skip_ws(m, v.end())
        except ValueError:
            continue
        im = _INST_NAME.match(m, i)
        if not im or im.group(1) in _KEYWORDS:
            continue
        parent = next((d for d in modules if d.start <= x.start() < d.end),
                      None)
        if parent is None:
            print(
                f'warning: {src.where(x.start())}: instance {im.group(1)} '
                f'is outside of any module - skipped',
                file=sys.stderr)
            continue

        def connect(name, pm=pm, simple=simple, name_end=x.end()):
            return _connect(src, target, name, pm, simple, name_end)

        yield im.group(1), x.start(), parent, connect


def _connect(src, target, name, pm, simple, name_end):
    m = src.masked
    if pm:
        inner = m[pm[0] + 1:pm[1]]
        if not inner.strip():
            src.insert(pm[0] + 1, f'.{name}({name})')
            return 'connected'
        if inner.lstrip().startswith('.'):
            if re.search(r'\.\s*' + re.escape(name) + r'\s*\(', inner):
                return 'already'
            append_item(src, pm[0], pm[1], f'.{name}({name})', ',', '(')
            return 'connected'
        return positional_append(src, target, name, pm[0], pm[1],
                                 split_top(inner, ','))
    if simple:
        if len(target.param_names()) == 1:
            src.insert(simple[0], '(')
            src.insert(simple[1], f', {name})')
            return 'connected (positional)'
        return 'SKIPPED: #value form - connect manually'
    src.insert(name_end, f' #(.{name}({name}))')
    return 'connected'
