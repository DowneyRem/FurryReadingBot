"""FileCacheStore：TTL、持久化、过期清理。

运行（在项目根目录）:
	python -m pytest test/test_file_cache.py -v
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from storage.file_cache import FileCacheStore


def _store(tmp_path, **kwargs) -> FileCacheStore:
	return FileCacheStore(path=tmp_path / "files_cache.json", **kwargs)


def _iso(delta: timedelta) -> str:
	return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%S%z")


def test_make_key() -> None:
	assert FileCacheStore.make_key("novel", "1", "txt") == "novel:1:txt"
	assert FileCacheStore.make_key("author", 2, "zip") == "author:2:zip"


def test_set_then_get_valid(tmp_path) -> None:
	store = _store(tmp_path, default_ttl_days=1)
	key = FileCacheStore.make_key("novel", "1", "txt")
	store.set(key, "FILE_ID", file_name="a.txt", caption="标题")

	info = store.get_valid(key)
	assert info is not None
	assert info.file_id == "FILE_ID"
	assert info.file_name == "a.txt"
	assert info.caption == "标题"

	expires = datetime.strptime(info.expires_at, "%Y-%m-%dT%H:%M:%S%z")
	left = expires - datetime.now(timezone.utc)
	assert timedelta(hours=23) < left <= timedelta(days=1)


def test_author_fields_persist(tmp_path) -> None:
	"""作者信息跟着 file_id 一起缓存：分享记录要按作者查冷却 / 下架。"""
	path = tmp_path / "files_cache.json"
	key = FileCacheStore.make_key("novel", "1", "txt")
	FileCacheStore(path=path, default_ttl_days=1).set(
		key, "FILE_ID", author_id="456", author_name="作者A")

	info = FileCacheStore(path=path, default_ttl_days=1).get_valid(key)
	assert info is not None
	assert info.author_id == "456"
	assert info.author_name == "作者A"


def test_link_persists(tmp_path) -> None:
	"""作品链接跟着 file_id 一起缓存：分享到频道时「添加本文至书架」要用。"""
	path = tmp_path / "files_cache.json"
	key = FileCacheStore.make_key("novel", "1", "txt")
	FileCacheStore(path=path, default_ttl_days=1).set(
		key, "FILE_ID", link="https://linpx.ink/pixiv/novel/1")

	info = FileCacheStore(path=path, default_ttl_days=1).get_valid(key)
	assert info is not None
	assert info.link == "https://linpx.ink/pixiv/novel/1"


def test_missing_link_reads_as_empty(tmp_path) -> None:
	"""老缓存没有 link 字段，读出来是空串而不是 KeyError。"""
	key = FileCacheStore.make_key("novel", "1", "txt")
	store = _store(tmp_path, default_ttl_days=1)
	store.set(key, "FILE_ID")

	info = store.get_valid(key)
	assert info is not None
	assert info.link == ""


def test_zero_ttl_means_immediately_expired(tmp_path) -> None:
	"""default_ttl_days=0 不应被 or 兜底成默认 30 天。"""
	store = _store(tmp_path, default_ttl_days=0)
	key = FileCacheStore.make_key("series", "9", "zip")
	store.set(key, "FILE_ID")
	assert store.get_valid(key) is None


def test_expired_entry_is_pruned_on_write(tmp_path) -> None:
	path = tmp_path / "files_cache.json"
	old = _iso(timedelta(days=-1))
	payload = {
		"updated_at": old,
		"files": {
			"novel:1:txt": {
				"file_id": "OLD",
				"file_name": "old.txt",
				"caption": "旧",
				"uploaded_at": old,
				"expires_at": old,
			},
			"novel:2:txt": {
				"file_id": "ALIVE",
				"file_name": "alive.txt",
				"caption": "有效",
				"uploaded_at": old,
				"expires_at": _iso(timedelta(days=1)),
			},
		},
	}
	path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

	store = FileCacheStore(path=path, default_ttl_days=1)
	assert store.get_valid("novel:1:txt") is None
	assert store.get_valid("novel:2:txt") is not None

	# 过期条目在下一次写盘时真正从文件里删除
	store.set(FileCacheStore.make_key("novel", "3", "txt"), "NEW")
	raw = json.loads(path.read_text(encoding="utf-8"))
	assert "novel:1:txt" not in raw["files"]
	assert "novel:2:txt" in raw["files"]
	assert "novel:3:txt" in raw["files"]


if __name__ == "__main__":
	test_make_key()
