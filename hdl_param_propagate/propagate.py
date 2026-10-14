import sys


class UserError(Exception):
    pass


def key_of(d):
    return (d.lang_family, d.name if d.lang_family == 'v' else d.name.lower())


def find_roots(design, module, lang=None, where=''):
    found = {
        'verilog': design.definitions('v', module),
        'vhdl': design.definitions('vhdl', module)
    }
    if lang:
        found = {lang: found[lang]}
    found = {k: v for k, v in found.items() if v}
    if not found:
        raise UserError(f'module/entity {module} not found in {where}')
    if len(found) > 1:
        lst = '; '.join(f'{k}: ' + ', '.join(d.where for d in v)
                        for k, v in found.items())
        raise UserError(
            f'{module} is declared in both Verilog and VHDL ({lst}); '
            f'use --lang verilog|vhdl')
    roots = next(iter(found.values()))
    if len(roots) > 1:
        print(
            f'warning: {module} is declared in several places, the parameter will be added '
            f'to all of them: ' + ', '.join(d.where for d in roots),
            file=sys.stderr)
    return roots


def _add_to_definitions(defs, spec, depth):
    propagate = True
    name = defs[0].name
    for d in defs:
        kind = d.has_param(spec.name)
        if kind == 'localparam':
            print(
                f'[{depth}] {name} ({d.where}): localparam {spec.name} already exists - '
                f'not propagating further up')
            propagate = False
        elif kind:
            print(
                f'[{depth}] {name} ({d.where}): parameter {spec.name} already exists'
            )
        else:
            d.add_param(spec)
            print(f'[{depth}] {name} ({d.where}): parameter {spec.name} added')
    return propagate


def _add_to_components(design, name, spec):
    for c in design.components(name):
        if c.has_param(spec.name):
            continue
        c.add_param(spec)
        print(f'    component {c.name} ({c.where}): generic added')


def propagate(design, roots, spec, stop_at=(), max_depth=None):
    stop = {s.lower() for s in stop_at}
    queue = [(roots, 0)]
    visited = {key_of(roots[0])}
    status = 0
    while queue:
        defs, depth = queue.pop(0)
        name = defs[0].name
        if not _add_to_definitions(defs, spec, depth) or name.lower() in stop or \
                (max_depth is not None and depth >= max_depth):
            continue
        _add_to_components(design, name, spec)
        for inst in design.instances(defs[0]):
            res = inst.connect(spec.name)
            if res == 'already' and inst.parent is None:
                continue
            pname = inst.parent.name if inst.parent else '?'
            print(
                f'    instance {inst.label} in {pname} ({inst.src.where(inst.pos)}): {res}'
            )
            if res.startswith('SKIPPED'):
                status = 2
            if inst.parent is None:
                continue
            k = key_of(inst.parent)
            if k not in visited:
                visited.add(k)
                pdefs = design.definitions(
                    *k) if k[0] == 'vhdl' else [inst.parent]
                queue.append((pdefs, depth + 1))
    return status
