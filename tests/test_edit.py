from hdl_param_propagate.edit import append_item, line_indent, positional_append
from helpers import dedent


def _list(src, start_text):
    o = src.text.index(start_text) + len(start_text) - 1
    c = src.text.index(')', o)
    while src.masked.count('(', o, c + 1) != src.masked.count(')', o, c + 1):
        c = src.text.index(')', c + 1)
    return o, c


def test_append_to_empty_list(make_src):
    src = make_src('m #() u ();')
    o, c = _list(src, '#(')
    append_item(src, o, c, '.P(P)', ',')
    assert src.result() == 'm #(.P(P)) u ();'


def test_append_single_line(make_src):
    src = make_src('m #(.A(1), .B(2)) u ();')
    o, c = _list(src, '#(')
    append_item(src, o, c, '.P(P)', ',', '(')
    assert src.result() == 'm #(.A(1), .B(2), .P(P)) u ();'


def test_append_multiline_keeps_trailing_comment(make_src):
    src = make_src('''
        #(
            parameter A = 1,  // a
            parameter B = 2   // b
        )
    ''')
    o, c = _list(src, '#(')
    append_item(src, o, c, 'parameter P = 3', ',')
    assert src.result() == dedent('''
        #(
            parameter A = 1,  // a
            parameter B = 2,   // b
            parameter P = 3
        )
    ''')


def test_append_multiline_paren_on_last_line(make_src):
    src = make_src('''
        generic map (
           A => 1,
           B => 2)
    ''',
                   name='a.vhd')
    o, c = _list(src, 'map (')
    append_item(src, o, c, 'P => P', ',')
    assert src.result() == dedent('''
        generic map (
           A => 1,
           B => 2,
           P => P)
    ''')


def test_append_aligned_to_first_item_column(make_src):
    src = make_src('''
        #(    parameter A = 1,
              parameter B = 2
        )
    ''')
    o, c = _list(src, '#(')
    append_item(src, o, c, 'parameter P = 3', ',')
    assert src.result().splitlines()[2] == '      parameter P = 3'


def test_append_aligns_token_column(make_src):
    src = make_src('''
        generic (
          C_LONG_NAME : integer := 1
        );
    ''',
                   name='a.vhd')
    o, c = _list(src, 'generic (')
    append_item(src, o, c, 'P : integer := 2', ';', ':')
    assert src.result().splitlines()[2] == '  P           : integer := 2'


def test_append_no_alignment_when_new_item_is_longer(make_src):
    src = make_src('''
        generic (
          A : integer := 1
        );
    ''',
                   name='a.vhd')
    o, c = _list(src, 'generic (')
    append_item(src, o, c, 'LONG_NAME : integer := 2', ';', ':')
    assert src.result().splitlines()[2] == '  LONG_NAME : integer := 2'


def test_append_crlf(make_src):
    src = make_src('#(\r\n    .A(1)\r\n)\r\n')
    o, c = _list(src, '#(')
    append_item(src, o, c, '.P(P)', ',')
    assert src.result() == '#(\r\n    .A(1),\r\n    .P(P)\r\n)\r\n'


def test_line_indent(make_src):
    src = make_src('    port map (\nx port map')
    assert line_indent(src, 4) == '    '
    assert line_indent(src, src.text.index('port map', 5)) is None


class _Target:
    lang_family = 'v'

    def __init__(self, names):
        self._names = names

    def param_names(self):
        return self._names


def test_positional_append_all_given(make_src):
    src = make_src('m #(3, 4) u ();')
    o, c = _list(src, '#(')
    res = positional_append(src, _Target(['A', 'B']), 'P', o, c, ['3', '4'])
    assert res == 'connected (positional)'
    assert src.result() == 'm #(3, 4, P) u ();'


def test_positional_append_incomplete(make_src):
    src = make_src('m #(3) u ();')
    o, c = _list(src, '#(')
    res = positional_append(src, _Target(['A', 'B']), 'P', o, c, ['3'])
    assert res.startswith('SKIPPED')
    assert src.edits == []


def test_positional_append_already_connected(make_src):
    src = make_src('m #(3, 4, P) u ();')
    o, c = _list(src, '#(')
    res = positional_append(src, _Target(['A', 'B', 'P']), 'P', o, c,
                            ['3', '4', 'P'])
    assert res == 'already'
    assert src.edits == []
