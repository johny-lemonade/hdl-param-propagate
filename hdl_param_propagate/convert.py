import re


class ConvError(Exception):
    pass


def _num(s):
    try:
        return int(str(s).replace('_', ''))
    except ValueError:
        return None


def parse_sv_type(t):
    s = ' '.join(t.split())
    if s.lower() in ('', '-', 'none', 'untyped'):
        return {'kind': 'none'}
    if re.fullmatch(r'(int|integer|shortint|longint|byte)( (un)?signed)?', s):
        return {'kind': 'int'}
    if s == 'string':
        return {'kind': 'string'}
    if s in ('real', 'shortreal', 'realtime'):
        return {'kind': 'real'}
    m = re.fullmatch(
        r'(?:(logic|bit|reg)\s*)?(?:(signed|unsigned)\s*)?'
        r'(?:\[\s*([^:\]]+?)\s*:\s*([^\]]+?)\s*\])?', s)
    if m and (m.group(1) or m.group(3)):
        if m.group(3):
            return {
                'kind': 'vec',
                'left': m.group(3),
                'right': m.group(4),
                'signed': m.group(2) == 'signed'
            }
        return {'kind': 'bit'}
    return {'kind': 'raw'}


def parse_vhdl_type(t):
    s = ' '.join(t.split())
    low = s.lower()
    if re.fullmatch(r'(integer|natural|positive)( range .*)?', low):
        return {'kind': 'int'}
    if low == 'boolean':
        return {'kind': 'bool'}
    if low in ('std_logic', 'std_ulogic', 'bit'):
        return {'kind': 'bit'}
    if low == 'string':
        return {'kind': 'string'}
    if low == 'real':
        return {'kind': 'real'}
    m = re.fullmatch(
        r'(std_logic_vector|std_ulogic_vector|bit_vector|unsigned|signed)'
        r'\s*\(\s*(.+?)\s+(downto|to)\s+(.+?)\s*\)', s, re.I)
    if m:
        return {
            'kind': 'vec',
            'left': m.group(2),
            'right': m.group(4),
            'signed': m.group(1).lower() == 'signed'
        }
    return {'kind': 'raw'}


def vec_width(pt):
    if pt.get('kind') != 'vec':
        return None
    left, right = _num(pt['left']), _num(pt['right'])
    if left is None or right is None:
        return None
    return abs(left - right) + 1


def parse_sv_value(v):
    s = v.strip()
    if re.fullmatch(r'"(?:\\.|[^"\\])*"', s):
        return ('str', s[1:-1])
    m = re.fullmatch(r"'([01])", s)
    if m:
        return ('fill', m.group(1))
    m = re.fullmatch(r"(\d+)?\s*'\s*[sS]?([bBoOdDhH])\s*([0-9a-fA-F_]+)", s)
    if m:
        base = {'b': 2, 'o': 8, 'd': 10, 'h': 16}[m.group(2).lower()]
        return ('bits', int(m.group(3).replace('_', ''),
                            base), int(m.group(1)) if m.group(1) else None)
    if re.fullmatch(r'[+-]?\d[\d_]*', s):
        return ('int', _num(s))
    if re.fullmatch(r'[+-]?\d[\d_]*(\.\d[\d_]*)?([eE][+-]?\d+)?', s):
        return ('real', s)
    return ('raw', s)


def parse_vhdl_value(v, pt):
    s = v.strip()
    low = s.lower()
    if low in ('true', 'false'):
        return ('bool', low == 'true')
    m = re.fullmatch(r"'([01])'", s)
    if m:
        return ('bits', int(m.group(1)), 1)
    m = re.fullmatch(r'"([01_]*)"', s)
    if m and pt['kind'] in ('vec', 'bit'):
        d = m.group(1).replace('_', '')
        return ('bits', int(d or '0', 2), len(d))
    m = re.fullmatch(r'([bBoOxX])"([0-9a-fA-F_]+)"', s)
    if m:
        base = {'b': 2, 'o': 8, 'x': 16}[m.group(1).lower()]
        d = m.group(2).replace('_', '')
        return ('bits', int(d, base), len(d) * {2: 1, 8: 3, 16: 4}[base])
    m = re.fullmatch(r'"((?:""|[^"])*)"', s)
    if m:
        return ('str', m.group(1).replace('""', '\\"'))
    m = re.fullmatch(r"\(\s*others\s*=>\s*'([01])'\s*\)", low)
    if m:
        return ('fill', m.group(1))
    m = re.fullmatch(r'(\d+)#([0-9a-fA-F_]+)#', s)
    if m:
        return ('int', int(m.group(2).replace('_', ''), int(m.group(1))))
    if re.fullmatch(r'[+-]?\d[\d_]*', s):
        return ('int', _num(s))
    if re.fullmatch(r'[+-]?\d[\d_]*\.\d[\d_]*([eE][+-]?\d+)?', s):
        return ('real', s)
    return ('raw', s)


def _sv_sized(n, w):
    if n < 0:
        return str(n)
    if w is None:
        return f"'h{n:X}"
    if w <= 8:
        return f"{w}'b{n:0{w}b}"
    return f"{w}'h{n:0{(w + 3) // 4}X}"


def sv_type_text(pt, flavor):
    k = pt['kind']
    sv = flavor == 'sv'
    if k == 'none':
        return ''
    if k == 'int':
        return 'int' if sv else 'integer'
    if k in ('bool', 'bit'):
        return ('bit' if k == 'bool' else 'logic') if sv else ''
    if k == 'vec':
        rng = f"{'signed ' if pt['signed'] else ''}[{pt['left']}:{pt['right']}]"
        return f'logic {rng}' if sv else rng
    if k == 'string':
        return 'string' if sv else ''
    if k == 'real':
        return 'real'
    raise ConvError('type cannot be translated to Verilog')


def sv_value_text(pt, val, flavor='sv'):
    k, a = val[0], val[1:]
    tk = pt['kind']
    if k == 'raw':
        raise ConvError(f'value "{a[0]}" cannot be translated to Verilog')
    if k == 'str':
        return f'"{a[0]}"'
    if k == 'real':
        return a[0]
    if k == 'fill':
        if tk == 'int':
            return '0' if a[0] == '0' else '-1'
        if flavor == 'sv':
            return "'" + a[0]
        if a[0] == '0':
            return '0'
        w = vec_width(pt) or 1
        return f"{{{w}{{1'b1}}}}"
    if k == 'bool':
        n = int(a[0])
        return str(n) if tk in ('int', 'none') else f"1'b{n}"
    n = a[0]
    w = a[1] if k == 'bits' else None
    if tk == 'bit' or tk == 'bool':
        return f"1'b{n & 1}"
    if tk == 'vec':
        return _sv_sized(n, vec_width(pt) or w)
    if tk == 'none' and k == 'bits':
        return _sv_sized(n, w)
    return str(n)


def vhdl_type_text(pt, val):
    k = pt['kind']
    if k == 'none':
        vk = val[0]
        if vk in ('int', 'fill'):
            return 'integer'
        if vk == 'bits':
            return f'std_logic_vector({val[2] - 1} downto 0)' if val[
                2] else 'integer'
        if vk == 'bool':
            return 'boolean'
        if vk == 'str':
            return 'string'
        if vk == 'real':
            return 'real'
        raise ConvError('cannot infer a VHDL type')
    if k == 'int':
        return 'integer'
    if k == 'bool':
        return 'boolean'
    if k == 'bit':
        return 'std_logic'
    if k == 'vec':
        left, right = _num(pt['left']), _num(pt['right'])
        d = 'to' if left is not None and right is not None and left < right else 'downto'
        base = 'signed' if pt['signed'] else 'std_logic_vector'
        return f"{base}({pt['left']} {d} {pt['right']})"
    if k == 'string':
        return 'string'
    if k == 'real':
        return 'real'
    raise ConvError('type cannot be translated to VHDL')


def _vhdl_vec(n, w):
    if n == 0:
        return "(others => '0')"
    if w and 0 <= n < (1 << w):
        return '"' + format(n, f'0{w}b') + '"'
    raise ConvError('cannot translate the value to a VHDL vector')


def vhdl_value_text(pt, val):
    k, a = val[0], val[1:]
    tk = pt['kind']
    if k == 'raw':
        raise ConvError(f'value "{a[0]}" cannot be translated to VHDL')
    if k == 'str':
        return '"' + a[0].replace('\\"', '""') + '"'
    if k == 'real':
        return a[0]
    if tk == 'none' and k == 'bits':
        tk, pt = 'vec', {
            'kind': 'vec',
            'left': str((a[1] or 32) - 1),
            'right': '0'
        }
    if k == 'fill':
        if tk == 'vec':
            return f"(others => '{a[0]}')"
        if tk == 'bit':
            return f"'{a[0]}'"
        if tk == 'bool':
            return 'true' if a[0] == '1' else 'false'
        return '0' if a[0] == '0' else '-1'
    n = int(a[0])
    if tk == 'bool':
        return 'true' if n else 'false'
    if tk == 'bit':
        return f"'{n & 1}'"
    if tk == 'vec':
        return _vhdl_vec(n, vec_width(pt) or (a[1] if k == 'bits' else None))
    return str(n)


class ParamSpec:

    def __init__(self, name, lang, ptype, default, overrides):
        self.name = name
        self.lang = lang
        self.ptype, self.default = ptype, default
        self.ov = overrides
        if lang == 'vhdl':
            self.pt = parse_vhdl_type(ptype)
            self.val = parse_vhdl_value(default, self.pt)
        else:
            self.pt = parse_sv_type(ptype)
            self.val = parse_sv_value(default)

    def _err(self, target, e):
        opt = '--vhdl-type/--vhdl-default' if target == 'vhdl' else '--sv-type/--sv-default'
        raise ConvError(
            f'parameter {self.name}: {e}; specify {opt} explicitly')

    def verilog_decl(self, flavor):
        try:
            if self.ov.get('sv_type') is not None:
                t = self.ov['sv_type']
            elif flavor == 'sv' and self.lang in ('sv', 'v'):
                t = self.ptype.strip()
            elif self.lang in ('sv', 'v') and self.pt['kind'] == 'raw':
                t = self.ptype.strip()
            else:
                t = sv_type_text(self.pt, flavor)
            if self.ov.get('sv_default') is not None:
                v = self.ov['sv_default']
            elif self.lang in ('sv', 'v'):
                v = self.default.strip()
            else:
                v = sv_value_text(self.pt, self.val, flavor)
        except ConvError as e:
            self._err('sv', e)
        return f"parameter {t + ' ' if t else ''}{self.name} = {v}"

    def vhdl_decl(self):
        try:
            if self.ov.get('vhdl_type') is not None:
                t = self.ov['vhdl_type']
            elif self.lang == 'vhdl':
                t = self.ptype.strip()
            else:
                t = vhdl_type_text(self.pt, self.val)
            if self.ov.get('vhdl_default') is not None:
                v = self.ov['vhdl_default']
            elif self.lang == 'vhdl':
                v = self.default.strip()
            else:
                v = vhdl_value_text(self.pt, self.val)
        except ConvError as e:
            self._err('vhdl', e)
        return f'{self.name} : {t} := {v}'
