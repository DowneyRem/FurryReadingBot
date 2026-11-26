"""申请记录 TTL：只有已结束（通过 / 拒绝）的记录会被淘汰。

兽人作者申请（`furry_request.json`）与作者下架申请（`black_request.json`）
共用同一套语义：TTL 到期在 `_prune()` 里整条删掉，`reload()` 后下一次写盘生效。
还在流程里的记录（`pending` / `pending_material` / `pending_review`）永不自动消失。

运行（在项目根目录）:
	.venv\\Scripts\\python.exe -m pytest test/test_request_ttl.py -q
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from storage.black_request import BlackRequestStore
from storage.furry_request import FurryRequestStore
from utils.time import utc_now


def _age(path: Path, data_key: str, key: str, *, days: float) -> None:
	"""把磁盘上某条记录的 ``updated_at`` 改成 ``days`` 天前（模拟长期没人动）。"""
	raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
	stamp = (utc_now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S%z")
	raw[data_key][key]["updated_at"] = stamp
	path.write_text(json.dumps(raw, ensure_ascii=False, indent=4), encoding="utf-8")


def _closed_black_request(path: Path, status: str) -> None:
	"""造一条走完流程的下架申请：等截图 -> 交截图送审 -> 通过 / 拒绝。"""
	store = BlackRequestStore(path=path)
	store.open("9", author_name="作者", user_id=1, user_name="Alice")
	store.attach_photo("9", "PHOTO")
	store.set_status("9", status)


# ----- 兽人作者申请 -----


def test_furry_closed_request_expires(tmp_path) -> None:
	path = tmp_path / "furry_request.json"
	store = FurryRequestStore(path=path, record_ttl_days=90)
	store.submit("1", author_name="旧申请")
	store.set_status("1", FurryRequestStore.STATUS_REJECTED)
	_age(path, "furry_request", "1", days=91)

	assert FurryRequestStore(path=path, record_ttl_days=90).get("1") is None


def test_furry_approved_request_expires_too(tmp_path) -> None:
	"""通过和拒绝都算「已结束」，一样按 TTL 淘汰（名单在 furry_authors.json 里）。"""
	path = tmp_path / "furry_request.json"
	store = FurryRequestStore(path=path, record_ttl_days=90)
	store.submit("1", author_name="已通过")
	store.set_status("1", FurryRequestStore.STATUS_APPROVED)
	_age(path, "furry_request", "1", days=91)

	assert FurryRequestStore(path=path, record_ttl_days=90).get("1") is None


def test_furry_closed_request_kept_within_ttl(tmp_path) -> None:
	path = tmp_path / "furry_request.json"
	store = FurryRequestStore(path=path, record_ttl_days=90)
	store.submit("1", author_name="刚拒的")
	store.set_status("1", FurryRequestStore.STATUS_REJECTED)
	_age(path, "furry_request", "1", days=89)

	info = FurryRequestStore(path=path, record_ttl_days=90).get("1")
	assert info is not None
	assert info.status == FurryRequestStore.STATUS_REJECTED


def test_furry_pending_request_never_expires(tmp_path) -> None:
	"""待审核的申请过了多久都不能被 TTL 悄悄删掉。"""
	path = tmp_path / "furry_request.json"
	FurryRequestStore(path=path).submit("1", author_name="等审核")
	_age(path, "furry_request", "1", days=3650)

	store = FurryRequestStore(path=path, record_ttl_days=90)
	assert store.is_pending("1") is True


def test_furry_ttl_zero_drops_closed_records_only(tmp_path) -> None:
	"""0 = 立即过期（不会被 or 兜底），但只影响已结束的记录。"""
	path = tmp_path / "furry_request.json"
	store = FurryRequestStore(path=path)
	store.submit("1", author_name="已拒")
	store.set_status("1", FurryRequestStore.STATUS_REJECTED)
	store.submit("2", author_name="待审")

	reloaded = FurryRequestStore(path=path, record_ttl_days=0)
	assert reloaded.get("1") is None
	assert reloaded.is_pending("2") is True


def test_furry_prune_is_written_back_on_next_save(tmp_path) -> None:
	"""`reload()` 只清理内存，下一次写盘时文件里也不再保留过期记录。"""
	path = tmp_path / "furry_request.json"
	store = FurryRequestStore(path=path, record_ttl_days=90)
	store.submit("1", author_name="过期")
	store.set_status("1", FurryRequestStore.STATUS_REJECTED)
	_age(path, "furry_request", "1", days=91)

	reloaded = FurryRequestStore(path=path, record_ttl_days=90)
	reloaded.submit("2", author_name="新的")
	raw = json.loads(path.read_text(encoding="utf-8"))
	assert "1" not in raw["furry_request"]
	assert "2" in raw["furry_request"]


# ----- 作者下架申请 -----


def test_black_closed_request_expires(tmp_path) -> None:
	path = tmp_path / "black_request.json"
	_closed_black_request(path, BlackRequestStore.STATUS_APPROVED)
	_age(path, "black_request", "9", days=366)

	assert BlackRequestStore(path=path, record_ttl_days=365).get("9") is None


def test_black_closed_request_kept_within_ttl(tmp_path) -> None:
	path = tmp_path / "black_request.json"
	_closed_black_request(path, BlackRequestStore.STATUS_REJECTED)
	_age(path, "black_request", "9", days=364)

	info = BlackRequestStore(path=path, record_ttl_days=365).get("9")
	assert info is not None
	assert info.status == BlackRequestStore.STATUS_REJECTED


def test_black_material_request_outlives_record_ttl(tmp_path) -> None:
	"""等截图的记录不按 TTL 淘汰：窗口过期后还要被下一位申请人接手。"""
	path = tmp_path / "black_request.json"
	store = BlackRequestStore(path=path, record_ttl_days=1)
	store.open("9", author_name="作者", user_id=1, user_name="Alice")
	_age(path, "black_request", "9", days=30)

	reloaded = BlackRequestStore(path=path, record_ttl_days=1)
	record = reloaded.get("9")
	assert record is not None
	assert record.status == BlackRequestStore.STATUS_MATERIAL
	# 30 分钟的材料窗口早就过了，但记录仍在，交给下一位申请人接手
	assert reloaded.is_stale(record) is True

	taken = reloaded.open("9", user_id=2, user_name="Bob")
	assert taken.count == 2
	assert taken.previous_user_id == "1"


def test_black_pending_review_request_never_expires(tmp_path) -> None:
	path = tmp_path / "black_request.json"
	store = BlackRequestStore(path=path, record_ttl_days=1)
	store.open("9", author_name="作者", user_id=1, user_name="Alice")
	store.attach_photo("9", "PHOTO")
	_age(path, "black_request", "9", days=30)

	info = BlackRequestStore(path=path, record_ttl_days=1).get("9")
	assert info is not None
	assert info.status == BlackRequestStore.STATUS_REVIEW


def test_black_missing_timestamp_is_kept(tmp_path) -> None:
	"""旧数据没有可解析的 updated_at：宁可留着，也不静默删掉申请凭据。"""
	path = tmp_path / "black_request.json"
	_closed_black_request(path, BlackRequestStore.STATUS_APPROVED)
	raw = json.loads(path.read_text(encoding="utf-8"))
	raw["black_request"]["9"]["updated_at"] = ""
	path.write_text(json.dumps(raw, ensure_ascii=False, indent=4), encoding="utf-8")

	assert BlackRequestStore(path=path, record_ttl_days=0).get("9") is not None


if __name__ == "__main__":
	print("请使用 pytest 运行：python -m pytest test/test_request_ttl.py -q")
