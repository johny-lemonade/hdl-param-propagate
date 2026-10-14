import textwrap

from hdl_param_propagate.convert import ParamSpec


def dedent(text):
    return textwrap.dedent(text).lstrip('\n')


def write(path, text):
    with open(str(path), 'w', newline='') as f:
        f.write(text)


def read(root, name):
    return (root / name).read_text()


def spec(name='P', lang='sv', ptype='int', default='1', **overrides):
    return ParamSpec(name, lang, ptype, default, overrides)
