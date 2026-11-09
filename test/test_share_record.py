"""ShareRecordStore：冷却窗口、TTL、持久化。

运行（在项目根目录）:
	python -m pytest test/test_share_record.py -v
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from storage.share_record import ShareRecordStore


def _store(tmp_path, **kwargs) -> ShareRecordStore:
	return ShareRecordStore(path=tmp_path / "share_records.json", **kwargs)


def _iso(delta: timedelta) -> str:
	return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%S%z")


def test_make_key() -> None:
	assert ShareRecordStore.make_key("novel", "123") == "novel:123"
	assert ShareRecordStore.make_key("series", 456) == "series:456"


def test_empty_store(tmp_path) -> None:
	store = _store(tmp_path)
	assert store.get("novel:1") is None
	assert store.is_limited("novel:1") is False
	assert store.remaining("novel:1") == 0.0
	assert store.records() == {}


def test_record_then_limited(tmp_path) -> None:
	store = _store(tmp_path, cooldown_days=1)
	key = ShareRecordStore.make_key("novel", "123")
	store.record(
		key,
		kind="novel", item_id="123", title="标题",
		user_id=42, user_name="Alice",
		chat_ids="@channel", file_type="txt", public=True,
	)

	info = store.get(key)
	assert info is not None
	assert info.kind == "novel"
	assert info.item_id == "123"
	assert info.title == "标题"
	assert info.count == 1
	assert info.last_user_id == "42"
	assert info.last_user_name == "Alice"
	assert info.last_chat_ids == ["@channel"]
	assert info.last_file_type == "txt"
	assert info.public is True

	assert store.is_limited(key) is True
	assert 0 < store.remaining(key) <= 86400


def test_cooldown_expired(tmp_path) -> None:
	store = _store(tmp_path, cooldown_days=1)
	key = ShareRecordStore.make_key("novel", "1")
	store.record(key, kind="novel", item_id="1")
	assert store.is_limited(key) is True
	assert store.is_limited(key, cooldown_days=0) is False


def test_limited_is_per_key_and_ignores_file_type(tmp_path) -> None:
	store = _store(tmp_path, cooldown_days=1)
	store.record("novel:1", kind="novel", item_id="1", file_type="txt")
	assert store.is_limited("novel:1") is True
	assert store.is_limited("novel:2") is False
	assert store.is_limited("series:1") is False
	# 同一作品的 txt / zip 共用 kind:id，缓存 key 不同也不会绕过冷却
	assert store.is_limited("series:1", cooldown_days=0) is False


def test_record_accumulates(tmp_path) -> None:
	store = _store(tmp_path, cooldown_days=0)
	key = ShareRecordStore.make_key("series", "789")
	first = store.record(key, kind="series", item_id="789", user_name="A")
	second = store.record(
		key, kind="series", item_id="789", user_name="B", public=False)

	assert second.count == 2
	assert second.first_shared_at == first.first_shared_at
	assert second.last_user_name == "B"
	assert second.public is False


def test_persist_across_instances(tmp_path) -> None:
	path = tmp_path / "share_records.json"
	key = ShareRecordStore.make_key("novel", "9")
	ShareRecordStore(path=path, cooldown_days=1).record(
		key, kind="novel", item_id="9", title="跨实例")

	other = ShareRecordStore(path=path, cooldown_days=1)
	info = other.get(key)
	assert info is not None
	assert info.title == "跨实例"
	assert info.count == 1
	assert other.is_limited(key) is True


def test_expired_record_is_pruned(tmp_path) -> None:
	path = tmp_path / "share_records.json"
	old = _iso(timedelta(days=-40))
	payload = {
		"updated_at": old,
		"shares": {
			"novel:1": {
				"kind": "novel",
				"item_id": "1",
				"title": "旧",
				"first_shared_at": old,
				"last_shared_at": old,
				"expires_at": old,
				"count": 3,
				"last_user_id": "1",
				"last_user_name": "A",
				"last_chat_ids": ["@c"],
				"last_file_type": "txt",
				"public": True,
			},
		},
	}
	path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

	store = ShareRecordStore(path=path, cooldown_days=1)
	assert store.get("novel:1") is None
	assert store.is_limited("novel:1") is False
	assert store.records() == {}


def test_remove(tmp_path) -> None:
	store = _store(tmp_path, cooldown_days=1)
	key = ShareRecordStore.make_key("novel", "5")
	store.record(key, kind="novel", item_id="5")
	assert store.remove(key) is True
	assert store.remove(key) is False
	assert store.is_limited(key) is False
