import json
import os
import time

from src.providers.cache import cached_fetch


def test_cached_fetch_calls_fetch_fn_once_within_ttl(tmp_path, monkeypatch):
    monkeypatch.setattr("src.providers.cache.CACHE_ROOT", tmp_path)
    calls = {"n": 0}

    def fetch_fn():
        calls["n"] += 1
        return {"value": 42}

    first = cached_fetch("testprov", "key1", ttl_seconds=3600, fetch_fn=fetch_fn)
    second = cached_fetch("testprov", "key1", ttl_seconds=3600, fetch_fn=fetch_fn)

    assert first == {"value": 42}
    assert second == {"value": 42}
    assert calls["n"] == 1


def test_cached_fetch_refetches_after_ttl_expires(tmp_path, monkeypatch):
    monkeypatch.setattr("src.providers.cache.CACHE_ROOT", tmp_path)
    calls = {"n": 0}

    def fetch_fn():
        calls["n"] += 1
        return {"value": calls["n"]}

    cached_fetch("testprov", "key2", ttl_seconds=3600, fetch_fn=fetch_fn)
    cache_file = tmp_path / "testprov" / "key2.json"
    old_time = time.time() - 7200
    os.utime(cache_file, (old_time, old_time))

    result = cached_fetch("testprov", "key2", ttl_seconds=3600, fetch_fn=fetch_fn)
    assert result == {"value": 2}
    assert calls["n"] == 2


def test_cached_fetch_recovers_from_corrupt_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("src.providers.cache.CACHE_ROOT", tmp_path)
    cache_file = tmp_path / "provider" / "key.json"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text("{partial")
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return {"fresh": True}

    assert cached_fetch("provider", "key", 3600, fetch) == {"fresh": True}
    assert calls["n"] == 1
    assert json.loads(cache_file.read_text()) == {"fresh": True}
