"""ShareRecordStore：作者 → 作品 → 频道 → 消息，冷却、TTL、下架查询。

运行（在项目根目录）:
	python -m pytest test/test_share_record.py -v
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from storage.share_records import ShareRecordStore


def _store(tmp_path, **kwargs) -> ShareRecordStore:
	return ShareRecordStore(path=tmp_path / "share_records.json", **kwargs)


def _iso(delta: timedelta) -> str:
	return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%S%z")


def _record(
		store: ShareRecordStore,
		*,
		author_id="12345",
		author_name="某作者",
		kind="novel",
		item_id="1001",
		title="雨夜",
		messages=(("-1001", 812),),
		user_id=42,
		user_name="Alice",
		shared_at=None,
):
	return store.record(
		author_id=author_id,
		author_name=author_name,
		kind=kind,
		item_id=item_id,
		messages=list(messages),
		title=title,
		user_id=user_id,
		user_name=user_name,
		shared_at=shared_at,
	)


def test_make_key_and_parse_key() -> None:
	assert ShareRecordStore.make_key("novel", "123") == "novel:123"
	assert ShareRecordStore.make_key("series", 456) == "series:456"
	assert ShareRecordStore.parse_key("novel:123") == ("novel", "123")
	# 非法 kind / 缺 id 的作品 key 一律丢弃
	assert ShareRecordStore.parse_key("novels:123") is None
	assert ShareRecordStore.parse_key("novel") is None
	assert ShareRecordStore.parse_key("novel:") is None


def test_empty_store(tmp_path) -> None:
	store = _store(tmp_path)
	assert store.work("12345", "novel", "1") is None
	assert store.is_limited("12345", "novel", "1") is False
	assert store.remaining("12345", "novel", "1") == 0.0
	assert store.by_author("12345") == []


def test_record_writes_author_tree(tmp_path) -> None:
	store = _store(tmp_path, cooldown_days=1)
	_record(store)

	work = store.work("12345", "novel", "1001")
	assert work is not None
	assert work.title == "雨夜"
	assert work.share_count == 1
	assert work.first_shared_at == work.last_shared_at
	assert work.history["-1001"][0].message_id == 812
	assert work.history["-1001"][0].user_id == "42"
	assert work.history["-1001"][0].user_name == "Alice"

	assert store.is_limited("12345", "novel", "1001") is True
	assert 0 < store.remaining("12345", "novel", "1001") <= 86400


def test_share_count_counts_user_actions_not_messages(tmp_path) -> None:
	store = _store(tmp_path, cooldown_days=0)
	# 一次分享发到两个频道：share_count 只 +1，但消息两条
	_record(store, messages=(("-1001", 903), ("-1002", 889)))

	work = store.work("12345", "novel", "1001")
	assert work.share_count == 1
	assert set(work.history.keys()) == {"-1001", "-1002"}

	_record(store, messages=(("-1001", 1201),))
	work = store.work("12345", "novel", "1001")
	assert work.share_count == 2
	assert [row.message_id for row in work.history["-1001"]] == [903, 1201]
	assert work.first_shared_at <= work.last_shared_at


def test_cooldown_is_per_author_and_work(tmp_path) -> None:
	store = _store(tmp_path, cooldown_days=1)
	_record(store)
	assert store.is_limited("12345", "novel", "1001") is True
	assert store.is_limited("12345", "novel", "2002") is False
	assert store.is_limited("12345", "series", "1001") is False
	# 作者未知时落到 "-" 桶，与有作者时的记录互不影响
	assert store.is_limited("", "novel", "1001") is False

	_record(store, author_id="", author_name="")
	assert store.is_limited("", "novel", "1001") is True
	assert store.is_limited("12345", "novel", "1001") is True


def test_cooldown_expired(tmp_path) -> None:
	store = _store(tmp_path, cooldown_days=1)
	_record(store)
	assert store.is_limited("12345", "novel", "1001") is True
	assert store.is_limited("12345", "novel", "1001", cooldown_days=0) is False


def test_by_author_flattens_all_works(tmp_path) -> None:
	store = _store(tmp_path, cooldown_days=0)
	_record(store, messages=(("-1001", 903), ("-1002", 889)))
	_record(store, kind="series", item_id="55", messages=(("-1002", 912),))
	_record(store, author_id="67890", author_name="另一位", messages=(("-1001", 45),))

	rows = store.by_author("12345")
	assert len(rows) == 3
	assert {row.kind for row in rows} == {"novel", "series"}
	assert {row.chat_id for row in rows} == {"-1001", "-1002"}
	assert all(row.author_name == "某作者" for row in rows)
	assert all(row.title for row in rows)

	other = store.by_author("67890")
	assert len(other) == 1
	assert other[0].message_id == 45
	assert other[0].author_name == "另一位"

def test_remove_message_recycles_empty_nodes(tmp_path) -> None:
	store = _store(tmp_path, cooldown_days=0)
	_record(store, messages=(("-1001", 903),))
	_record(store, kind="series", item_id="55", messages=(("-1002", 912),))

	assert store.remove_message("12345", "novel", "1001", "-1001", 903) is True
	assert store.work("12345", "novel", "1001") is None
	assert store.remove_message("12345", "novel", "1001", "-1001", 903) is False
	# series 还在，作者不会被一起删掉
	assert store.work("12345", "series", "55") is not None

	assert store.remove_message("12345", "series", "55", "-1002", 912) is True
	assert store.by_author("12345") == []
	assert store.drop_author("12345") is False


def test_drop_author(tmp_path) -> None:
	store = _store(tmp_path)
	_record(store)
	assert store.drop_author("12345") is True
	assert store.work("12345", "novel", "1001") is None
	assert store.drop_author("12345") is False


def test_persist_across_instances(tmp_path) -> None:
	path = tmp_path / "share_records.json"
	_record(ShareRecordStore(path=path, cooldown_days=1), title="跨实例")

	other = ShareRecordStore(path=path, cooldown_days=1)
	work = other.work("12345", "novel", "1001")
	assert work is not None
	assert work.title == "跨实例"
	assert work.share_count == 1
	assert other.is_limited("12345", "novel", "1001") is True


def test_expired_messages_are_pruned(tmp_path) -> None:
	"""消息级 TTL：过期消息 → 空频道 → 空作品 → 空作者。"""
	path = tmp_path / "share_records.json"
	old = _iso(timedelta(days=-40))
	payload = {
		"updated_at": old,
		"shares": {
			"12345": {
				"author_name": "旧作者",
				"novel:1": {
					"title": "旧",
					"share_count": 3,
					"first_shared_at": old,
					"last_shared_at": old,
					"history": {
						"-1001": [
							{
								"message_id": 1,
								"sent_at": old,
								"user_id": "42",
								"user_name": "A",
							},
						],
					},
				},
			},
		},
	}
	path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

	store = ShareRecordStore(path=path, cooldown_days=1)
	assert store.work("12345", "novel", "1") is None
	assert store.by_author("12345") == []
	assert store.is_limited("12345", "novel", "1") is False

	# 写盘后文件里不会留下空壳作者
	_record(store)
	raw = json.loads(path.read_text(encoding="utf-8"))
	assert "12345" in raw["shares"]
	assert "novel:1" not in raw["shares"]["12345"]
	assert raw["shares"]["12345"]["novel:1001"]["share_count"] == 1

def test_legacy_layout_is_dropped(tmp_path) -> None:
	"""旧格式顶层 key 是 kind:id，不是作者；读盘时静默丢弃。"""
	path = tmp_path / "share_records.json"
	old = _iso(timedelta(days=-1))
	payload = {
		"updated_at": old,
		"shares": {
			"novel:1": {
				"kind": "novel",
				"item_id": "1",
				"last_chat_ids": ["-1001"],
				"count": 2,
				"last_shared_at": old,
			},
		},
	}
	path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

	store = ShareRecordStore(path=path, cooldown_days=1)
	assert store.by_author("novel:1") == []
	assert store.is_limited("novel:1", "novel", "1") is False

	_record(store)
	raw = json.loads(path.read_text(encoding="utf-8"))
	assert "novel:1" not in raw["shares"]


def test_derived_fields_are_recomputed_on_load(tmp_path) -> None:
	"""first / last 由 history 派生：手改 history 后读盘会自动纠正。"""
	path = tmp_path / "share_records.json"
	first = _iso(timedelta(days=-3))
	last = _iso(timedelta(days=-1))
	payload = {
		"updated_at": last,
		"shares": {
			"12345": {
				"author_name": "某作者",
				"novel:1": {
					"title": "x",
					"share_count": 2,
					"first_shared_at": "2000-01-01T00:00:00+0000",
					"last_shared_at": "2000-01-01T00:00:00+0000",
					"history": {
						"-1001": [
							{
								"message_id": 1,
								"sent_at": first,
								"user_id": "1",
								"user_name": "A",
							},
							{
								"message_id": 2,
								"sent_at": last,
								"user_id": "2",
								"user_name": "B",
							},
						],
					},
				},
			},
		},
	}
	path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

	work = ShareRecordStore(path=path).work("12345", "novel", "1")
	assert work is not None
	assert work.first_shared_at == first
	assert work.last_shared_at == last
	assert work.share_count == 2


def test_file_layout(tmp_path) -> None:
	"""落盘形状：作者按 key 排序；不存 expires_at / item_id / author_id 等冗余字段。"""
	path = tmp_path / "share_records.json"
	store = ShareRecordStore(path=path, cooldown_days=0)
	_record(store, author_id="67890", author_name="B")
	_record(store, author_id="12345", author_name="A")

	raw = json.loads(path.read_text(encoding="utf-8"))
	assert raw["updated_at"]
	assert list(raw["shares"].keys()) == ["12345", "67890"]

	node = raw["shares"]["12345"]
	assert node["author_name"] == "A"
	assert "author_id" not in node

	work = node["novel:1001"]
	assert work["title"] == "雨夜"
	assert work["share_count"] == 1
	assert work["first_shared_at"] == work["last_shared_at"]
	assert work["history"]["-1001"][0]["message_id"] == 812
	assert work["history"]["-1001"][0]["user_name"] == "Alice"
	assert "expires_at" not in work
	assert "item_id" not in work
	assert "kind" not in work
