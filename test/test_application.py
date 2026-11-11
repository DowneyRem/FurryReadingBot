"""ApplicationStore：申请记录持久化、累计、状态流转。

运行（在项目根目录）:
	python -m pytest test/test_application.py -v
"""

from __future__ import annotations

import json

from storage.application import ApplicationStore


def _store(tmp_path) -> ApplicationStore:
	return ApplicationStore(path=tmp_path / "applications.json")


def test_make_key() -> None:
	assert ApplicationStore.make_key("123") == "123"
	assert ApplicationStore.make_key(456) == "456"


def test_empty_store(tmp_path) -> None:
	store = _store(tmp_path)
	assert store.get("1") is None
	assert store.is_pending("1") is False
	assert store.records() == {}


def test_submit_then_pending(tmp_path) -> None:
	store = _store(tmp_path)
	record = store.submit(
		"123",
		author_name="作者A", link="https://linpx.ink/pixiv/novel/1",
		user_id=42, user_name="Alice",
	)

	assert record.author_id == "123"
	assert record.author_name == "作者A"
	assert record.link == "https://linpx.ink/pixiv/novel/1"
	assert record.user_id == "42"
	assert record.user_name == "Alice"
	assert record.status == ApplicationStore.STATUS_PENDING
	assert record.count == 1
	assert record.created_at
	assert record.updated_at

	assert store.is_pending("123") is True


def test_submit_accumulates_and_keeps_created_at(tmp_path) -> None:
	store = _store(tmp_path)
	first = store.submit("9", author_name="A", link="l1", user_id=1, user_name="A")
	second = store.submit("9", link="l2", user_id=2, user_name="B")

	assert second.count == 2
	assert second.created_at == first.created_at
	assert second.updated_at >= first.updated_at
	assert second.link == "l2"
	assert second.user_id == "2"
	# 新值为空时不覆盖旧值
	assert second.author_name == "A"


def test_submit_resets_status_to_pending(tmp_path) -> None:
	store = _store(tmp_path)
	store.submit("7", author_name="原名")
	store.set_status("7", ApplicationStore.STATUS_REJECTED)
	assert store.is_pending("7") is False

	record = store.submit("7", link="l")
	assert record.status == ApplicationStore.STATUS_PENDING
	assert record.count == 2


def test_persist_across_instances(tmp_path) -> None:
	path = tmp_path / "applications.json"
	ApplicationStore(path=path).submit("5", author_name="跨实例", link="l")

	other = ApplicationStore(path=path)
	info = other.get("5")
	assert info is not None
	assert info.author_name == "跨实例"
	assert other.is_pending("5") is True


def test_set_status(tmp_path) -> None:
	store = _store(tmp_path)
	store.submit("3", author_name="待审")
	assert store.set_status("3", ApplicationStore.STATUS_APPROVED) is True

	info = store.get("3")
	assert info.status == ApplicationStore.STATUS_APPROVED
	assert store.is_pending("3") is False
	assert store.set_status("404", ApplicationStore.STATUS_APPROVED) is False


def test_set_status_expected(tmp_path) -> None:
	store = _store(tmp_path)
	store.submit("4", author_name="待审")

	assert store.set_status(
		"4", ApplicationStore.STATUS_APPROVED,
		expected=ApplicationStore.STATUS_PENDING,
	) is True
	assert store.set_status(
		"4", ApplicationStore.STATUS_REJECTED,
		expected=ApplicationStore.STATUS_PENDING,
	) is False

	info = store.get("4")
	assert info.status == ApplicationStore.STATUS_APPROVED


def test_remove(tmp_path) -> None:
	store = _store(tmp_path)
	store.submit("2")
	assert store.remove("2") is True
	assert store.remove("2") is False
	assert store.get("2") is None


def test_file_layout(tmp_path) -> None:
	path = tmp_path / "applications.json"
	ApplicationStore(path=path).submit("1", author_name="单条")

	raw = json.loads(path.read_text(encoding="utf-8"))
	assert raw["updated_at"]
	assert raw["applications"]["1"]["author_name"] == "单条"
	assert raw["applications"]["1"]["status"] == ApplicationStore.STATUS_PENDING


if __name__ == "__main__":
	print("请使用 pytest 运行：python -m pytest test/test_application.py -v")
