import pytest

from hdl_param_propagate.cli import parse_args, run
from hdl_param_propagate.source import Source
from helpers import dedent, write


@pytest.fixture
def make_src(tmp_path):

    def make(text, name='a.sv'):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        write(path, dedent(text))
        return Source(str(path))

    return make


@pytest.fixture
def project(tmp_path):

    def make(files):
        for name, text in files.items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            write(path, dedent(text))
        return tmp_path

    return make


@pytest.fixture
def add_param():

    def call(root, *args):
        return run(parse_args([str(root), *args]))

    return call
