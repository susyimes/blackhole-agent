from __future__ import annotations

from pathlib import Path

from python_discovery._cache import DiskCache, DiskContentStore, NoOpCache, NoOpContentStore


def test_disk_content_store_read_valid_json(tmp_path: Path) -> None:
    store = DiskContentStore(tmp_path, "test")
    data = {"key": "value"}
    store.write(data)
    assert store.read() == data


def test_disk_content_store_read_invalid_json(tmp_path: Path) -> None:
    store = DiskContentStore(tmp_path, "test")
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "test.json").write_text("not json", encoding="utf-8")
    assert store.read() is None
    assert not (tmp_path / "test.json").exists()


def test_disk_content_store_read_missing_file(tmp_path: Path) -> None:
    store = DiskContentStore(tmp_path, "test")
    assert store.read() is None


def test_disk_content_store_remove(tmp_path: Path) -> None:
    store = DiskContentStore(tmp_path, "test")
    store.write({"key": "value"})
    assert store.exists()
    store.remove()
    assert not store.exists()


def test_disk_content_store_remove_missing_file(tmp_path: Path) -> None:
    store = DiskContentStore(tmp_path, "test")
    store.remove()


def test_disk_content_store_locked(tmp_path: Path) -> None:
    store = DiskContentStore(tmp_path, "test")
    with store.locked():
        store.write({"key": "value"})
    assert store.read() == {"key": "value"}


def test_disk_content_store_exists(tmp_path: Path) -> None:
    store = DiskContentStore(tmp_path, "test")
    assert store.exists() is False
    store.write({"key": "value"})
    assert store.exists() is True


def test_disk_cache_py_info(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    store = cache.py_info(Path("/some/path"))
    assert isinstance(store, DiskContentStore)


def test_disk_cache_py_info_clear(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    store = cache.py_info(Path("/some/path"))
    store.write({"key": "value"})
    assert store.exists()
    cache.py_info_clear()
    assert not store.exists()


def test_disk_cache_py_info_clear_empty(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    cache.py_info_clear()


def test_disk_cache_py_info_clear_skips_non_json(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    py_info_dir = tmp_path / "py_info" / "4"
    py_info_dir.mkdir(parents=True)
    (py_info_dir / "test.json").write_text("{}", encoding="utf-8")
    (py_info_dir / "notjson.txt").touch()
    cache.py_info_clear()
    remaining = [entry.name for entry in py_info_dir.iterdir()]
    assert "notjson.txt" in remaining
    assert "test.json" not in remaining


def test_noop_content_store_exists() -> None:
    assert NoOpContentStore().exists() is False


def test_noop_content_store_read() -> None:
    assert NoOpContentStore().read() is None


def test_noop_content_store_write() -> None:
    NoOpContentStore().write({"key": "value"})


def test_noop_content_store_remove() -> None:
    NoOpContentStore().remove()


def test_noop_content_store_locked() -> None:
    with NoOpContentStore().locked():
        pass


def test_noop_cache_py_info() -> None:
    cache = NoOpCache()
    store = cache.py_info(Path("/some/path"))
    assert isinstance(store, NoOpContentStore)


def test_noop_cache_py_info_clear() -> None:
    NoOpCache().py_info_clear()
