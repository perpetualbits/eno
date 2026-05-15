"""Minimal test runner without pytest dependency.

Discovers test_*.py files in the same directory, imports them, finds
functions starting with test_, runs each one. Reports pass/fail.

Supports a tiny shim for `pytest.raises` used in our tests.
"""

import importlib.util
import os
import sys
import traceback
from contextlib import contextmanager


class _RaisesCtx:
    def __init__(self, expected_type, match=None):
        self.expected_type = expected_type
        self.match = match
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            raise AssertionError(
                f"expected {self.expected_type.__name__} but no exception was raised"
            )
        if not issubclass(exc_type, self.expected_type):
            return False
        if self.match is not None:
            import re
            if not re.search(self.match, str(exc_val)):
                raise AssertionError(
                    f"expected {self.expected_type.__name__} matching "
                    f"{self.match!r}, got: {exc_val!r}"
                )
        self.value = exc_val
        return True


class _PytestShim:
    """Minimal pytest shim."""

    @staticmethod
    def raises(expected_type, *, match=None):
        return _RaisesCtx(expected_type, match=match)


# Make `import pytest` work for our test files.
sys.modules.setdefault("pytest", _PytestShim())


def discover_and_run(test_dir):
    test_dir = os.path.abspath(test_dir)
    sys.path.insert(0, test_dir)
    # Also add the src directory.
    src_dir = os.path.join(os.path.dirname(test_dir), "src")
    if os.path.isdir(src_dir):
        sys.path.insert(0, src_dir)

    test_files = sorted(
        f for f in os.listdir(test_dir)
        if f.startswith("test_") and f.endswith(".py")
    )

    passed = 0
    failed = 0
    failures = []

    for f in test_files:
        module_name = f[:-3]
        spec = importlib.util.spec_from_file_location(
            module_name, os.path.join(test_dir, f),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for name in dir(mod):
            if not name.startswith("test_"):
                continue
            func = getattr(mod, name)
            if not callable(func):
                continue
            try:
                func()
                passed += 1
                print(f"  PASS {module_name}::{name}")
            except Exception as e:
                failed += 1
                tb = traceback.format_exc()
                failures.append((f"{module_name}::{name}", tb))
                print(f"  FAIL {module_name}::{name}: {e}")

    print()
    print(f"Result: {passed} passed, {failed} failed")
    if failed:
        print()
        print("=" * 70)
        for name, tb in failures:
            print(f"FAILURE: {name}")
            print(tb)
            print("-" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    test_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(__file__) or "."
    sys.exit(discover_and_run(test_dir))
