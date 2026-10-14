import pytest

from hdl_param_propagate.cli import main
from hdl_param_propagate.propagate import UserError
from helpers import dedent, read

FIFO = '''
    module fifo #(
        parameter int WIDTH = 8
    ) (
        input  logic clk
    );
    endmodule
'''

CORE = '''
    module core (
        input logic clk
    );
        fifo #(.WIDTH(8)) u_fifo (.clk(clk));
    endmodule
'''

TOP = '''
    library ieee;
    use ieee.std_logic_1164.all;

    entity top is
      generic (
        G_MODE : integer := 0
      );
      port (clk : in std_logic);
    end entity top;

    architecture rtl of top is
      component core is
        port (clk : in std_logic);
      end component;
    begin
      u_core : core
        port map (
          clk => clk
        );
    end architecture rtl;
'''

TB = '''
    module tb;
        logic clk;
        top dut (.clk(clk));
    endmodule
'''

MIXED = {
    'rtl/fifo.sv': FIFO,
    'rtl/core.sv': CORE,
    'rtl/top.vhd': TOP,
    'tb/tb.sv': TB
}


def test_mixed_hierarchy(project, add_param, capsys):
    root = project(MIXED)
    assert add_param(root, 'fifo', 'DEPTH', 'int', '16') == 0

    assert read(root, 'rtl/fifo.sv') == dedent('''
        module fifo #(
            parameter int WIDTH = 8,
            parameter int DEPTH = 16
        ) (
            input  logic clk
        );
        endmodule
    ''')
    assert read(root, 'rtl/core.sv') == dedent('''
        module core #(
            parameter int DEPTH = 16
        ) (
            input logic clk
        );
            fifo #(.WIDTH(8), .DEPTH(DEPTH)) u_fifo (.clk(clk));
        endmodule
    ''')
    assert read(root, 'rtl/top.vhd') == dedent('''
        library ieee;
        use ieee.std_logic_1164.all;

        entity top is
          generic (
            G_MODE : integer := 0;
            DEPTH  : integer := 16
          );
          port (clk : in std_logic);
        end entity top;

        architecture rtl of top is
          component core is
            generic (
              DEPTH : integer := 16
            );
            port (clk : in std_logic);
          end component;
        begin
          u_core : core
            generic map (
              DEPTH => DEPTH
            )
            port map (
              clk => clk
            );
        end architecture rtl;
    ''')
    assert read(root, 'tb/tb.sv') == dedent('''
        module tb #(
            parameter int DEPTH = 16
        );
            logic clk;
            top #(.DEPTH(DEPTH)) dut (.clk(clk));
        endmodule
    ''')
    out = capsys.readouterr().out
    assert '[0] fifo' in out and '[3] tb' in out
    assert 'component core' in out


def test_rerun_is_idempotent(project, add_param, capsys):
    root = project(MIXED)
    add_param(root, 'fifo', 'DEPTH', 'int', '16')
    files = {name: read(root, name) for name in MIXED}
    capsys.readouterr()
    assert add_param(root, 'fifo', 'DEPTH', 'int', '16') == 0
    assert {name: read(root, name) for name in MIXED} == files
    out = capsys.readouterr().out
    assert 'added' not in out and 'connected' not in out
    assert 'Files modified: none' in out


def test_vhdl_root(project, add_param):
    root = project(MIXED)
    add_param(root, 'top', 'G_EN', 'boolean', 'true')
    assert '    G_EN   : boolean := true\n' in read(root, 'rtl/top.vhd')
    assert "parameter bit G_EN = 1'b1" in read(root, 'tb/tb.sv')
    assert 'top #(.G_EN(G_EN)) dut' in read(root, 'tb/tb.sv')


def test_vector_parameter(project, add_param):
    root = project(MIXED)
    add_param(root, 'fifo', 'MASK', 'bit [1:0]', "2'b10")
    assert "parameter bit [1:0] MASK = 2'b10" in read(root, 'rtl/core.sv')
    assert 'MASK   : std_logic_vector(1 downto 0) := "10"' in read(
        root, 'rtl/top.vhd')


def test_stop_at(project, add_param):
    root = project(MIXED)
    add_param(root, 'fifo', 'DEPTH', 'int', '16', '--stop-at', 'core')
    assert 'parameter int DEPTH = 16' in read(root, 'rtl/core.sv')
    assert 'DEPTH' not in read(root, 'rtl/top.vhd')
    assert 'DEPTH' not in read(root, 'tb/tb.sv')


@pytest.mark.parametrize('depth, changed', [
    ('0', ['rtl/fifo.sv']),
    ('1', ['rtl/fifo.sv', 'rtl/core.sv']),
    ('2', ['rtl/fifo.sv', 'rtl/core.sv', 'rtl/top.vhd']),
])
def test_max_depth(project, add_param, depth, changed):
    root = project(MIXED)
    add_param(root, 'fifo', 'DEPTH', 'int', '16', '--max-depth', depth)
    assert [n for n in MIXED if 'DEPTH' in read(root, n)] == changed


def test_dry_run_does_not_modify(project, add_param, capsys):
    root = project(MIXED)
    add_param(root, 'fifo', 'DEPTH', 'int', '16', '--dry-run')
    for name, text in MIXED.items():
        assert read(root, name) == dedent(text)
    out = capsys.readouterr().out
    assert '+    parameter int DEPTH = 16' in out
    assert 'Files to be modified:' in out


def test_backup(project, add_param):
    root = project(MIXED)
    add_param(root, 'fifo', 'DEPTH', 'int', '16', '--backup')
    assert read(root, 'rtl/fifo.sv.bak') == dedent(FIFO)
    assert (root / 'rtl/top.vhd.bak').exists()


def test_extra_search_dir(project, add_param):
    root = project(MIXED)
    add_param(root / 'rtl', 'fifo', 'DEPTH', 'int', '16', '-s',
              str(root / 'tb'))
    assert 'top #(.DEPTH(DEPTH)) dut' in read(root, 'tb/tb.sv')


def test_without_search_dir_tb_is_untouched(project, add_param):
    root = project(MIXED)
    add_param(root / 'rtl', 'fifo', 'DEPTH', 'int', '16')
    assert read(root, 'tb/tb.sv') == dedent(TB)


def test_localparam_in_parent_stops_propagation(project, add_param, capsys):
    root = project({
        'leaf.sv':
        'module leaf (input clk); endmodule\n',
        'mid.sv':
        '''
            module mid (input clk);
                localparam P = 3;
                leaf u (.clk(clk));
            endmodule
        ''',
        'top.sv':
        'module top (input clk); mid u (.clk(clk)); endmodule\n',
    })
    add_param(root, 'leaf', 'P', 'int', '1')
    assert 'leaf #(.P(P)) u' in read(root, 'mid.sv')
    assert 'P' not in read(root, 'top.sv').replace('top', '')
    assert 'localparam P already exists' in capsys.readouterr().out


def test_skipped_positional_returns_2(project, add_param):
    root = project({
        'leaf.sv':
        'module leaf #(parameter A = 1, B = 2) (input clk); endmodule\n',
        'top.sv':
        'module top (input clk); leaf #(5) u (.clk(clk)); endmodule\n',
    })
    assert add_param(root, 'leaf', 'P', 'int', '1') == 2
    assert 'leaf #(5) u' in read(root, 'top.sv')


def test_crlf_is_preserved(project, add_param):
    root = project({
        'leaf.sv':
        'module leaf (\r\n    input clk\r\n);\r\nendmodule\r\n',
        'top.sv':
        'module top (input clk);\r\n    leaf u (.clk(clk));\r\nendmodule\r\n',
    })
    add_param(root, 'leaf', 'P', 'int', '1')
    text = (root / 'leaf.sv').read_bytes().decode()
    assert '\r\n' in text and '\n' not in text.replace('\r\n', '')


def test_hidden_directories_are_skipped(project, add_param):
    root = project({
        'leaf.sv':
        'module leaf (input clk); endmodule\n',
        '.git/x.sv':
        'module x (input clk); leaf u (.clk(clk)); endmodule\n',
    })
    add_param(root, 'leaf', 'P', 'int', '1')
    assert 'leaf u' in read(root, '.git/x.sv')


def test_module_not_found(project, add_param):
    root = project(MIXED)
    with pytest.raises(UserError, match='not found'):
        add_param(root, 'nope', 'P', 'int', '1')


def test_name_in_both_languages(project, add_param):
    root = project({
        'a.sv': 'module dup (input clk); endmodule\n',
        'a.vhd': 'entity dup is end dup;\n',
    })
    with pytest.raises(UserError, match='--lang'):
        add_param(root, 'dup', 'P', 'int', '1')
    add_param(root, 'dup', 'P', 'integer', '1', '--lang', 'vhdl')
    assert 'P : integer := 1' in read(root, 'a.vhd')
    assert 'P' not in read(root, 'a.sv')


def test_error_leaves_files_untouched(project, add_param):
    root = project(MIXED)
    with pytest.raises(Exception, match='--sv-type'):
        add_param(root, 'top', 'T', 'time', '1 ns')
    for name, text in MIXED.items():
        assert read(root, name) == dedent(text)


def test_main_exit_codes(project, capsys):
    root = project(MIXED)
    with pytest.raises(SystemExit) as e:
        main([str(root), 'fifo', 'DEPTH', 'int', '16'])
    assert e.value.code == 0
    with pytest.raises(SystemExit) as e:
        main([str(root), 'nope', 'P', 'int', '1'])
    assert e.value.code == 'error: module/entity nope not found in ' + str(
        root)
    with pytest.raises(SystemExit) as e:
        main([str(root / 'missing'), 'fifo', 'P', 'int', '1'])
    assert 'directory' in e.value.code
