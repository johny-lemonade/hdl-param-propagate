from .source import skip_ws


def _align(src, start, indent, item, align):
    if not align:
        return item
    t, m = src.text, src.masked
    le = t.find('\n', start)
    line = m[start:le if le >= 0 else len(m)]
    k = line.find(align)
    j = item.find(align)
    if k < 0 or j < 0:
        return item
    ls = t.rfind('\n', 0, start) + 1
    col_old = len((t[ls:start] + line[:k]).expandtabs())
    col_new = len((indent + item[:j]).expandtabs())
    if col_new >= col_old:
        return item
    head = item[:j].rstrip()
    return head + ' ' * (col_old - len(
        (indent + head).expandtabs())) + item[j:]


def append_item(src, open_i, close_i, item, sep, align=None):
    m, t = src.masked, src.text
    if not m[open_i + 1:close_i].strip():
        src.insert(open_i + 1, item)
        return
    last = close_i - 1
    while m[last].isspace():
        last -= 1
    start, depth = open_i + 1, 0
    for k in range(last, open_i, -1):
        c = m[k]
        if c == ')':
            depth += 1
        elif c == '(':
            depth -= 1
        elif c == sep and depth == 0:
            start = k + 1
            break
    start = skip_ws(m, start)
    ls = t.rfind('\n', 0, start) + 1
    indent = ''.join(ch if ch == '\t' else ' ' for ch in t[ls:start])
    if '\n' not in t[open_i:close_i]:
        src.insert(last + 1, f'{sep} {item}')
        return
    item = _align(src, start, indent, item, align)
    nlpos = t.find('\n', last + 1)
    if 0 <= nlpos < close_i:
        if t[nlpos - 1] == '\r':
            nlpos -= 1
        src.insert(last + 1, sep)
        src.insert(nlpos, src.nl + indent + item)
    else:
        src.insert(last + 1, sep + src.nl + indent + item)


def line_indent(src, pos):
    ls = src.text.rfind('\n', 0, pos) + 1
    pre = src.text[ls:pos]
    return pre if not pre.strip() else None


def positional_append(src, target, name, open_i, close_i, items):
    names = target.param_names()
    key = name.lower() if target.lang_family == 'vhdl' else name
    n_before = names.index(key) if key in names else len(names)
    if len(items) > n_before and key in names:
        return 'already'
    if len(items) == n_before:
        append_item(src, open_i, close_i, name, ',')
        return 'connected (positional)'
    return f'SKIPPED: positional override ({len(items)} of {n_before}) - connect manually'
