# hdl-param-propagate

[![CI](https://github.com/johny-lemonade/hdl-param-propagate/actions/workflows/ci.yml/badge.svg)](https://github.com/johny-lemonade/hdl-param-propagate/actions/workflows/ci.yml)

Adds a parameter to a Verilog/SystemVerilog module or a VHDL entity and
propagates it **recursively up the hierarchy**:

1. the parameter is added to the module declaration;
2. every instance of the module is found in the project and the parameter is
   connected there (`.P(P)` in Verilog, `P => P` in VHDL);
3. the module that contains the instance gets the same parameter, and so on up
   to the top level.

Mixed Verilog ↔ VHDL hierarchies are supported: VHDL `component` declarations
are updated too, and the parameter type and default value are translated to the
syntax of the other language.

## Requirements

Python 3.10+, standard library only (CI runs the tests on Python 3.10–3.14).
No installation is needed — keep `hdl-param-propagate.py` and the
`hdl_param_propagate/` directory together.

## Usage

```bash
python3 hdl-param-propagate.py <dir> <module> <param> <type> <default> [options]
```

| Argument  | Description |
|-----------|-------------|
| `dir`     | project directory; all `*.sv`, `*.svh`, `*.v`, `*.vh`, `*.vhd`, `*.vhdl` files are searched recursively |
| `module`  | module / entity name |
| `param`   | name of the new parameter |
| `type`    | type in the module's language, e.g. `int`, `"logic [7:0]"`, `natural`, `"std_logic_vector(7 downto 0)"`; `""` = untyped Verilog parameter |
| `default` | default value in the module's language, e.g. `16`, `"8'hA5"`, `true`, `'x"A5"'` |

The language of the module (where it is found) defines the syntax of `type`
and `default`. Quote arguments that contain spaces or quotes.

| Option | Description |
|--------|-------------|
| `-n`, `--dry-run` | print a unified diff, do not modify files |
| `--backup` | save `<file>.bak` before modifying a file |
| `-s DIR`, `--search-dir DIR` | additional search directory (may be repeated) |
| `--stop-at MODULE` | add the parameter to `MODULE` but do not propagate above it (may be repeated) |
| `--max-depth N` | maximum number of levels to go up (`0` = the module only) |
| `--lang {verilog,vhdl}` | module language, if the name exists in both Verilog and VHDL |
| `--sv-type`, `--sv-default` | explicit type / value for Verilog/SV files (when the module is VHDL) |
| `--vhdl-type`, `--vhdl-default` | explicit type / value for VHDL files (when the module is Verilog/SV) |

The package can also be run as `python3 -m hdl_param_propagate ...`.

## Examples

All examples use this project:

```
rtl/
├── fifo.sv    module fifo #(parameter int WIDTH = 8) (...)
├── core.sv    module core (...);  fifo #(.WIDTH(8)) u_fifo (...);
└── top.vhd    entity top;  u_core : core port map (...);   -- component core
```

### Add an integer parameter

```bash
python3 hdl-param-propagate.py rtl fifo DEPTH int 16
```

```
[0] fifo (rtl/fifo.sv:1): parameter DEPTH added
    instance u_fifo in core (rtl/core.sv:6): connected
[1] core (rtl/core.sv:1): parameter DEPTH added
    component core (rtl/top.vhd:16): generic added
    instance u_core in top (rtl/top.vhd:24): connected
[2] top (rtl/top.vhd:4): parameter DEPTH added
Files modified: rtl/core.sv, rtl/fifo.sv, rtl/top.vhd
```

Resulting changes:

```diff
 module fifo #(
-    parameter int WIDTH = 8
+    parameter int WIDTH = 8,
+    parameter int DEPTH = 16
 ) (
```

```diff
-module core (
+module core #(
+    parameter int DEPTH = 16
+) (
     ...
-    fifo #(.WIDTH(8)) u_fifo (.clk(clk), .din(din), .dout(dout));
+    fifo #(.WIDTH(8), .DEPTH(DEPTH)) u_fifo (.clk(clk), .din(din), .dout(dout));
```

```diff
 entity top is
   generic (
-    G_MODE : integer := 0
+    G_MODE : integer := 0;
+    DEPTH  : integer := 16
   );
 ...
   component core is
+    generic (
+      DEPTH : integer := 16
+    );
     port (
 ...
   u_core : core
+    generic map (
+      DEPTH => DEPTH
+    )
     port map (
```

### Vector parameter

```bash
python3 hdl-param-propagate.py rtl fifo MASK "bit [1:0]" "2'b10"
```

```
SV:    parameter bit [1:0] MASK = 2'b10
VHDL:  MASK : std_logic_vector(1 downto 0) := "10"
```

### Preview without modifying files

```bash
python3 hdl-param-propagate.py rtl fifo DEPTH int 16 --dry-run
```

### Module defined in VHDL

```bash
python3 hdl-param-propagate.py rtl my_entity G_EN boolean true
python3 hdl-param-propagate.py rtl my_entity G_MASK "std_logic_vector(7 downto 0)" 'x"A5"'
```

### Untyped Verilog parameter

```bash
python3 hdl-param-propagate.py rtl fifo DBG "" 0
```

### Limit propagation

```bash
# stop at 'core': it gets the parameter, its parents do not
python3 hdl-param-propagate.py rtl fifo DEPTH int 16 --stop-at core

# only the module itself and its direct parents
python3 hdl-param-propagate.py rtl fifo DEPTH int 16 --max-depth 1
```

### Types that cannot be translated automatically

```bash
python3 hdl-param-propagate.py rtl my_entity T_DLY time "1 ns" --sv-type realtime --sv-default 1.0
```

Without `--sv-type/--sv-default` the script stops with an error and modifies
nothing:

```
error: parameter T_DLY: type cannot be translated to Verilog; specify --sv-type/--sv-default explicitly
```

### Several search directories

```bash
python3 hdl-param-propagate.py rtl fifo DEPTH int 16 -s ../ip -s ../common
```

## Type translation

| SystemVerilog | VHDL |
|---------------|------|
| `int` / `integer` = `16` | `integer := 16` |
| `bit [1:0]` = `2'b10` | `std_logic_vector(1 downto 0) := "10"` |
| `logic [7:0]` = `8'hA5` | `std_logic_vector(7 downto 0) := "10100101"` |
| `logic [7:0]` = `'0` | `std_logic_vector(7 downto 0) := (others => '0')` |
| `bit` / `logic` = `1'b1` | `std_logic := '1'` |
| `string` = `"abc"` | `string := "abc"` |
| `real` = `1.5` | `real := 1.5` |
| untyped = `8'd7` | `std_logic_vector(7 downto 0) := "00000111"` |
| `bit` = `1'b1` | `boolean := true` (VHDL → SV) |
| `int` = `255` | `integer := 16#FF#` (VHDL → SV) |

In plain Verilog files (`.v`, `.vh`) SystemVerilog-only types are converted:
`int` → `integer`, `logic [7:0]` → `[7:0]`, `bit`/`string` → untyped.

## Behaviour details

- Comments and string literals are ignored when searching for modules and
  instances; existing comments are kept in place.
- Formatting is preserved: indentation, one-line vs multi-line lists, and column
  alignment of `=`, `:`, `=>`, `(`.
- Re-running is safe: existing declarations and connections are detected and
  left unchanged.
- A Verilog module without a `#(...)` list but with `parameter` declarations in
  its body gets the new parameter in the body (adding a `#(...)` list would turn
  the body parameters into `localparam`s).
- Positional overrides (`#(3, 4)`) are extended positionally when all preceding
  parameters are given; otherwise the instance is reported as `SKIPPED`.
- If the parent already has a `localparam` with the same name, the instance is
  connected to it and propagation stops there.

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | success |
| 1 | error (module not found, ambiguous name, type cannot be translated, …); no files are modified |
| 2 | done, but some instances were `SKIPPED` and must be connected manually |

## Limitations

- `` `ifdef `` / `` `else `` branches are not evaluated — both branches are edited.
- `defparam`, `bind` and VHDL `configuration` declarations are not handled.
- Entities with the same name in different VHDL libraries are not distinguished.
- Unpacked array parameters (`parameter int A [4] = '{...}`) are not supported.

## Project layout

```
hdl-param-propagate.py  entry point
hdl_param_propagate/
├── cli.py              command line, writing files / diff
├── propagate.py        recursive propagation up the hierarchy
├── design.py           loading project files, finding definitions and instances
├── verilog.py          Verilog/SV: modules, instances, .P(P) connection
├── vhdl.py             VHDL: entities, components, architectures, generic map
├── convert.py          SV <-> VHDL type and value translation
├── edit.py             inserting items into (...) lists, keeping the style
└── source.py           file reading, comment/string masking, scanner helpers
tests/
├── conftest.py         pytest fixtures (temporary files and projects)
├── helpers.py          shared test helpers
├── test_source.py      masking, scanner helpers
├── test_edit.py        list insertion, alignment, positional overrides
├── test_convert.py     type / value parsing and SV <-> VHDL translation
├── test_verilog.py     module parsing, instance search and connection
├── test_vhdl.py        entity / component parsing, generic map connection
├── test_end_to_end.py  full runs on mixed Verilog/VHDL projects, CLI options
└── test_simulators.py  compile / simulate results with iverilog, verilator, ghdl
```

## Tests

The tests use [pytest](https://pytest.org):

```bash
python3 -m pytest
```

Run a single file or test:

```bash
python3 -m pytest tests/test_convert.py
python3 -m pytest -k mixed_hierarchy -v
```

`tests/test_simulators.py` runs the script on small projects and then compiles
and simulates the result with [Icarus Verilog](https://steveicarus.github.io/iverilog/),
[Verilator](https://www.veripool.org/verilator/) and [GHDL](https://github.com/ghdl/ghdl):
parameter values are checked at the bottom of the hierarchy, and SV ↔ VHDL type
translations are checked by the compilers. Tests for tools that are not installed
are skipped; set `REQUIRE_SIMULATORS=1` to make them fail instead:

```bash
REQUIRE_SIMULATORS=1 python3 -m pytest tests/test_simulators.py
```

Formatting uses [yapf](https://github.com/google/yapf) with the style from
`pyproject.toml`:

```bash
yapf --diff --recursive hdl_param_propagate tests hdl-param-propagate.py
```

## Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request:

| Job | What it does |
|-----|--------------|
| Lint | `yapf --diff` (formatting) and `pyflakes` (unused imports, undefined names, …) |
| Tests | `pytest` on Python 3.10, 3.11, 3.12, 3.13 and 3.14 |
| HDL simulators | installs `iverilog`, `verilator` and `ghdl` from apt and runs `tests/test_simulators.py` with `REQUIRE_SIMULATORS=1` |
