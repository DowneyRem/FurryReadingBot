"""ShareService：冷却、缓存、频道、上传与分享记录。

运行（在项目根目录）:
	python -m pytest test/test_share_service.py -q

说明：不依赖 pytest-asyncio，异步用例统一用 asyncio.run 驱动。
"""

from __future__ import annotations

import asyncio

import pytest

from services.share_service import ShareRequest, ShareService
from storage.file_cache import FileCacheStore
from storage.share_records import ShareRecordStore


def run(coro):
	return asyncio.run(coro)


def make_service(tmp_path, *, channels=("channel",), support="频道"):
	cache = FileCacheStore(
		path=tmp_path / "files_cache.json", default_ttl_days=1)
	records = ShareRecordStore(
		path=tmp_path / "share_records.json", cooldown_days=1)
	service = ShareService(
		cache=cache,
		records=records,
		channels=channels,
		support_text=support,
	)
	cache.set(
		"novel:1:txt", "FILE_ID",
		file_name="a.txt", caption="标题\n作者：A")
	return service, cache, records


def request(**kwargs) -> ShareRequest:
	data = {
		"kind": "novel",
		"item_id": "1",
		"file_type": "txt",
		"public": True,
		"user_id": 42,
		"user_name": "Alice",
	}
	data.update(kwargs)
	return ShareRequest(**data)


def test_share_success(tmp_path) -> None:
	service, _cache, records = make_service(tmp_path)
	seen = []

	async def upload(artifact) -> None:
		seen.append(artifact)

	result = run(service.share(request(), upload=upload))

	assert result.status == "shared"
	assert result.channels == ("channel",)
	assert result.record is not None
	assert result.record.count == 1
	assert result.record.last_user_name == "Alice"
	assert result.record.last_chat_ids == ["channel"]
	assert result.artifact is not None
	assert result.artifact.file_id == "FILE_ID"
	assert "来自 Alice 的分享" in result.artifact.caption
	assert "支持作者 频道" in result.artifact.caption
	assert len(seen) == 1
	assert records.get("novel:1").count == 1


def test_share_private_caption_and_record(tmp_path) -> None:
	service, _cache, records = make_service(tmp_path)
	seen = []

	async def upload(artifact) -> None:
		seen.append(artifact)

	result = run(service.share(
		request(public=False), upload=upload))

	assert result.status == "shared"
	assert "来自 匿名用户 的分享" in result.artifact.caption
	assert result.record is not None
	assert result.record.public is False
	assert records.get("novel:1").public is False


def test_share_cooldown(tmp_path) -> None:
	service, _cache, _records = make_service(tmp_path)
	seen = []

	async def upload(artifact) -> None:
		seen.append(artifact)

	first = run(service.share(request(), upload=upload))
	second = run(service.share(request(), upload=upload))

	assert first.status == "shared"
	assert second.status == "cooldown"
	assert second.remaining_seconds > 0
	assert len(seen) == 1


def test_share_cache_missing(tmp_path) -> None:
	service, cache, records = make_service(tmp_path)
	cache.remove("novel:1:txt")
	seen = []

	async def upload(artifact) -> None:
		seen.append(artifact)

	result = run(service.share(request(), upload=upload))

	assert result.status == "cache_missing"
	assert seen == []
	assert records.get("novel:1") is None


def test_share_no_channel(tmp_path) -> None:
	service, _cache, records = make_service(tmp_path, channels=())
	seen = []

	async def upload(artifact) -> None:
		seen.append(artifact)

	result = run(service.share(request(), upload=upload))

	assert result.status == "no_channel"
	assert seen == []
	assert records.get("novel:1") is None


def test_share_inflight(tmp_path) -> None:
	service, _cache, _records = make_service(tmp_path)
	started = asyncio.Event()
	gate = asyncio.Event()
	uploads = []

	async def blocking_upload(artifact) -> None:
		uploads.append(artifact)
		started.set()
		await gate.wait()

	async def other_upload(artifact) -> None:
		uploads.append(artifact)

	async def scenario():
		task = asyncio.create_task(service.share(request(), upload=blocking_upload))
		await started.wait()
		second = await service.share(request(), upload=other_upload)
		gate.set()
		first = await task
		return first, second

	first, second = run(scenario())

	assert first.status == "shared"
	assert second.status == "inflight"
	assert len(uploads) == 1


def test_share_upload_failure_clears_inflight(tmp_path) -> None:
	service, _cache, records = make_service(tmp_path)

	async def failing_upload(artifact) -> None:
		raise RuntimeError("boom")

	with pytest.raises(RuntimeError):
		run(service.share(request(), upload=failing_upload))

	seen = []

	async def upload(artifact) -> None:
		seen.append(artifact)

	result = run(service.share(request(), upload=upload))

	assert result.status == "shared"
	assert len(seen) == 1
	assert records.get("novel:1").count == 1
