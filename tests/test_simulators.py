import os
import re
import shutil
import subprocess

import pytest

from helpers import write

REQUIRED = os.environ.get('REQUIRE_SIMULATORS') == '1'


def _needs(*tools):
    missing = [t for t in tools if not shutil.which(t)]
    return pytest.mark.skipif(bool(missing) and not REQUIRED,
                              reason=' '.join(missing) + ' not installed')


needs_iverilog = _needs('iverilog', 'vvp')
needs_verilator = _needs('verilator')
needs_ghdl = _needs('ghdl')


def sh(cwd, *cmd):
    r = subprocess.run(cmd,
                       cwd=str(cwd),
                       stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT,
                       universal_newlines=True)
    assert r.returncode == 0, ' '.join(cmd) + '\n' + r.stdout
    return r.stdout


VERILOG = {
    'leaf.sv':
    '''
        module leaf #(
            parameter int WIDTH = 8
        ) (
            input logic clk
        );
            initial $display("%m DEPTH=%0d MASK=%b", DEPTH, MASK);
        endmodule
    ''',
    'mid.v':
    '''
        module mid (clk);
            input clk;
            parameter N = 2;
            genvar i;
            generate
                for (i = 0; i < N; i = i + 1) begin : g
                    leaf #(.WIDTH(4)) u_leaf (.clk(clk));
                end
            endgenerate
        endmodule
    ''',
    'top.sv':
    '''
        module top;
            logic clk;
            mid u_mid (.clk(clk));
        endmodule
    ''',
}


def _verilog_project(project, add_param):
    root = project(VERILOG)
    add_param(root, 'leaf', 'DEPTH', 'int', '16')
    add_param(root, 'leaf', 'MASK', 'logic [3:0]', "4'hA")
    return root


@needs_iverilog
def test_iverilog_default_and_override(project, add_param):
    root = _verilog_project(project, add_param)
    files = ['leaf.sv', 'mid.v', 'top.sv']

    sh(root, 'iverilog', '-g2012', '-o', 'sim', *files)
    out = sh(root, 'vvp', '-n', 'sim')
    assert out.count('DEPTH=16 MASK=1010') == 2

    sh(root, 'iverilog', '-g2012', '-Ptop.DEPTH=7', "-Ptop.MASK=4'b0101", '-o',
       'sim', *files)
    out = sh(root, 'vvp', '-n', 'sim')
    assert out.count('DEPTH=7 MASK=0101') == 2


@needs_iverilog
def test_iverilog_plain_verilog_file_has_no_sv_syntax(project, add_param):
    root = _verilog_project(project, add_param)
    write(
        root / 'leaf_stub.v',
        'module leaf (clk); input clk; parameter WIDTH = 0, DEPTH = 0, MASK = 0; endmodule\n'
    )
    out = sh(root, 'iverilog', '-g2001', '-o', '/dev/null', 'mid.v',
             'leaf_stub.v')
    assert 'SystemVerilog' not in out


@needs_verilator
def test_verilator_lint(project, add_param):
    root = _verilog_project(project, add_param)
    sh(root, 'verilator', '--lint-only', '--top-module', 'top', 'leaf.sv',
       'mid.v', 'top.sv')


VHDL = {
    'leaf.vhd':
    '''
        library ieee;
        use ieee.std_logic_1164.all;

        entity leaf is
          port (clk : in std_logic);
        end entity leaf;

        architecture sim of leaf is
        begin
          process
          begin
            report "DEPTH=" & integer'image(G_DEPTH) & " MASK=" & to_string(G_MASK);
            wait;
          end process;
        end architecture sim;
    ''',
    'mid.vhd':
    '''
        library ieee;
        use ieee.std_logic_1164.all;

        entity mid is
          port (clk : in std_logic);
        end entity mid;

        architecture rtl of mid is
          component leaf is
            port (clk : in std_logic);
          end component;
        begin
          g : for i in 0 to 1 generate
            u_leaf : leaf port map (clk => clk);
          end generate;
        end architecture rtl;
    ''',
    'top.vhd':
    '''
        library ieee;
        use ieee.std_logic_1164.all;

        entity top is
        end entity top;

        architecture sim of top is
          signal clk : std_logic := '0';
        begin
          u_mid : entity work.mid
            port map (clk => clk);
        end architecture sim;
    ''',
}


def _ghdl_run(root, *generics):
    for f in ('leaf.vhd', 'mid.vhd', 'top.vhd'):
        sh(root, 'ghdl', '-a', '--std=08', f)
    sh(root, 'ghdl', '-e', '--std=08', 'top')
    return sh(root, 'ghdl', '-r', '--std=08', 'top', *generics)


@needs_ghdl
def test_ghdl_default_and_override(project, add_param):
    root = project(VHDL)
    add_param(root, 'leaf', 'G_DEPTH', 'natural', '16')
    add_param(root, 'leaf', 'G_MASK', 'std_logic_vector(3 downto 0)', 'x"A"')

    assert _ghdl_run(root).count('DEPTH=16 MASK=1010') == 2
    out = _ghdl_run(root, '-gG_DEPTH=7', '-gG_MASK=0101')
    assert out.count('DEPTH=7 MASK=0101') == 2


SV_TO_VHDL = [
    ('int', '16'),
    ('logic [7:0]', "8'hA5"),
    ('bit [1:0]', "2'b10"),
    ('logic [7:0]', "'0"),
    ('bit', "1'b1"),
    ('string', '"abc"'),
    ('', "8'd7"),
]


@needs_ghdl
@needs_iverilog
@pytest.mark.parametrize('ptype, default', SV_TO_VHDL)
def test_mixed_sv_root(project, add_param, ptype, default):
    root = project({
        'leaf.sv': 'module leaf (input logic clk); endmodule\n',
        'mid.vhd': VHDL['mid.vhd'],
        'top.sv': VERILOG['top.sv'],
    })
    add_param(root, 'leaf', 'P', ptype, default)
    sh(root, 'ghdl', '-a', '--std=08', 'mid.vhd')
    write(root / 'mid_stub.sv',
          'module mid #(parameter P = 0) (input logic clk); endmodule\n')
    sh(root, 'iverilog', '-g2012', '-o', '/dev/null', 'leaf.sv', 'top.sv',
       'mid_stub.sv')


VHDL_TO_SV = [
    ('natural', '16'),
    ('boolean', 'true'),
    ('std_logic', "'1'"),
    ('std_logic_vector(7 downto 0)', 'x"A5"'),
    ('std_logic_vector(3 downto 0)', "(others => '1')"),
    ('integer', '16#FF#'),
    ('string', '"abc"'),
]


@needs_ghdl
@needs_iverilog
@pytest.mark.parametrize('ptype, default', VHDL_TO_SV)
def test_mixed_vhdl_root_through_plain_verilog(project, add_param, ptype,
                                               default):
    root = project({
        'leaf.vhd':
        '''
            library ieee;
            use ieee.std_logic_1164.all;
            entity leaf is
              port (clk : in std_logic);
            end entity leaf;
            architecture rtl of leaf is
            begin
            end architecture rtl;
        ''',
        'mid.v':
        '''
            module mid (clk);
                input clk;
                leaf u_leaf (.clk(clk));
            endmodule
        ''',
        'top.vhd':
        '''
            library ieee;
            use ieee.std_logic_1164.all;
            entity top is
            end entity top;
            architecture rtl of top is
              component mid is
                port (clk : in std_logic);
              end component;
              signal clk : std_logic;
            begin
              u_mid : mid port map (clk => clk);
            end architecture rtl;
        ''',
    })
    add_param(root, 'leaf', 'P', ptype, default)
    sh(root, 'ghdl', '-a', '--std=08', 'leaf.vhd', 'top.vhd')
    write(root / 'leaf_stub.v',
          'module leaf (clk); input clk; parameter P = 0; endmodule\n')
    out = sh(root, 'iverilog', '-g2001', '-o', '/dev/null', 'mid.v',
             'leaf_stub.v')
    assert 'SystemVerilog' not in out
    assert re.search(r'parameter .*P = ', (root / 'mid.v').read_text())
