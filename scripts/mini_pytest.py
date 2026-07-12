"""mini_pytest — a ~150-line fallback runner for constrained environments.

The real workflow is plain `pytest` (installed via `pip install -e ".[dev]"`).
This script exists for environments where pytest cannot be installed (e.g.
offline sandboxes): it emulates the tiny subset of the pytest API this test
suite uses — raises, mark.parametrize, markers, skip/importorskip, and the
tmp_path / monkeypatch arguments — and runs tests/**/test_*.py.

It is intentionally dumb and small. Do not extend it; extend the tests, and
let pytest be pytest.

Usage:  python scripts/mini_pytest.py [-k substring] [--integration]
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import itertools
import re
import shutil
import sys
import tempfile
import traceback
import types
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# --------------------------------------------------------------- pytest shim
class Skip(Exception):
    pass


class _ExcInfo:
    value: BaseException | None = None


@contextmanager
def _raises(expected, match: str | None = None):
    info = _ExcInfo()
    try:
        yield info
    except expected as exc:
        info.value = exc
        if match is not None and not re.search(match, str(exc)):
            raise AssertionError(
                f"exception message {str(exc)!r} does not match {match!r}"
            )
    else:
        raise AssertionError(f"DID NOT RAISE {expected}")


class _Mark:
    def __init__(self, name: str):
        self.name = name

    def __call__(self, func):  # bare marker used as decorator
        marks = getattr(func, "_shim_marks", [])
        func._shim_marks = [*marks, self.name]
        return func


class _MarkNamespace:
    def parametrize(self, argnames: str, argvalues):
        names = [n.strip() for n in argnames.split(",")]

        def deco(func):
            layers = getattr(func, "_shim_params", [])
            func._shim_params = [*layers, (names, list(argvalues))]
            return func

        return deco

    def __getattr__(self, name: str) -> _Mark:  # e.g. pytest.mark.integration
        return _Mark(name)


def _skip(reason: str = ""):
    raise Skip(reason)


def _importorskip(modname: str):
    try:
        return __import__(modname)
    except ImportError:
        raise Skip(f"could not import {modname!r}")


def _fixture(func=None, **_kw):  # accepted but unused by this suite
    return func if func is not None else (lambda f: f)


shim = types.ModuleType("pytest")
shim.raises = _raises
shim.mark = _MarkNamespace()
shim.skip = _skip
shim.importorskip = _importorskip
shim.fixture = _fixture
sys.modules["pytest"] = shim


class _MonkeyPatch:
    def __init__(self):
        self._saved: list[tuple[object, str, object, bool]] = []

    def setattr(self, target, name, value):
        existed = hasattr(target, name)
        self._saved.append((target, name, getattr(target, name, None), existed))
        setattr(target, name, value)

    def undo(self):
        for target, name, old, existed in reversed(self._saved):
            if existed:
                setattr(target, name, old)
            else:
                delattr(target, name)


# ------------------------------------------------------------------- running
def _expand(func):
    """Turn stacked parametrize layers into a list of (case_id, kwargs)."""
    layers = getattr(func, "_shim_params", [])
    if not layers:
        return [("", {})]
    per_layer = []
    for names, values in layers:
        cases = []
        for value in values:
            row = value if isinstance(value, (tuple, list)) and len(names) > 1 else [value]
            cases.append(dict(zip(names, row)))
        per_layer.append(cases)
    combos = []
    for combo in itertools.product(*per_layer):
        merged: dict = {}
        for part in combo:
            merged.update(part)
        case_id = "[" + "-".join(repr(v) for v in merged.values()) + "]"
        combos.append((case_id, merged))
    return combos


def _import_file(path: Path):
    rel = path.relative_to(ROOT).with_suffix("")
    module_name = ".".join(rel.parts)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", default="", help="only run tests containing substring")
    ap.add_argument("--integration", action="store_true")
    args = ap.parse_args()

    _import_file(ROOT / "conftest.py")
    _import_file(ROOT / "tests" / "conftest.py")

    passed = failed = skipped = 0
    failures: list[tuple[str, str]] = []

    for path in sorted((ROOT / "tests").rglob("test_*.py")):
        module = _import_file(path)
        raw_marks = getattr(module, "pytestmark", [])
        if isinstance(raw_marks, _Mark):  # pytest allows a bare mark too
            raw_marks = [raw_marks]
        module_marks = [m.name for m in raw_marks]
        for attr, func in sorted(vars(module).items()):
            if not (attr.startswith("test_") and callable(func)):
                continue
            marks = module_marks + getattr(func, "_shim_marks", [])
            for case_id, params in _expand(func):
                test_id = f"{path.relative_to(ROOT)}::{attr}{case_id}"
                if args.k and args.k not in test_id:
                    continue
                if "integration" in marks and not args.integration:
                    skipped += 1
                    continue
                kwargs, cleanups = dict(params), []
                sig_params = inspect.signature(func).parameters
                if "tmp_path" in sig_params:
                    d = Path(tempfile.mkdtemp(prefix="mini_pytest_"))
                    kwargs["tmp_path"] = d
                    cleanups.append(lambda d=d: shutil.rmtree(d, ignore_errors=True))
                if "monkeypatch" in sig_params:
                    mp = _MonkeyPatch()
                    kwargs["monkeypatch"] = mp
                    cleanups.append(mp.undo)
                try:
                    func(**kwargs)
                    passed += 1
                    print(f"PASS  {test_id}")
                except Skip as s:
                    skipped += 1
                    print(f"SKIP  {test_id}  ({s})")
                except Exception:
                    failed += 1
                    failures.append((test_id, traceback.format_exc()))
                    print(f"FAIL  {test_id}")
                finally:
                    for cleanup in cleanups:
                        cleanup()

    print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
    for test_id, tb in failures:
        print(f"\n--- {test_id} ---\n{tb}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
