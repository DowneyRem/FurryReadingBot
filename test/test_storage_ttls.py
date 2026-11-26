"""存储层时间参数：只来自 config，storage 里不再自带保底数值。

运行（在项目根目录）:
	.venv\\Scripts\\python.exe -m pytest test/test_storage_ttls.py -q
"""

from __future__ import annotations

import config

from storage.black_request import BlackRequestStore
from storage.fetch_cache import FetchCacheStore
from storage.file_cache import FileCacheStore
from storage.furry_request import FurryRequestStore
from storage.share_records import ShareRecordStore


def test_file_cache_ttl_comes_from_config(tmp_path) -> None:
	"""不传 default_ttl_days 时必须读 config，而不是某个类常量。"""
	store = FileCacheStore(path=tmp_path / "files_cache.json")
	assert store.default_ttl_days == config.FILE_CACHE_TTL_DAYS


def test_fetch_cache_ttl_comes_from_config(tmp_path) -> None:
	store = FetchCacheStore(path=tmp_path / "fetch_cache.json")
	assert store.default_ttl_hours == config.FETCH_CACHE_TTL_HOURS


def test_share_record_ttls_come_from_config(tmp_path) -> None:
	store = ShareRecordStore(path=tmp_path / "share_records.json")
	assert store.cooldown_days == config.SHARE_COOLDOWN_DAYS
	assert store.record_ttl_days == config.SHARE_RECORD_TTL_DAYS


def test_apply_cooldown_comes_from_config(tmp_path) -> None:
	"""申请冷却只从 config 取默认值：兽人名单 / 黑名单两个 Store 共用。"""
	furry = FurryRequestStore(path=tmp_path / "furry_request.json")
	black = BlackRequestStore(path=tmp_path / "black_request.json")
	assert furry.apply_cooldown_hours == config.APPLY_COOLDOWN_HOURS
	assert black.apply_cooldown_hours == config.APPLY_COOLDOWN_HOURS


def test_black_request_ttl_comes_from_config(tmp_path) -> None:
	store = BlackRequestStore(path=tmp_path / "black_request.json")
	assert store.material_ttl_minutes == config.BLACK_REQUEST_MATERIAL_TTL_MINUTES


def test_explicit_values_win_over_config(tmp_path) -> None:
	"""测试 / 特殊场景可以显式覆盖，0 也不会被 or 兜底掉。"""
	file_cache = FileCacheStore(path=tmp_path / "a.json", default_ttl_days=0)
	fetch_cache = FetchCacheStore(path=tmp_path / "b.json", default_ttl_hours=0)
	records = ShareRecordStore(
		path=tmp_path / "c.json", cooldown_days=0, record_ttl_days=0)
	requests = BlackRequestStore(path=tmp_path / "d.json", material_ttl_minutes=0)
	furry_requests = FurryRequestStore(
		path=tmp_path / "e.json", apply_cooldown_hours=0)
	black_requests = BlackRequestStore(
		path=tmp_path / "f.json", apply_cooldown_hours=0)

	assert file_cache.default_ttl_days == 0
	assert fetch_cache.default_ttl_hours == 0
	assert records.cooldown_days == 0
	assert records.record_ttl_days == 0
	assert requests.material_ttl_minutes == 0
	assert furry_requests.apply_cooldown_hours == 0
	assert black_requests.apply_cooldown_hours == 0
