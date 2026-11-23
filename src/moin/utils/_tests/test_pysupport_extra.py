# License: GNU GPL v2 (or any later version), see LICENSE.txt for details.

"""Unit tests for module discovery and thread-safe helpers, independent of migration."""

from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from moin.utils import pysupport


class FakeLock:
    """Single-threaded lock fake that detects missing or unbalanced locking."""

    def __init__(self):
        self.locked = False
        self.events = []

    def acquire(self):
        assert not self.locked
        self.locked = True
        self.events.append("acquire")

    def release(self):
        assert self.locked
        self.locked = False
        self.events.append("release")


def test_load_package_modules_filters_files_and_skips_loaded_modules(monkeypatch):
    listings = {"first": ["zeta.py", "_private.py", "__init__.py", "notes.txt", "cached.py"], "second": ["alpha.py"]}
    # A directory-listing stub and an isolated module-cache stub avoid real imports.
    monkeypatch.setattr(pysupport, "os", SimpleNamespace(listdir=listings.__getitem__))
    monkeypatch.setattr(pysupport, "sys", SimpleNamespace(modules={"example.cached": object()}))
    importer = Mock()
    monkeypatch.setattr(pysupport, "importlib", SimpleNamespace(import_module=importer))

    pysupport.load_package_modules("example", ["first", "second"])

    assert importer.call_args_list == [call("example.zeta"), call("example.alpha")]


@pytest.mark.parametrize("paths", ["directory", None, {"directory"}])
def test_load_package_modules_rejects_invalid_path_containers(paths):
    with pytest.raises(AssertionError):
        pysupport.load_package_modules("example", paths)


def test_load_package_modules_propagates_import_errors(monkeypatch):
    monkeypatch.setattr(pysupport, "os", SimpleNamespace(listdir=lambda path: ["broken.py"]))
    error = ImportError("missing plugin dependency")
    importer = Mock(side_effect=error)
    monkeypatch.setattr(pysupport, "importlib", SimpleNamespace(import_module=importer))

    with pytest.raises(ImportError) as caught:
        pysupport.load_package_modules("example", ("plugins",))

    assert caught.value is error
    importer.assert_called_once_with("example.broken")


@pytest.mark.parametrize("module, expected", [("sys", 1), ("_moin_nonexistent_test_module_", 0)])
def test_is_importable_reports_module_availability(module, expected):
    assert pysupport.isImportable(module) == expected


def test_get_plugin_modules_filters_and_sorts(monkeypatch):
    # The stub intentionally returns an unsorted mix of public and ignored files.
    monkeypatch.setattr(
        pysupport,
        "os",
        SimpleNamespace(listdir=lambda path: ["zeta.py", "_hidden.py", "__init__.py", "alpha.py", "alpha.pyc"]),
    )

    assert pysupport.getPluginModules("plugins") == ["alpha", "zeta"]


def test_get_package_modules_uses_parent_directory(tmp_path):
    for name in ["__init__.py", "zeta.py", "alpha.py", "_private.py", "notes.txt"]:
        (tmp_path / name).touch()

    assert pysupport.getPackageModules(str(tmp_path / "__init__.py")) == ["alpha", "zeta"]


def test_make_thread_safe_forwards_arguments_and_returns_result():
    lock = FakeLock()
    result = object()

    def operation(value, *, increment):
        assert lock.locked
        assert (value, increment) == (7, 3)
        return result

    wrapped = pysupport.makeThreadSafe(operation, lock)

    assert wrapped(7, increment=3) is result
    assert not lock.locked
    assert lock.events == ["acquire", "release"]


def test_make_thread_safe_releases_lock_after_exception():
    lock = FakeLock()
    error = ValueError("operation failed")

    def operation():
        assert lock.locked
        raise error

    wrapped = pysupport.makeThreadSafe(operation, lock)

    with pytest.raises(ValueError) as caught:
        wrapped()

    assert caught.value is error
    assert not lock.locked
    # A failed operation must leave the lock usable by the next caller.
    assert pysupport.makeThreadSafe(lambda: "recovered", lock)() == "recovered"
    assert lock.events == ["acquire", "release", "acquire", "release"]


def test_make_thread_safe_creates_and_reuses_default_lock(monkeypatch):
    import threading

    lock = FakeLock()
    factory = Mock(return_value=lock)
    monkeypatch.setattr(threading, "Lock", factory)

    def operation():
        assert lock.locked
        return "done"

    wrapped = pysupport.makeThreadSafe(operation)
    assert wrapped() == "done"
    assert wrapped() == "done"

    factory.assert_called_once_with()
    assert lock.events == ["acquire", "release", "acquire", "release"]


@pytest.mark.parametrize("equality, expected", [(True, False), (False, True), (NotImplemented, NotImplemented)])
def test_auto_ne_inverts_equality_and_preserves_not_implemented(equality, expected):
    class Comparable(pysupport.AutoNe):
        def __eq__(self, other):
            return equality

    assert Comparable().__ne__(object()) is expected
