from hdl_param_propagate import verilog
from helpers import dedent, spec


def _mod(src, name):
    return next(m for m in verilog.parse(src) if m.name == name)


def _instances(src, target_name, target_src=None):
    mods = verilog.parse(src)
    target = _mod(target_src or src, target_name)
    return list(verilog.find_instances(src, target, mods))


def test_parse_modules(make_src):
    src = make_src('''
        module a; endmodule
        macromodule b (input x); endmodule : b
        interface c; endinterface
        program automatic d; endprogram
        class e; virtual interface c vif; endclass
    ''')
    assert [m.name for m in verilog.parse(src)] == ['a', 'b', 'c', 'd']


def test_parse_header_variants(make_src):
    src = make_src('''
        module plain (input a);
        endmodule
        module with_params #(parameter A = 1, B = 2) (input a);
        endmodule
        module with_import import pkg::*; #(parameter A = 1) (input a);
        endmodule
        module body_params (a);
            input a;
            parameter A = 1, B = 2;
            localparam L = 3;
        endmodule
        module no_ports;
        endmodule
    ''')
    assert _mod(src, 'plain').param_open is None
    assert _mod(src, 'with_params').param_names() == ['A', 'B']
    assert _mod(src, 'with_import').param_names() == ['A']
    assert _mod(src, 'body_params').param_names() == ['A', 'B']
    assert _mod(src, 'no_ports').port_open is None


def test_has_param(make_src):
    src = make_src('''
        module m #(parameter int A = 1, parameter [7:0] B = 8'h0) ();
            localparam L = A == 1;
        endmodule
    ''')
    m = _mod(src, 'm')
    assert m.has_param('A') == 'parameter'
    assert m.has_param('B') == 'parameter'
    assert m.has_param('L') == 'localparam'
    assert m.has_param('X') is None


def test_add_param_to_existing_list(make_src):
    src = make_src('''
        module m #(
            parameter int A = 1
        ) (input logic clk);
        endmodule
    ''')
    _mod(src, 'm').add_param(spec(default='5'))
    assert src.result() == dedent('''
        module m #(
            parameter int A = 1,
            parameter int P = 5
        ) (input logic clk);
        endmodule
    ''')


def test_add_param_creates_list(make_src):
    src = make_src('''
        module m
        (
            input logic clk
        );
        endmodule
    ''')
    _mod(src, 'm').add_param(spec(default='5'))
    assert src.result() == dedent('''
        module m #(
            parameter int P = 5
        )
        (
            input logic clk
        );
        endmodule
    ''')


def test_add_param_to_module_without_ports(make_src):
    src = make_src('module m; endmodule\n')
    _mod(src, 'm').add_param(spec(default='5'))
    assert src.result(
    ) == 'module m #(\n    parameter int P = 5\n); endmodule\n'


def test_add_param_to_body_when_no_header_list(make_src):
    src = make_src('''
        module m (input clk);
            parameter W = 8;
        endmodule
    ''')
    _mod(src, 'm').add_param(spec(default='5'))
    assert src.result() == dedent('''
        module m (input clk);
            parameter int P = 5;
            parameter W = 8;
        endmodule
    ''')


def test_add_param_uses_verilog2001_types_in_v_files(make_src):
    src = make_src('module m (input clk); endmodule\n', name='m.v')
    _mod(src, 'm').add_param(spec(ptype='logic [3:0]', default="4'h1"))
    assert "parameter [3:0] P = 4'h1" in src.result()


def test_find_instance_variants(make_src):
    src = make_src('''
        module leaf #(parameter A = 1) (input clk); endmodule
        module top (input clk);
            leaf u0 (.clk(clk));
            leaf #() u1 (.clk(clk));
            leaf #(.A(2)) u2 (.clk(clk));
            leaf #(2) u3 (.clk(clk));
            leaf #2 u4 (.clk(clk));
            leaf u5 [3:0] (.clk(clk));
            leaf u6 (.clk(clk)), u7 (.clk(clk));
        endmodule
    ''')
    found = _instances(src, 'leaf')
    assert [label for label, *_ in found
            ] == ['u0', 'u1', 'u2', 'u3', 'u4', 'u5', 'u6']
    assert {parent.name for _, _, parent, _ in found} == {'top'}


def test_find_instances_ignores_comments_strings_and_declarations(make_src):
    src = make_src('''
        module leaf (input clk); endmodule : leaf
        // leaf c1 (.clk(clk));
        /* leaf c2 (.clk(clk)); */
        module top (input clk);
            initial $display("leaf s1 (.clk(clk));");
            leaf real_inst (.clk(clk));
            leaf_other x (.clk(clk));
            my_leaf y (.clk(clk));
        endmodule
    ''')
    assert [label for label, *_ in _instances(src, 'leaf')] == ['real_inst']


def test_find_instance_outside_module_is_skipped(make_src, capsys):
    src = make_src('''
        module leaf (input clk); endmodule
        leaf orphan (.clk(clk));
    ''')
    assert _instances(src, 'leaf') == []
    assert 'outside of any module' in capsys.readouterr().err


def _connect_all(src, name='P'):
    return [connect(name) for *_, connect in _instances(src, 'leaf')]


def test_connect_variants(make_src):
    src = make_src('''
        module leaf #(parameter A = 1) (input clk); endmodule
        module top (input clk);
            leaf u0 (.clk(clk));
            leaf #() u1 (.clk(clk));
            leaf #(.A(2)) u2 (.clk(clk));
            leaf #(2) u3 (.clk(clk));
            leaf #2 u4 (.clk(clk));
            leaf #(.A(2), .P(P)) u5 (.clk(clk));
        endmodule
    ''')
    assert _connect_all(src) == [
        'connected', 'connected', 'connected', 'connected (positional)',
        'connected (positional)', 'already'
    ]
    assert src.result().splitlines()[2:8] == [
        '    leaf #(.P(P)) u0 (.clk(clk));',
        '    leaf #(.P(P)) u1 (.clk(clk));',
        '    leaf #(.A(2), .P(P)) u2 (.clk(clk));',
        '    leaf #(2, P) u3 (.clk(clk));',
        '    leaf #(2, P) u4 (.clk(clk));',
        '    leaf #(.A(2), .P(P)) u5 (.clk(clk));',
    ]


def test_connect_skips_incomplete_positional(make_src):
    src = make_src('''
        module leaf #(parameter A = 1, B = 2) (input clk); endmodule
        module top (input clk);
            leaf #(1) u0 (.clk(clk));
            leaf #1 u1 (.clk(clk));
        endmodule
    ''')
    assert [r.split(':')[0]
            for r in _connect_all(src)] == ['SKIPPED', 'SKIPPED']
    assert src.edits == []


def test_vhdl_target_is_matched_case_insensitively(make_src):
    vh = make_src('''
        entity Leaf is port (clk : in bit); end;
    ''',
                  name='leaf.vhd')
    from hdl_param_propagate import vhdl
    target = vhdl.parse(vh)[0][0]
    src = make_src('''
        module top (input clk);
            LEAF u0 (.clk(clk));
        endmodule
    ''')
    found = list(verilog.find_instances(src, target, verilog.parse(src)))
    assert [label for label, *_ in found] == ['u0']
