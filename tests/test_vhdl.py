from hdl_param_propagate import vhdl
from helpers import spec

TOP = '''
    library ieee;
    use ieee.std_logic_1164.all;

    entity top is
      generic (
        G_A : integer := 1;  -- comment A
        G_B : string  := "x"
      );
      port (clk : in std_logic);
    end entity top;

    architecture rtl of top is
      component leaf is
        port (clk : in std_logic);
      end component leaf;
    begin
      -- c0 : leaf port map (clk => clk);
      u0 : leaf port map (clk => clk);
      u1 : component leaf
        port map (
          clk => clk
        );
      gen : for i in 0 to 1 generate
        u2 : entity work.leaf(rtl)
          generic map (A => 1)
          port map (clk => clk);
      end generate;
      u3 : entity leaf generic map (1) port map (clk => clk);
      u4 : leaf_other port map (clk => clk);
    end architecture rtl;
'''


def test_parse_units(make_src):
    src = make_src(TOP, name='top.vhd')
    entities, comps, archs = vhdl.parse(src)
    assert [e.name for e in entities] == ['top']
    assert [c.name for c in comps] == ['leaf']
    assert [(a.name, a.entity) for a in archs] == [('rtl', 'top')]


def test_param_names_and_has_param(make_src):
    src = make_src('''
        entity e is
          generic (A, B : integer := 1; constant C : string := "x;y");
        end e;
    ''',
                   name='e.vhd')
    e = vhdl.parse(src)[0][0]
    assert e.param_names() == ['a', 'b', 'c']
    assert e.has_param('b') == 'generic'
    assert e.has_param('D') is None


def test_add_generic_to_existing_list(make_src):
    src = make_src(TOP, name='top.vhd')
    vhdl.parse(src)[0][0].add_param(
        spec(lang='vhdl', ptype='natural', default='4'))
    assert '    G_B : string  := "x";\n    P   : natural := 4\n  );' in src.result(
    )


def test_add_generic_creates_list_before_port(make_src):
    src = make_src(TOP, name='top.vhd')
    vhdl.parse(src)[1][0].add_param(
        spec(lang='vhdl', ptype='natural', default='4'))
    assert ('  component leaf is\n'
            '    generic (\n'
            '      P : natural := 4\n'
            '    );\n'
            '    port (clk : in std_logic);\n') in src.result()


def test_add_generic_to_entity_without_ports(make_src):
    src = make_src('''
        entity e is
        end e;
    ''',
                   name='e.vhd')
    vhdl.parse(src)[0][0].add_param(
        spec(lang='vhdl', ptype='integer', default='1'))
    assert src.result(
    ) == 'entity e is\ngeneric (\n  P : integer := 1\n);\nend e;\n'


def test_add_generic_inline_header(make_src):
    src = make_src('entity e is port (a : in bit); end e;\n', name='e.vhd')
    vhdl.parse(src)[0][0].add_param(
        spec(lang='vhdl', ptype='integer', default='1'))
    assert src.result() == \
        'entity e is generic (P : integer := 1); port (a : in bit); end e;\n'


def _leaf_and_top(make_src):
    leaf_src = make_src('''
        entity leaf is
          generic (A : integer := 0);
          port (clk : in bit);
        end leaf;
    ''',
                        name='leaf.vhd')
    leaf = vhdl.parse(leaf_src)[0][0]
    src = make_src(TOP, name='top.vhd')
    entities, _, archs = vhdl.parse(src)
    by_name = {e.name.lower(): [e] for e in entities}
    found = list(
        vhdl.find_instances(src, leaf, archs,
                            lambda n: by_name.get(n.lower(), [])))
    return src, found


def test_find_instances(make_src):
    _, found = _leaf_and_top(make_src)
    assert [label for label, *_ in found] == ['u0', 'u1', 'u2', 'u3']
    assert {parent.name for _, _, parent, _ in found} == {'top'}


def test_connect_instances(make_src):
    src, found = _leaf_and_top(make_src)
    assert [connect('P') for *_, connect in found] == \
        ['connected', 'connected', 'connected', 'connected (positional)']
    out = src.result()
    assert '  u0 : leaf generic map (P => P) port map (clk => clk);' in out
    assert ('  u1 : component leaf\n'
            '    generic map (\n'
            '      P => P\n'
            '    )\n'
            '    port map (\n') in out
    assert '      generic map (A => 1, P => P)' in out
    assert '  u3 : entity leaf generic map (1, P) port map (clk => clk);' in out


def test_connect_already_connected(make_src):
    leaf_src = make_src('entity leaf is end leaf;\n', name='leaf.vhd')
    leaf = vhdl.parse(leaf_src)[0][0]
    src = make_src('''
        entity top is end top;
        architecture rtl of top is
        begin
          u0 : entity work.leaf generic map (p => P) port map (clk => clk);
        end rtl;
    ''',
                   name='top.vhd')
    entities, _, archs = vhdl.parse(src)
    found = list(vhdl.find_instances(src, leaf, archs, lambda n: entities))
    assert [connect('P') for *_, connect in found] == ['already']


def test_instance_with_unknown_parent_entity(make_src, capsys):
    leaf_src = make_src('entity leaf is end leaf;\n', name='leaf.vhd')
    leaf = vhdl.parse(leaf_src)[0][0]
    src = make_src('''
        architecture rtl of missing is
        begin
          u0 : entity work.leaf port map (clk => clk);
        end rtl;
    ''',
                   name='arch.vhd')
    _, _, archs = vhdl.parse(src)
    found = list(vhdl.find_instances(src, leaf, archs, lambda n: []))
    assert [(label, parent) for label, _, parent, _ in found] == [('u0', None)]
    assert 'entity missing' in capsys.readouterr().err
