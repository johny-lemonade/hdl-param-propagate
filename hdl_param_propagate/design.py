import os

from . import verilog, vhdl
from .source import ALL_EXT, Source


def collect_files(dirs):
    files = []
    seen = set()
    for d in dirs:
        for root, dnames, fnames in os.walk(d):
            dnames[:] = sorted(x for x in dnames if not x.startswith('.'))
            for fn in sorted(fnames):
                p = os.path.join(root, fn)
                if os.path.splitext(fn)[1].lower() in ALL_EXT:
                    rp = os.path.realpath(p)
                    if rp not in seen:
                        seen.add(rp)
                        files.append(os.path.normpath(p))
    return files


class Instance:

    def __init__(self, src, label, pos, parent, connect):
        self.src, self.label, self.pos, self.parent, self.connect = src, label, pos, parent, connect


class Design:

    def __init__(self, files):
        self.sources = []
        self.vmods, self.entities, self.comps, self.archs = [], [], [], []
        for f in files:
            src = Source(f)
            self.sources.append(src)
            if src.is_vhdl:
                e, c, a = vhdl.parse(src)
                self.entities += e
                self.comps += c
                self.archs += a
            else:
                self.vmods += verilog.parse(src)

    def definitions(self, family, name):
        if family == 'v':
            return [d for d in self.vmods if d.name == name]
        return [d for d in self.entities if d.name.lower() == name.lower()]

    def components(self, name):
        return [c for c in self.comps if c.name.lower() == name.lower()]

    def instances(self, target):
        res = []
        for src in self.sources:
            if src.is_vhdl:
                archs = [a for a in self.archs if a.src is src]
                found = vhdl.find_instances(
                    src, target, archs, lambda n: self.definitions('vhdl', n))
            else:
                mods = [d for d in self.vmods if d.src is src]
                found = verilog.find_instances(src, target, mods)
            res += [Instance(src, *f) for f in found]
        return res

    def changed_sources(self):
        return [s for s in self.sources if s.edits]
