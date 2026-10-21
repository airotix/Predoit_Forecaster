"""Hashes of the forecasting source, found by module name rather than by file location.

Lineage and backtest reports record which code produced a result. Looking modules up through the
import system means the hashes stay the same when files move between folders or into a package.
"""
import hashlib
from importlib.util import find_spec
from pathlib import Path


def source_bytes(module):
    spec = find_spec(module)
    if spec is None or not spec.origin:
        raise ModuleNotFoundError(f'Cannot locate source for {module}.')
    return Path(spec.origin).read_bytes()


def code_hash(modules):
    """SHA-256 of the concatenated sources, in the order given."""
    return hashlib.sha256(b''.join(source_bytes(m) for m in modules)).hexdigest()


def file_hashes(modules):
    """{'<module>.py': sha256} for each module."""
    return {f'{m}.py': hashlib.sha256(source_bytes(m)).hexdigest() for m in modules}
