"""请求缓存：FetchCacheStore 的 TTL / 上限淘汰，以及 get_json 的命中与失效。

运行（在项目根目录）:
	.venv\\Scripts\\python.exe -m pytest test/test_fetch_cache.py -q
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timedelta, timezone

import pytest

import infra.http as http_module
import storage.fetch_cache as fetch_cache_module
from infra.http import HttpError, drop_cached_json, get_json
from storage.fetch_cache import FetchCacheStore


NOVEL_URL = "https://api.linpx.ink/pixiv/novel/1/cache"
SERIES_URL = "https://api.linpx.ink/pixiv/series/9/cache"
OTHER_URL = "https://api.linpx.ink/pixiv/novel/7/cache"


def run(coro):
	return asyncio.run(coro)


def _store(tmp_path, **kwargs) -> FetchCacheStore:
	return FetchCacheStore(path=tmp_path / "fetch_cache.json", **kwargs)


def _iso(delta: timedelta) -> str:
	return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%S%z")


# ----- FetchCacheStore -----
def test_set_then_get_payload(tmp_path) -> None:
	store = _store(tmp_path, default_ttl_hours=1)
	payload = {"error": False, "body": {"id": 1, "tags": [{"tag": "原创"}]}}

	assert store.set(NOVEL_URL, payload) is True
	assert store.get(NOVEL_URL) == payload


def test_missing_key_is_none(tmp_path) -> None:
	store = _store(tmp_path, default_ttl_hours=1)
	assert store.get(NOVEL_URL) is None


def test_payload_persists_across_instances(tmp_path) -> None:
	"""写盘走 JsonStore：换一个实例（等于重启进程）还能读到。"""
	path = tmp_path / "fetch_cache.json"
	FetchCacheStore(path=path, default_ttl_hours=1).set(NOVEL_URL, {"body": {"id": "1"}})

	cached = FetchCacheStore(path=path, default_ttl_hours=1).get(NOVEL_URL)
	assert cached == {"body": {"id": "1"}}


def test_list_payload_persists(tmp_path) -> None:
	"""Linpx 推荐作者接口返回的是数组，也要能缓存。"""
	store = _store(tmp_path, default_ttl_hours=1)
	store.set(NOVEL_URL, [{"id": 1}, {"id": 2}])

	assert store.get(NOVEL_URL) == [{"id": 1}, {"id": 2}]


def test_zero_ttl_means_immediately_expired(tmp_path) -> None:
	"""default_ttl_hours=0 不应被 or 兜底成 config.FETCH_CACHE_TTL_HOURS。"""
	store = _store(tmp_path, default_ttl_hours=0)
	store.set(NOVEL_URL, {"body": {}})
	assert store.get(NOVEL_URL) is None


def test_expired_entry_is_pruned_on_write(tmp_path) -> None:
	path = tmp_path / "fetch_cache.json"
	old = _iso(timedelta(hours=-1))
	alive = _iso(timedelta(hours=1))
	payload = {
		"updated_at": old,
		"responses": {
			NOVEL_URL: {
				"payload": {"old": True}, "size": 12, "seq": 1,
				"cached_at": old, "expires_at": old,
			},
			SERIES_URL: {
				"payload": {"old": False}, "size": 13, "seq": 2,
				"cached_at": old, "expires_at": alive,
			},
		},
	}
	path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

	store = FetchCacheStore(path=path, default_ttl_hours=1)
	assert store.get(NOVEL_URL) is None
	assert store.get(SERIES_URL) == {"old": False}

	# 过期条目在下一次写盘时真正从文件里删除
	store.set(OTHER_URL, {"new": True})
	raw = json.loads(path.read_text(encoding="utf-8"))
	assert NOVEL_URL not in raw["responses"]
	assert SERIES_URL in raw["responses"]
	assert OTHER_URL in raw["responses"]


def test_missing_expires_at_counts_as_expired(tmp_path) -> None:
	"""没有 expires_at（旧格式 / 手写坏）的缓存条目一律当过期：缓存本来就该重建。"""
	path = tmp_path / "fetch_cache.json"
	payload = {
		"updated_at": _iso(timedelta(hours=1)),
		"responses": {
			NOVEL_URL: {
				"payload": {"body": {}}, "size": 12, "seq": 1,
				"cached_at": _iso(timedelta(0)),
			},
		},
	}
	path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

	store = FetchCacheStore(path=path, default_ttl_hours=1)
	assert store.get(NOVEL_URL) is None


def test_remove(tmp_path) -> None:
	store = _store(tmp_path, default_ttl_hours=1)
	store.set(NOVEL_URL, {"body": {}})

	assert store.remove(NOVEL_URL) is True
	assert store.get(NOVEL_URL) is None
	assert store.remove(NOVEL_URL) is False


def test_entries_over_limit_drop_oldest(tmp_path) -> None:
	store = _store(tmp_path, default_ttl_hours=1, max_entries=2)
	store.set(NOVEL_URL, {"n": 1})
	store.set(SERIES_URL, {"n": 2})
	store.set(OTHER_URL, {"n": 3})

	assert store.get(NOVEL_URL) is None
	assert store.get(SERIES_URL) == {"n": 2}
	assert store.get(OTHER_URL) == {"n": 3}


def test_total_size_limit_drops_oldest(tmp_path) -> None:
	store = _store(tmp_path, default_ttl_hours=1, max_bytes=120)
	store.set(NOVEL_URL, {"body": "a" * 40})
	store.set(SERIES_URL, {"body": "b" * 40})
	store.set(OTHER_URL, {"body": "c" * 40})

	# 三条加起来超过上限：最旧的一条被淘汰，剩下两条仍在
	assert store.get(NOVEL_URL) is None
	assert store.get(SERIES_URL) is not None
	assert store.get(OTHER_URL) is not None


def test_oversized_payload_is_skipped(tmp_path) -> None:
	store = _store(tmp_path, default_ttl_hours=1, max_bytes=10)
	assert store.set(NOVEL_URL, {"body": "x" * 100}) is False
	assert store.get(NOVEL_URL) is None


def test_none_payload_is_skipped(tmp_path) -> None:
	store = _store(tmp_path, default_ttl_hours=1)
	assert store.set(NOVEL_URL, None) is False
	assert store.get(NOVEL_URL) is None


# ----- infra.http.get_json -----
def _patch_cache(monkeypatch, tmp_path) -> FetchCacheStore:
	store = _store(tmp_path, default_ttl_hours=1)
	monkeypatch.setattr(fetch_cache_module, "_default_cache", store)
	return store


def _patch_requests(monkeypatch, payload=None) -> list[str]:
	"""替换真实网络：``_request`` 只记录 URL 并返回固定 JSON。"""
	calls: list[str] = []
	body = {"body": {"id": "1"}} if payload is None else payload

	async def fake_request(url, headers=None, *, retry_on_429=True, as_json=True):
		calls.append(url)
		return body

	monkeypatch.setattr(http_module, "_request", fake_request)
	return calls


def test_get_json_hits_cache_on_second_call(monkeypatch, tmp_path) -> None:
	"""同一链接第二次请求直接读缓存，不再打网络。"""
	store = _patch_cache(monkeypatch, tmp_path)
	calls = _patch_requests(monkeypatch)

	first = run(get_json(NOVEL_URL))
	second = run(get_json(NOVEL_URL))

	assert calls == [NOVEL_URL]
	assert first == second == {"body": {"id": "1"}}
	assert store.get(NOVEL_URL) == {"body": {"id": "1"}}


def test_get_json_caches_list_response(monkeypatch, tmp_path) -> None:
	calls = _patch_requests(monkeypatch, payload=[{"id": 1}, {"id": 2}])
	_patch_cache(monkeypatch, tmp_path)

	assert run(get_json(NOVEL_URL)) == [{"id": 1}, {"id": 2}]
	assert run(get_json(NOVEL_URL)) == [{"id": 1}, {"id": 2}]
	assert calls == [NOVEL_URL]


def test_get_json_separates_urls(monkeypatch, tmp_path) -> None:
	_patch_cache(monkeypatch, tmp_path)
	calls = _patch_requests(monkeypatch)

	run(get_json(NOVEL_URL))
	run(get_json(SERIES_URL))

	assert calls == [NOVEL_URL, SERIES_URL]


def test_get_json_can_bypass_cache(monkeypatch, tmp_path) -> None:
	store = _patch_cache(monkeypatch, tmp_path)
	calls = _patch_requests(monkeypatch)

	run(get_json(NOVEL_URL, use_cache=False))
	run(get_json(NOVEL_URL, use_cache=False))

	assert calls == [NOVEL_URL, NOVEL_URL]
	assert store.get(NOVEL_URL) is None


def test_failed_request_is_not_cached(monkeypatch, tmp_path) -> None:
	store = _patch_cache(monkeypatch, tmp_path)

	async def failing(url, headers=None, *, retry_on_429=True, as_json=True):
		raise HttpError(url, 500)

	monkeypatch.setattr(http_module, "_request", failing)
	with pytest.raises(HttpError):
		run(get_json(NOVEL_URL))
	assert store.get(NOVEL_URL) is None


def test_drop_cached_json_forces_refetch(monkeypatch, tmp_path) -> None:
	_patch_cache(monkeypatch, tmp_path)
	calls = _patch_requests(monkeypatch)

	run(get_json(NOVEL_URL))
	assert drop_cached_json(NOVEL_URL) is True
	# 已经删掉了：第二次没有可删的
	assert drop_cached_json(NOVEL_URL) is False

	run(get_json(NOVEL_URL))
	assert calls == [NOVEL_URL, NOVEL_URL]


def test_drop_cached_json_without_cache_is_noop(monkeypatch, tmp_path) -> None:
	"""缓存还没建出来时（测试 / 全新进程）不为了删除而创建缓存文件。"""
	monkeypatch.setattr(fetch_cache_module, "_default_cache", None)

	assert drop_cached_json(NOVEL_URL) is False
	assert (tmp_path / "fetch_cache.json").exists() is False


def test_broken_cache_file_degrades_to_direct_request(monkeypatch, tmp_path) -> None:
	"""缓存文件坏了只该少一层加速：请求照常发出，不能抛异常。"""
	store = _store(tmp_path, default_ttl_hours=1)
	monkeypatch.setattr(fetch_cache_module, "_default_cache", store)
	path = tmp_path / "fetch_cache.json"
	path.write_text("{ 坏掉的 JSON", encoding="utf-8")
	# 让 mtime 变化，保证读取时真的重新加载坏文件
	os.utime(path, (time.time() + 5, time.time() + 5))

	calls = _patch_requests(monkeypatch)
	assert run(get_json(NOVEL_URL)) == {"body": {"id": "1"}}
	assert run(get_json(NOVEL_URL)) == {"body": {"id": "1"}}
	assert calls == [NOVEL_URL, NOVEL_URL]


def test_get_fetch_cache_is_singleton(monkeypatch, tmp_path) -> None:
	monkeypatch.setattr(fetch_cache_module, "_default_cache", None)
	monkeypatch.setattr(
		fetch_cache_module, "FetchCacheStore",
		lambda **_kwargs: _store(tmp_path, default_ttl_hours=1),
	)

	assert fetch_cache_module.get_fetch_cache() is fetch_cache_module.get_fetch_cache()

