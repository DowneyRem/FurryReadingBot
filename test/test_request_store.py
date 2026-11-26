"""AuthorRequestStore：兽人作者申请 / 作者下架申请共用的那部分行为。

两个 Store 的 `make_key` / `get` / `records` / `remove` / `apply_remaining` /
`set_status` / `_prune` 都来自 `storage/request_store.py`，这里验证收敛后行为不变，
并钉住 `BlackRequestStore` 也有 `remove()`（以前只有 furry 有）。

运行（在项目根目录）:
	.venv\\Scripts\\python.exe -m pytest test/test_request_store.py -q
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from storage.black_request import BlackRequestStore
from storage.furry_request import FurryRequestStore
from storage.request_store import AuthorRequestStore
from utils.time import utc_now


def _furry(tmp_path, **kwargs) -> FurryRequestStore:
	return FurryRequestStore(path=tmp_path / "furry_request.json", **kwargs)


def _black(tmp_path, **kwargs) -> BlackRequestStore:
	return BlackRequestStore(path=tmp_path / "black_request.json", **kwargs)


def _set_updated_at(path: Path, data_key: str, key: str, stamp: str) -> None:
	raw = json.loads(path.read_text(encoding="utf-8"))
	raw[data_key][key]["updated_at"] = stamp
	path.write_text(json.dumps(raw, ensure_ascii=False, indent=4), encoding="utf-8")


def test_both_stores_share_the_same_base() -> None:
	assert issubclass(FurryRequestStore, AuthorRequestStore)
	assert issubclass(BlackRequestStore, AuthorRequestStore)
	# 已结束状态与淘汰白名单在基类，子类只补自己的「未结束」状态
	assert FurryRequestStore.STATUS_APPROVED == "approved"
	assert BlackRequestStore.STATUS_REJECTED == "rejected"
	assert FurryRequestStore.CLOSED_STATUSES == BlackRequestStore.CLOSED_STATUSES


def test_make_key_is_shared() -> None:
	assert FurryRequestStore.make_key(42) == "42"
	assert BlackRequestStore.make_key("42") == "42"


def test_remove_works_on_both_stores(tmp_path) -> None:
	"""`remove` 由 JsonStore 提供：下架申请 Store 以前根本没有这个方法。"""
	furry = _furry(tmp_path)
	furry.submit("1", author_name="A")
	assert furry.remove("1") is True
	assert furry.remove("1") is False
	assert furry.get("1") is None

	black = _black(tmp_path)
	black.open("2", author_name="B", user_id=1)
	assert black.remove("2") is True
	assert black.remove("2") is False
	assert black.get("2") is None


def test_set_status_expected_guards_concurrency(tmp_path) -> None:
	black = _black(tmp_path)
	black.open("9", author_name="作者", user_id=1, user_name="Alice")
	black.attach_photo("9", "PHOTO")

	assert black.set_status(
		"9", BlackRequestStore.STATUS_APPROVED,
		expected=BlackRequestStore.STATUS_REVIEW) is True
	assert black.set_status(
		"9", BlackRequestStore.STATUS_REJECTED,
		expected=BlackRequestStore.STATUS_REVIEW) is False
	assert black.get("9").status == BlackRequestStore.STATUS_APPROVED


def test_apply_remaining_is_shared(tmp_path) -> None:
	"""冷却剩余秒数走同一个基类方法（内部是 utils.time.cooldown_left）。"""
	furry = _furry(tmp_path, apply_cooldown_hours=24)
	furry.submit("1", author_name="A")
	assert 0 < furry.apply_remaining("1") <= 24 * 3600

	black = _black(tmp_path, apply_cooldown_hours=24)
	black.open("2", author_name="B", user_id=1)
	black.attach_photo("2", "PHOTO")  # 送审才起算冷却
	assert 0 < black.apply_remaining("2") <= 24 * 3600
	assert black.apply_remaining("404") == 0.0


def test_latest_material_picks_most_recent(tmp_path) -> None:
	"""同一用户出现多条待交材料时，两个查询都取 updated_at 最新的那条。"""
	path = tmp_path / "black_request.json"
	store = _black(tmp_path)
	store.open("1", author_name="作者一", user_id=7, user_name="Alice")
	store.open("2", author_name="作者二", user_id=7, user_name="Alice")

	old = (utc_now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S%z")
	_set_updated_at(path, "black_request", "1", old)
	reloaded = _black(tmp_path)

	latest = reloaded.pending_material_for_user(7)
	assert latest is not None
	assert latest.author_id == "2"
	# 查「别的作者上是否还有待交材料」：排掉当前作者，剩那条旧的
	assert reloaded.other_material_for_user(7, "2").author_id == "1"
	assert reloaded.other_material_for_user(7, "1").author_id == "2"
	assert reloaded.other_material_for_user(7, "9") is not None
	assert reloaded.other_material_for_user(404, "9") is None


if __name__ == "__main__":
	print("请使用 pytest 运行：python -m pytest test/test_request_store.py -q")
