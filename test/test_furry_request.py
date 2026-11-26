"""FurryRequestStore：申请记录持久化、累计、状态流转。

运行（在项目根目录）:
	python -m pytest test/test_furry_request.py -v
"""

from __future__ import annotations

import json

from storage.furry_request import FurryRequestStore


def _store(tmp_path) -> FurryRequestStore:
	return FurryRequestStore(path=tmp_path / "furry_request.json")


def test_make_key() -> None:
	assert FurryRequestStore.make_key("123") == "123"
	assert FurryRequestStore.make_key(456) == "456"


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
	assert record.status == FurryRequestStore.STATUS_PENDING
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
	store.set_status("7", FurryRequestStore.STATUS_REJECTED)
	assert store.is_pending("7") is False

	record = store.submit("7", link="l")
	assert record.status == FurryRequestStore.STATUS_PENDING
	assert record.count == 2


def test_apply_remaining_after_submit(tmp_path) -> None:
	"""提交后进入 1 天冷却；没有记录的作者不受限。"""
	store = _store(tmp_path)
	store.submit("123", author_name="作者A")

	assert 0 < store.apply_remaining("123") <= 24 * 3600
	assert store.apply_remaining("404") == 0.0


def test_apply_remaining_survives_status_change(tmp_path) -> None:
	"""审核只改状态、不刷新申请时间：被拒后仍然处在冷却里。"""
	store = _store(tmp_path)
	store.submit("123", author_name="作者A")
	store.set_status("123", FurryRequestStore.STATUS_REJECTED)

	info = store.get("123")
	assert info.last_apply_at
	assert store.apply_remaining("123") > 0


def test_apply_remaining_disabled(tmp_path) -> None:
	"""显式传 0 = 不冷却（测试 / 特殊场景）。"""
	store = FurryRequestStore(
		path=tmp_path / "no_cooldown.json", apply_cooldown_hours=0)
	store.submit("123")

	assert store.apply_remaining("123") == 0.0


def test_persist_across_instances(tmp_path) -> None:
	path = tmp_path / "furry_request.json"
	FurryRequestStore(path=path).submit("5", author_name="跨实例", link="l")

	other = FurryRequestStore(path=path)
	info = other.get("5")
	assert info is not None
	assert info.author_name == "跨实例"
	assert other.is_pending("5") is True


def test_set_status(tmp_path) -> None:
	store = _store(tmp_path)
	store.submit("3", author_name="待审")
	assert store.set_status("3", FurryRequestStore.STATUS_APPROVED) is True

	info = store.get("3")
	assert info.status == FurryRequestStore.STATUS_APPROVED
	assert store.is_pending("3") is False
	assert store.set_status("404", FurryRequestStore.STATUS_APPROVED) is False


def test_set_status_expected(tmp_path) -> None:
	store = _store(tmp_path)
	store.submit("4", author_name="待审")

	assert store.set_status(
		"4", FurryRequestStore.STATUS_APPROVED,
		expected=FurryRequestStore.STATUS_PENDING,
	) is True
	assert store.set_status(
		"4", FurryRequestStore.STATUS_REJECTED,
		expected=FurryRequestStore.STATUS_PENDING,
	) is False

	info = store.get("4")
	assert info.status == FurryRequestStore.STATUS_APPROVED


def test_remove(tmp_path) -> None:
	store = _store(tmp_path)
	store.submit("2")
	assert store.remove("2") is True
	assert store.remove("2") is False
	assert store.get("2") is None


def test_file_layout(tmp_path) -> None:
	path = tmp_path / "furry_request.json"
	FurryRequestStore(path=path).submit("1", author_name="单条")

	raw = json.loads(path.read_text(encoding="utf-8"))
	assert raw["updated_at"]
	assert raw["furry_request"]["1"]["author_name"] == "单条"
	assert raw["furry_request"]["1"]["status"] == FurryRequestStore.STATUS_PENDING
	# 1 天冷却的起点：只由「提交申请」写入
	assert raw["furry_request"]["1"]["last_apply_at"]


if __name__ == "__main__":
	print("请使用 pytest 运行：python -m pytest test/test_furry_request.py -v")
