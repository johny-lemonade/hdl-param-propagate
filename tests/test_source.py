import pytest

from hdl_param_propagate.source import lang_of, match_paren, prev_token, skip_ws, split_top


@pytest.mark.parametrize('path, lang', [
    ('a.sv', 'sv'),
    ('a.SVH', 'sv'),
    ('a.v', 'v'),
    ('a.vh', 'v'),
    ('a.vhd', 'vhdl'),
    ('a.vhdl', 'vhdl'),
    ('a.txt', None),
])
def test_lang_of(path, lang):
    assert lang_of(path) == lang


def test_mask_verilog_comments_and_strings(make_src):
    src = make_src('''
        a // line comment
        /* block
           comment */ b
        c = "str // not comment";
    ''')
    assert len(src.masked) == len(src.text)
    assert src.masked.count('\n') == src.text.count('\n')
    assert 'comment' not in src.masked
    assert 'str' not in src.masked
    assert '""' not in src.masked
    assert src.masked.split() == ['a', 'b', 'c', '=', '"', '";']


def test_mask_verilog_escaped_quote(make_src):
    src = make_src(r'''
        x = "a \" b"; y
    ''')
    assert src.masked.split() == ['x', '=', '"', '";', 'y']


def test_mask_vhdl_comments_strings_and_chars(make_src):
    src = make_src('''
        a <= '"'; -- comment with "quote
        b <= "x--y"; /* block */ c
        d'length
    ''',
                   name='a.vhd')
    assert 'comment' not in src.masked
    assert 'block' not in src.masked
    assert 'x--y' not in src.masked
    assert "d'length" in src.masked
    assert src.masked.split()[-2:] == ['c', "d'length"]


def test_source_insert_and_result(make_src):
    src = make_src('abcdef')
    src.insert(3, 'X')
    src.insert(1, 'Y')
    src.insert(3, 'Z')
    assert src.result() == 'aYbcXZdef'
    assert src.text == 'abcdef'


def test_source_lines_and_where(make_src):
    src = make_src('l1\nl2\nl3\n')
    assert src.line(0) == 1
    assert src.line(3) == 2
    assert src.line(6) == 3
    assert src.where(3).endswith('a.sv:2')


def test_source_newline_style(make_src):
    assert make_src('a\r\nb\r\n').nl == '\r\n'
    assert make_src('a\nb\n').nl == '\n'


def test_skip_ws():
    assert skip_ws('a  \n\tb', 1) == 5
    assert skip_ws('a   ', 1) == 4


def test_match_paren():
    s = 'f(a, (b), g(c(d)))x'
    assert match_paren(s, 1) == len(s) - 2
    assert match_paren(s, 5) == 7


def test_match_paren_unbalanced():
    with pytest.raises(ValueError):
        match_paren('(a, (b)', 0)


@pytest.mark.parametrize('text, pos, token', [
    ('module foo', 7, 'module'),
    ('  x  :  y', 8, ':'),
    ('a$b  c', 5, 'a$b'),
    ('   x', 3, ''),
])
def test_prev_token(text, pos, token):
    assert prev_token(text, pos) == token


def test_split_top():
    assert split_top('a, f(b, c), [d, e], {g, h}', ',') == \
        ['a', ' f(b, c)', ' [d, e]', ' {g, h}']
    assert split_top('A : integer := 1; B : string', ';') == \
        ['A : integer := 1', ' B : string']
    assert split_top('', ',') == ['']
