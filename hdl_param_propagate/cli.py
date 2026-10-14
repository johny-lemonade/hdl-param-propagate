import argparse
import difflib
import os
import shutil
import sys

from .convert import ConvError, ParamSpec
from .design import Design, collect_files
from .propagate import UserError, find_roots, propagate


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        prog='hdl-param-propagate.py',
        description='Add a parameter to a module and recursively propagate it '
        'through all instances.')
    ap.add_argument(
        'dir',
        help=
        'project directory: *.sv, *.svh, *.v, *.vhd are searched recursively')
    ap.add_argument('module', help='module / entity name')
    ap.add_argument('param', help='parameter name')
    ap.add_argument(
        'type',
        help='parameter type in the module language ("" - untyped for Verilog)'
    )
    ap.add_argument('default', help='default value')
    ap.add_argument('-s',
                    '--search-dir',
                    action='append',
                    help='additional search directory (may be repeated)')
    ap.add_argument(
        '--lang',
        choices=('verilog', 'vhdl'),
        help='module language if the name exists in both Verilog and VHDL')
    ap.add_argument(
        '--stop-at',
        action='append',
        default=[],
        metavar='MODULE',
        help='add the parameter to MODULE but do not propagate above it')
    ap.add_argument('--max-depth',
                    type=int,
                    help='maximum propagation depth (0 - the module only)')
    ap.add_argument('--sv-type',
                    help='type for Verilog/SV when the module is VHDL')
    ap.add_argument('--sv-default', help='default value for Verilog/SV')
    ap.add_argument('--vhdl-type',
                    help='type for VHDL when the module is Verilog/SV')
    ap.add_argument('--vhdl-default', help='default value for VHDL')
    ap.add_argument('-n',
                    '--dry-run',
                    action='store_true',
                    help='only show the diff')
    ap.add_argument('--backup',
                    action='store_true',
                    help='save *.bak before modifying')
    return ap.parse_args(argv)


def write_changes(design, dry_run=False, backup=False):
    changed = design.changed_sources()
    for s in changed:
        new = s.result()
        if dry_run:
            sys.stdout.writelines(
                difflib.unified_diff(s.text.splitlines(True),
                                     new.splitlines(True), s.path, s.path))
            continue
        if backup:
            shutil.copy2(s.path, s.path + '.bak')
        with open(s.path,
                  'w',
                  encoding='utf-8',
                  errors='surrogateescape',
                  newline='') as f:
            f.write(new)
    verb = 'to be modified' if dry_run else 'modified'
    print(f'Files {verb}: ' + (', '.join(s.path for s in changed) or 'none'))


def run(args):
    dirs = [args.dir] + (args.search_dir or [])
    for d in dirs:
        if not os.path.isdir(d):
            raise UserError(f'directory {d} not found')
    design = Design(collect_files(dirs))
    roots = find_roots(design, args.module, args.lang, args.dir)
    overrides = {
        'sv_type': args.sv_type,
        'sv_default': args.sv_default,
        'vhdl_type': args.vhdl_type,
        'vhdl_default': args.vhdl_default
    }
    spec = ParamSpec(args.param, roots[0].src.lang, args.type, args.default,
                     overrides)
    status = propagate(design, roots, spec, args.stop_at, args.max_depth)
    write_changes(design, args.dry_run, args.backup)
    return status


def main(argv=None):
    args = parse_args(argv)
    try:
        sys.exit(run(args))
    except (ConvError, UserError) as e:
        sys.exit(f'error: {e}')
