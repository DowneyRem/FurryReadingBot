"""ShareService：冷却、缓存、频道选择、上传与分享记录。

运行（在项目根目录）:
	python -m pytest test/test_share_service.py -q

说明：不依赖 pytest-asyncio，异步用例统一用 asyncio.run 驱动。
"""

from __future__ import annotations

import asyncio

import pytest

import services.share_service as share_service_module
from policy.author import AuthorPolicy
from services.share_service import ShareRequest, ShareService
from storage.file_cache import FileCacheStore
from storage.share_records import ShareRecordStore


def run(coro):
	return asyncio.run(coro)


class FakeList:
	def get_name(self, author_id) -> str:
		return ""


class FakeLists:
	"""名单替身：默认 456 在兽人作者名单。"""

	def __init__(self, *, black=(), furry=("456",)) -> None:
		self.black, self.furry = set(black), set(furry)
		self.blacklist = self.furrylist = FakeList()

	def is_blacklisted(self, author_id) -> bool:
		return str(author_id) in self.black

	def is_furryauthor(self, author_id) -> bool:
		return str(author_id) in self.furry


class FakeWork:
	author_id = "456"
	author_name = "作者A"


def make_service(
		tmp_path,
		*,
		lists=None,
		channels=("channel",),
		mode=None,
		support="频道",
		author_id="456",
		author_name="作者A",
		link="",
):
	cache = FileCacheStore(
		path=tmp_path / "files_cache.json", default_ttl_days=1)
	records = ShareRecordStore(
		path=tmp_path / "share_records.json", cooldown_days=1)
	service = ShareService(
		cache=cache,
		records=records,
		channels=channels,
		support_text=support,
		mode=mode,
		policy=AuthorPolicy(lists or FakeLists()),
		fetch_fn=fetch_work,
	)
	cache.set(
		"novel:1:txt", "FILE_ID",
		file_name="a.txt", caption="标题\n作者：A",
		link=link,
		author_id=author_id, author_name=author_name,
	)
	return service, cache, records


async def fetch_work(link: str) -> FakeWork:
	return FakeWork()


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


def uploader(*, message_id=903, seen=None):
	"""上传适配器：每个频道返回一个 message_id。"""

	async def upload(artifact, chat_id) -> int:
		if seen is not None:
			seen.append(artifact)
		return message_id

	return upload


def test_share_success(tmp_path) -> None:
	service, _cache, records = make_service(tmp_path)
	seen: list = []

	result = run(service.share(request(), upload=uploader(seen=seen)))

	assert result.status == "shared"
	assert result.channels == ("channel",)
	assert result.share_count == 1
	assert result.messages == (dict(chat_id="channel", message_id=903),)
	assert result.artifact is not None
	assert result.artifact.file_id == "FILE_ID"
	assert "来自 Alice 的分享" in result.artifact.caption
	assert "支持作者 频道" in result.artifact.caption
	assert len(seen) == 1

	# 记录落在作者名下，作者来自 file_id 缓存
	work = records.work("456", "novel", "1")
	assert work is not None
	assert work.share_count == 1
	assert records.by_author("456")[0].message_id == 903
	assert records.by_author("456")[0].user_name == "Alice"


def test_artifact_link_comes_from_cache(tmp_path) -> None:
	"""下载时写进缓存的 target_link 会带进分享产物，供「添加本文至书架」使用。"""
	service, _cache, _records = make_service(
		tmp_path, link="https://linpx.ink/pixiv/novel/1")
	seen: list = []

	result = run(service.share(request(), upload=uploader(seen=seen)))

	assert result.artifact is not None
	assert result.artifact.link == "https://linpx.ink/pixiv/novel/1"
	assert seen[0].link == "https://linpx.ink/pixiv/novel/1"


def test_artifact_link_falls_back_to_work_url(tmp_path) -> None:
	"""老缓存没存 link：按 kind + item_id 拼作品链接，按钮照样能用。"""
	service, _cache, _records = make_service(tmp_path)

	result = run(service.share(request(), upload=uploader()))

	assert result.artifact is not None
	assert result.artifact.link == "https://linpx.ink/pixiv/novel/1"


def test_series_artifact_link_uses_series_url(tmp_path) -> None:
	service, cache, _records = make_service(tmp_path)
	cache.set(
		FileCacheStore.make_key("series", "9", "txt"), "FILE_ID",
		author_id="456", author_name="作者A")

	result = run(service.share(
		request(kind="series", item_id="9"), upload=uploader()))

	assert result.artifact is not None
	assert result.artifact.link == "https://linpx.ink/pixiv/series/9"


def test_share_writes_one_message_per_channel(tmp_path) -> None:
	service, _cache, records = make_service(
		tmp_path, channels=("reading", "novels"))

	result = run(service.share(request(), upload=uploader(message_id=1201)))

	assert result.status == "shared"
	assert result.channels == ("reading", "novels")
	# 一次用户分享，两条消息：share_count 只 +1
	assert result.share_count == 1
	assert len(result.messages) == 2

	work = records.work("456", "novel", "1")
	assert work.share_count == 1
	assert set(work.history.keys()) == {"reading", "novels"}


def test_share_private_caption_and_record(tmp_path) -> None:
	service, _cache, records = make_service(tmp_path)

	result = run(service.share(
		request(public=False), upload=uploader()))

	assert result.status == "shared"
	assert "来自 匿名用户 的分享" in result.artifact.caption
	work = records.work("456", "novel", "1")
	assert work.history["channel"][0].user_id == "42"


def test_share_cooldown(tmp_path) -> None:
	service, _cache, _records = make_service(tmp_path)
	seen: list = []

	first = run(service.share(request(), upload=uploader(seen=seen)))
	second = run(service.share(request(), upload=uploader(seen=seen)))

	assert first.status == "shared"
	assert second.status == "cooldown"
	assert second.remaining_seconds > 0
	assert len(seen) == 1


def test_share_cache_missing(tmp_path) -> None:
	service, cache, records = make_service(tmp_path)
	cache.remove("novel:1:txt")
	seen: list = []

	result = run(service.share(request(), upload=uploader(seen=seen)))

	assert result.status == "cache_missing"
	assert seen == []
	assert records.by_author("456") == []


def test_share_no_channel(tmp_path) -> None:
	service, _cache, records = make_service(tmp_path, channels=())
	seen: list = []

	result = run(service.share(request(), upload=uploader(seen=seen)))

	assert result.status == "no_channel"
	assert seen == []
	assert records.by_author("456") == []

def test_share_without_author_fetches_author(tmp_path) -> None:
	"""老缓存没有 author_id：补拉作者再判定与记录，下架才能找到这条分享。"""
	service, _cache, records = make_service(
		tmp_path, author_id="", author_name="")

	first = run(service.share(request(), upload=uploader()))
	second = run(service.share(request(), upload=uploader()))

	assert first.status == "shared"
	assert second.status == "cooldown"
	assert records.by_author("456")[0].message_id == 903


def test_share_refused_after_author_blacklisted(tmp_path) -> None:
	"""下载后作者被拉黑：旧的分享按钮不能再发到频道。"""
	service, _cache, records = make_service(
		tmp_path, lists=FakeLists(black={"456"}))
	seen: list = []

	result = run(service.share(request(), upload=uploader(seen=seen)))

	assert result.status == "forbidden"
	assert result.author_status == "blacklisted"
	assert seen == []
	assert records.by_author("456") == []


def test_test_mode_uses_test_channel(monkeypatch, tmp_path) -> None:
	monkeypatch.setattr(share_service_module, "TEST_CHANNEL", "@test")
	service, _cache, _records = make_service(tmp_path, channels=None)

	assert service.channels(9) == ("@test",)
	assert service.channels(None) == ("@test",)


def test_prod_mode_splits_by_score(monkeypatch, tmp_path) -> None:
	monkeypatch.setattr(share_service_module, "FURRY_READING", "@reading")
	monkeypatch.setattr(share_service_module, "FURRY_NOVELS", "@novels")
	monkeypatch.setattr(share_service_module, "SHARE_SCORE_THRESHOLD", 7)
	service, _cache, records = make_service(tmp_path, channels=None, mode="prod")

	assert service.channels(9) == ("@reading", "@novels")
	assert service.channels(6) == ("@novels",)
	# 还没评分 → 按低分处理，只发兽人小说
	assert service.channels(None) == ("@novels",)

	result = run(service.share(request(score=9), upload=uploader(message_id=7)))

	assert result.status == "shared"
	assert result.channels == ("@reading", "@novels")
	assert len(result.messages) == 2
	assert set(records.work("456", "novel", "1").history.keys()) == {
		"@reading", "@novels"}


def test_share_inflight(tmp_path) -> None:
	service, _cache, _records = make_service(tmp_path)
	started = asyncio.Event()
	gate = asyncio.Event()
	uploads = []

	async def blocking_upload(artifact, chat_id):
		uploads.append(artifact)
		started.set()
		await gate.wait()
		return 1

	async def other_upload(artifact, chat_id):
		uploads.append(artifact)
		return 2

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

	async def failing_upload(artifact, chat_id):
		raise RuntimeError("boom")

	failed = run(service.share(request(), upload=failing_upload))
	assert failed.status == "failed"
	assert records.by_author("456") == []

	seen: list = []
	result = run(service.share(request(), upload=uploader(seen=seen)))

	assert result.status == "shared"
	assert len(seen) == 1
	assert records.work("456", "novel", "1").share_count == 1


def test_partial_failure_records_delivered_channels(tmp_path) -> None:
	"""一个频道失败：已发出的频道要记录并进入冷却，重试不能把它再发一遍。"""
	service, _cache, records = make_service(
		tmp_path, channels=("reading", "novels"))
	sent_to: list[str] = []

	async def flaky_upload(artifact, chat_id):
		if chat_id == "novels":
			raise RuntimeError("bot is not admin")
		sent_to.append(chat_id)
		return 77

	first = run(service.share(request(), upload=flaky_upload))
	retry = run(service.share(request(), upload=flaky_upload))

	assert first.status == "shared"
	assert first.channels == ("reading",)
	assert first.failed_channels == ("novels",)
	assert retry.status == "cooldown"
	assert sent_to == ["reading"]
	assert [m.message_id for m in records.by_author("456")] == [77]


def test_share_inflight_while_fetching_author(tmp_path) -> None:
	"""老缓存补拉作者期间连点：第二次必须被拦下，不能发两遍。"""
	service, _cache, _records = make_service(
		tmp_path, author_id="", author_name="")
	started = asyncio.Event()
	gate = asyncio.Event()

	async def slow_fetch(link):
		started.set()
		await gate.wait()
		return FakeWork()

	service._fetch = slow_fetch
	seen: list = []

	async def scenario():
		task = asyncio.create_task(service.share(request(), upload=uploader(seen=seen)))
		await started.wait()
		second = await service.share(request(), upload=uploader(seen=seen))
		gate.set()
		return await task, second

	first, second = run(scenario())

	assert first.status == "shared"
	assert second.status == "inflight"
	assert len(seen) == 1
