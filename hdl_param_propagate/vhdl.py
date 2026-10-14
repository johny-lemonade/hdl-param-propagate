import re
import sys

from .edit import append_item, line_indent, positional_append
from .source import match_paren, prev_token, skip_ws, split_top

_ENTITY = re.compile(r'(?<![\w.])entity\s+(\w+)\s+is\b', re.I)
_ARCH = re.compile(r'(?<![\w.])architecture\s+(\w+)\s+of\s+(\w+)\s+is\b', re.I)
_PKG = re.compile(r'(?<![\w.])package\s+(?:body\s+)?(\w+)\s+is\b', re.I)
_CFG = re.compile(r'(?<![\w.])configuration\s+\w+\s+of\b', re.I)
_COMP = re.compile(r'(?<![\w.])component\s+(\w+)(\s+is\b)?', re.I)
_GENERIC = re.compile(r'generic\s*\(', re.I)
_CONSTANT = re.compile(r'^\s*constant\s+', re.I)
_INST = re.compile(
    r'(?<![\w.])(\w+)\s*:\s*(?:entity\s+(?:\w+\s*\.\s*)?(\w+)(?:\s*\(\s*\w+\s*\))?|'
    r'(?:component\s+)?(\w+))\s*(?<=[\s)])(generic|port)\s+map\b', re.I)


class VhdlDecl:
    lang_family = 'vhdl'

    def __init__(self, src, kind, name, start, hdr_start):
        self.src, self.kind, self.name, self.start = src, kind, name, start
        m = src.masked
        i = skip_ws(m, hdr_start)
        self.gen_open = self.gen_close = None
        g = _GENERIC.match(m, i)
        if g:
            self.gen_open = g.end() - 1
            self.gen_close = match_paren(m, self.gen_open)
            i = skip_ws(m, self.gen_close + 1)
            if m.startswith(';', i):
                i = skip_ws(m, i + 1)
        self.ins_pos = i

    @property
    def where(self):
        return self.src.where(self.start)

    def param_names(self):
        if self.gen_open is None:
            return []
        names = []
        for it in split_top(self.src.masked[self.gen_open + 1:self.gen_close],
                            ';'):
            head = _CONSTANT.sub('', it.split(':')[0])
            names += [n.strip().lower() for n in head.split(',') if n.strip()]
        return names

    def has_param(self, name):
        return 'generic' if name.lower() in self.param_names() else None

    def add_param(self, spec):
        src = self.src
        item = spec.vhdl_decl()
        if self.gen_open is not None:
            append_item(src, self.gen_open, self.gen_close, item, ';', ':')
            return
        ind = line_indent(src, self.ins_pos)
        if ind is None:
            src.insert(self.ins_pos, f'generic ({item}); ')
        else:
            nl = src.nl
            src.insert(self.ins_pos,
                       f'generic ({nl}{ind}  {item}{nl}{ind});{nl}{ind}')


class VhdlArch:

    def __init__(self, src, name, entity, start, end):
        self.src, self.name, self.entity, self.start, self.end = src, name, entity, start, end


def parse(src):
    m = src.masked
    entities, comps, archs = [], [], []
    units = [(x.start(), 'entity', x) for x in _ENTITY.finditer(m)]
    units += [(x.start(), 'arch', x) for x in _ARCH.finditer(m)]
    units += [(x.start(), 'other', x) for rx in (_PKG, _CFG)
              for x in rx.finditer(m)]
    units.sort(key=lambda u: u[0])
    for n, (pos, kind, x) in enumerate(units):
        end = units[n + 1][0] if n + 1 < len(units) else len(m)
        try:
            if kind == 'entity':
                entities.append(
                    VhdlDecl(src, 'entity', x.group(1), pos, x.end()))
            elif kind == 'arch':
                archs.append(VhdlArch(src, x.group(1), x.group(2), pos, end))
        except ValueError:
            print(f'warning: {src.where(pos)}: cannot parse {x.group(0)}',
                  file=sys.stderr)
    for x in _COMP.finditer(m):
        pt = prev_token(m, x.start())
        if pt.lower() == 'end' or pt == ':':
            continue
        try:
            comps.append(
                VhdlDecl(src, 'component', x.group(1), x.start(), x.end()))
        except ValueError:
            print(f'warning: {src.where(x.start())}: cannot parse component',
                  file=sys.stderr)
    return entities, comps, archs


def find_instances(src, target, archs, entities_of):
    m = src.masked
    tname = target.name.lower()
    for x in _INST.finditer(m):
        if (x.group(2) or x.group(3)).lower() != tname:
            continue
        arch = next((a for a in archs if a.start <= x.start() < a.end), None)
        if arch is None:
            continue
        parents = entities_of(arch.entity)
        if not parents:
            print(
                f'warning: {src.where(x.start())}: entity {arch.entity} '
                f'(architecture {arch.name}) not found in the searched files',
                file=sys.stderr)

        def connect(name, kw_pos=x.start(4)):
            return _connect(src, target, name, kw_pos)

        for p in parents or [None]:
            yield x.group(1), x.start(), p, connect
            connect = (lambda name: 'already')


def _connect(src, target, name, kw_pos):
    m = src.masked
    if m[kw_pos:kw_pos + 7].lower() == 'generic':
        o = m.index('(', kw_pos)
        c = match_paren(m, o)
        inner = m[o + 1:c]
        if re.search(r'(?<![\w.])' + re.escape(name) + r'\s*=>', inner, re.I):
            return 'already'
        if '=>' in inner or not inner.strip():
            append_item(src, o, c, f'{name} => {name}', ',', '=>')
            return 'connected'
        return positional_append(src, target, name, o, c,
                                 split_top(inner, ','))
    ind = line_indent(src, kw_pos)
    if ind is None:
        src.insert(kw_pos, f'generic map ({name} => {name}) ')
    else:
        nl = src.nl
        src.insert(
            kw_pos,
            f'generic map ({nl}{ind}  {name} => {name}{nl}{ind}){nl}{ind}')
    return 'connected'
