import pytest

from hdl_param_propagate.convert import (ConvError, parse_sv_type,
                                         parse_sv_value, parse_vhdl_type,
                                         parse_vhdl_value, vec_width)
from helpers import spec


@pytest.mark.parametrize('text, kind', [
    ('', 'none'),
    ('int', 'int'),
    ('integer', 'int'),
    ('int unsigned', 'int'),
    ('string', 'string'),
    ('real', 'real'),
    ('bit', 'bit'),
    ('logic', 'bit'),
    ('logic [7:0]', 'vec'),
    ('bit [1:0]', 'vec'),
    ('[W-1:0]', 'vec'),
    ('my_pkg::cfg_t', 'raw'),
])
def test_parse_sv_type_kind(text, kind):
    assert parse_sv_type(text)['kind'] == kind


def test_parse_sv_type_vector():
    pt = parse_sv_type('logic signed [ W-1 : 0 ]')
    assert pt == {'kind': 'vec', 'left': 'W-1', 'right': '0', 'signed': True}


@pytest.mark.parametrize('text, kind', [
    ('integer', 'int'),
    ('natural', 'int'),
    ('integer range 0 to 7', 'int'),
    ('BOOLEAN', 'bool'),
    ('std_logic', 'bit'),
    ('std_logic_vector(7 downto 0)', 'vec'),
    ('unsigned (0 to 3)', 'vec'),
    ('string', 'string'),
    ('time', 'raw'),
])
def test_parse_vhdl_type_kind(text, kind):
    assert parse_vhdl_type(text)['kind'] == kind


def test_vec_width():
    assert vec_width(parse_vhdl_type('std_logic_vector(7 downto 0)')) == 8
    assert vec_width(parse_vhdl_type('std_logic_vector(0 to 3)')) == 4
    assert vec_width(parse_sv_type('logic [W-1:0]')) is None
    assert vec_width(parse_sv_type('int')) is None


@pytest.mark.parametrize('text, value', [
    ('16', ('int', 16)),
    ('1_000', ('int', 1000)),
    ("8'hA5", ('bits', 0xA5, 8)),
    ("'b101", ('bits', 5, None)),
    ("4'sd3", ('bits', 3, 4)),
    ("'0", ('fill', '0')),
    ('"abc"', ('str', 'abc')),
    ('1.5', ('real', '1.5')),
    ('W*2', ('raw', 'W*2')),
])
def test_parse_sv_value(text, value):
    assert parse_sv_value(text) == value


@pytest.mark.parametrize('text, ptype, value', [
    ('TRUE', 'boolean', ('bool', True)),
    ("'1'", 'std_logic', ('bits', 1, 1)),
    ('"0101"', 'std_logic_vector(3 downto 0)', ('bits', 5, 4)),
    ('"0101"', 'string', ('str', '0101')),
    ('x"A5"', 'std_logic_vector(7 downto 0)', ('bits', 0xA5, 8)),
    ("(others => '1')", 'std_logic_vector(7 downto 0)', ('fill', '1')),
    ('16#FF#', 'integer', ('int', 255)),
    ('42', 'integer', ('int', 42)),
    ('1 ns', 'time', ('raw', '1 ns')),
])
def test_parse_vhdl_value(text, ptype, value):
    assert parse_vhdl_value(text, parse_vhdl_type(ptype)) == value


@pytest.mark.parametrize('ptype, default, vhdl', [
    ('int', '16', 'P : integer := 16'),
    ('bit [1:0]', "2'b10", 'P : std_logic_vector(1 downto 0) := "10"'),
    ('logic [7:0]', "8'hA5", 'P : std_logic_vector(7 downto 0) := "10100101"'),
    ('logic [7:0]', "'0",
     "P : std_logic_vector(7 downto 0) := (others => '0')"),
    ('logic [0:3]', "4'b0011", 'P : std_logic_vector(0 to 3) := "0011"'),
    ('logic signed [3:0]', '0', "P : signed(3 downto 0) := (others => '0')"),
    ('bit', "1'b1", "P : std_logic := '1'"),
    ('string', '"abc"', 'P : string := "abc"'),
    ('real', '1.5', 'P : real := 1.5'),
    ('', '7', 'P : integer := 7'),
    ('', "8'd7", 'P : std_logic_vector(7 downto 0) := "00000111"'),
])
def test_sv_to_vhdl(ptype, default, vhdl):
    assert spec(ptype=ptype, default=default).vhdl_decl() == vhdl


@pytest.mark.parametrize('ptype, default, sv, v', [
    ('natural', '8', 'parameter int P = 8', 'parameter integer P = 8'),
    ('boolean', 'true', "parameter bit P = 1'b1", "parameter P = 1'b1"),
    ('std_logic', "'0'", "parameter logic P = 1'b0", "parameter P = 1'b0"),
    ('std_logic_vector(7 downto 0)', 'x"A5"',
     "parameter logic [7:0] P = 8'b10100101",
     "parameter [7:0] P = 8'b10100101"),
    ('std_logic_vector(11 downto 0)', 'x"ABC"',
     "parameter logic [11:0] P = 12'hABC", "parameter [11:0] P = 12'hABC"),
    ('std_logic_vector(3 downto 0)', "(others => '0')",
     "parameter logic [3:0] P = '0", 'parameter [3:0] P = 0'),
    ('std_logic_vector(3 downto 0)', "(others => '1')",
     "parameter logic [3:0] P = '1", "parameter [3:0] P = {4{1'b1}}"),
    ('integer', '16#FF#', 'parameter int P = 255',
     'parameter integer P = 255'),
    ('string', '"abc"', 'parameter string P = "abc"', 'parameter P = "abc"'),
])
def test_vhdl_to_verilog(ptype, default, sv, v):
    s = spec(lang='vhdl', ptype=ptype, default=default)
    assert s.verilog_decl('sv') == sv
    assert s.verilog_decl('v') == v


def test_same_language_is_verbatim():
    assert spec(ptype='my_pkg::cfg_t', default="'{default: 0}").verilog_decl('sv') == \
        "parameter my_pkg::cfg_t P = '{default: 0}"
    assert spec(lang='vhdl', ptype='time', default='1 ns').vhdl_decl() == \
        'P : time := 1 ns'


def test_sv_types_downgraded_for_plain_verilog():
    assert spec(ptype='int',
                default='4').verilog_decl('v') == 'parameter integer P = 4'
    assert spec(ptype='logic [7:0]', default="8'h0").verilog_decl('v') == \
        "parameter [7:0] P = 8'h0"
    assert spec(ptype='', default='4').verilog_decl('v') == 'parameter P = 4'
    assert spec(lang='v', ptype='integer', default='4').verilog_decl('sv') == \
        'parameter integer P = 4'


def test_untranslatable_type_raises():
    with pytest.raises(ConvError, match='--sv-type/--sv-default'):
        spec(lang='vhdl', ptype='time', default='1 ns').verilog_decl('sv')
    with pytest.raises(ConvError, match='--vhdl-type/--vhdl-default'):
        spec(ptype='my_pkg::cfg_t', default='0').vhdl_decl()


def test_untranslatable_value_raises():
    with pytest.raises(ConvError):
        spec(ptype='int', default='W*2').vhdl_decl()


def test_overrides():
    s = spec(lang='vhdl',
             ptype='time',
             default='1 ns',
             sv_type='realtime',
             sv_default='1.0')
    assert s.verilog_decl('sv') == 'parameter realtime P = 1.0'
    s = spec(ptype='int', default='W*2', vhdl_default='2 * W')
    assert s.vhdl_decl() == 'P : integer := 2 * W'
