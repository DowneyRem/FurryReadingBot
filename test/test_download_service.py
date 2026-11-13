"""DownloadService：链接检查、作者权限、缓存/抓取/保存/上传编排。

运行（在项目根目录）:
	python -m pytest test/test_download_service.py -q

说明：不依赖 pytest-asyncio，异步用例统一用 asyncio.run 驱动。
"""

from __future__ import annotations

import asyncio

import pytest

from services.download_service import (
	DownloadArtifact,
	DownloadForbiddenError,
	DownloadService,
	FormatChoice,
	DownloadInvalidLinkError,
	DownloadUnsupportedActionError,
	DownloadUnsupportedLinkError,
)
from storage.file_cache import FileCacheStore


NOVEL_LINK = "https://linpx.ink/pixiv/novel/18012577"
SERIES_LINK = "https://linpx.ink/pixiv/series/16181401"
AUTHOR_LINK = "https://linpx.ink/pixiv/user/42"


def run(coro):
	return asyncio.run(coro)


class FakeItem:
	def __init__(
		self,
		*,
		title: str = "标题",
		author_id: str = "42",
		author_name: str = "作者",
		author_url: str = AUTHOR_LINK,
		series_id: str = "",
		url: str = NOVEL_LINK,
	) -> None:
		self.title = title
		self.author_id = author_id
		self.author_name = author_name
		self.author_url = author_url
		self.series_id = series_id
		self.url = url

	def __str__(self) -> str:
		return f"{self.title}\n作者：{self.author_name}"


class FakeSource:
	def __init__(self, kind: str = "novel") -> None:
		self.kind = kind

	def is_novel_link(self, link: str) -> bool:
		return self.kind == "novel"

	def is_series_link(self, link: str) -> bool:
		return self.kind == "series"

	def is_author_link(self, link: str) -> bool:
		return self.kind == "author"

	def can_handle(self, link: str) -> bool:
		return True


class FakeList:
	def __init__(self, names: dict[str, str] | None = None) -> None:
		self.names = names or {}

	def get_name(self, author_id: str) -> str:
		return self.names.get(str(author_id), "")


class FakeListManager:
	def __init__(self, *, black=(), furry=()) -> None:
		self.black = {str(x) for x in black}
		self.furry = {str(x) for x in furry}
		self.blacklist = FakeList({x: f"黑名单{x}" for x in self.black})
		self.furrylist = FakeList({x: f"兽人{x}" for x in self.furry})

	def is_blacklisted(self, author_id: str) -> bool:
		return str(author_id) in self.black

	def is_furryauthor(self, author_id: str) -> bool:
		return str(author_id) in self.furry


def make_service(
	tmp_path,
	*,
	kind: str = "novel",
	item: FakeItem | None = None,
	save_ext: str = "txt",
	list_manager=None,
	resolve=None,
	save_calls: list | None = None,
	fetch_calls: list | None = None,
	source: bool = True,
):
	cache = FileCacheStore(
		path=tmp_path / "files_cache.json", default_ttl_days=1)
	if item is None:
		item = FakeItem(series_id="7" if kind == "novel" else "")
		if kind == "series":
			item.url = SERIES_LINK
		elif kind == "author":
			item.url = AUTHOR_LINK

	async def fake_fetch(link: str) -> FakeItem:
		if fetch_calls is not None:
			fetch_calls.append(link)
		return item

	async def fake_save(link: str, ext: str):
		if save_calls is not None:
			save_calls.append((link, ext))
		suffix = save_ext if ext in ("", "auto") else ext
		path = tmp_path / f"out.{suffix}"
		path.write_text("data", encoding="utf-8")
		return path

	async def fake_resolve(link: str, target_kind: str) -> str:
		if resolve is not None:
			return resolve(link, target_kind)
		return link

	service = DownloadService(
		cache=cache,
		fetch_fn=fake_fetch,
		save_fn=fake_save,
		resolve_link_fn=fake_resolve,
		resolve_source_fn=(lambda link: FakeSource(kind)) if source else (lambda link: None),
		list_manager=list_manager or FakeListManager(furry={"42"}),
	)
	return service, cache


def test_inspect_text_and_kind(tmp_path) -> None:
	service, _ = make_service(tmp_path, kind="novel")
	offer = run(service.inspect_text(f"请下载 {NOVEL_LINK} 谢谢"))

	assert offer.kind == "novel"
	assert offer.link == NOVEL_LINK
	assert offer.author_id == "42"
	assert offer.author_name == "作者"
	assert offer.has_series is True
	assert "标题" in offer.description


def test_inspect_text_requires_single_url(tmp_path) -> None:
	service, _ = make_service(tmp_path)
	with pytest.raises(DownloadInvalidLinkError):
		run(service.inspect_text("没有链接"))
	with pytest.raises(DownloadInvalidLinkError):
		run(service.inspect_text(f"{NOVEL_LINK} {SERIES_LINK}"))


def test_inspect_series_and_author_kinds(tmp_path) -> None:
	series_service, _ = make_service(tmp_path, kind="series")
	assert run(series_service.inspect_link(SERIES_LINK)).kind == "series"

	author_service, _ = make_service(tmp_path, kind="author")
	assert run(author_service.inspect_link(AUTHOR_LINK)).kind == "author"


def test_unsupported_source_raises(tmp_path) -> None:
	service, _ = make_service(tmp_path, source=False)
	with pytest.raises(DownloadUnsupportedLinkError):
		run(service.inspect_link(NOVEL_LINK))


def test_check_access_blacklisted(tmp_path) -> None:
	service, _ = make_service(
		tmp_path, list_manager=FakeListManager(black={"42"}))
	offer = run(service.inspect_text(NOVEL_LINK))
	access = service.check_access(offer)

	assert access.status == "blacklisted"
	assert access.author_id == "42"
	assert access.author_name == "作者"


def test_check_access_furry_and_needs_apply(tmp_path) -> None:
	service, _ = make_service(
		tmp_path, list_manager=FakeListManager(furry={"42"}))
	offer = run(service.inspect_text(NOVEL_LINK))
	assert service.check_access(offer).status == "allowed"

	other, _ = make_service(tmp_path, list_manager=FakeListManager())
	assert other.check_access(offer).status == "needs_apply"


def test_prepare_uses_cache_without_fetch(tmp_path) -> None:
	service, cache = make_service(tmp_path)
	cache.set(
		"novel:18012577:txt", "FILE_ID",
		file_name="cached.txt", caption="缓存说明", author_id="42")
	fetch_calls: list[str] = []
	save_calls: list[tuple[str, str]] = []
	service, _ = make_service(
		tmp_path, fetch_calls=fetch_calls, save_calls=save_calls)

	artifact = run(service.prepare("dn", NOVEL_LINK))

	assert isinstance(artifact, DownloadArtifact)
	assert artifact.file_id == "FILE_ID"
	assert artifact.filename == "cached.txt"
	assert artifact.caption == "缓存说明"
	assert artifact.path is None
	assert artifact.from_cache is True
	assert artifact.cache_key == "novel:18012577:txt"
	assert fetch_calls == []
	assert save_calls == []


def test_prepare_cache_miss_returns_cleanup_file(tmp_path) -> None:
	service, _ = make_service(tmp_path)
	artifact = run(service.prepare("dn", NOVEL_LINK))

	assert isinstance(artifact, DownloadArtifact)
	assert artifact.file_id is None
	assert artifact.path is not None and artifact.path.exists()
	assert artifact.filename == artifact.path.name
	assert artifact.file_type == "txt"
	assert artifact.cache_key == "novel:18012577:txt"
	assert artifact.cleanup is True
	assert artifact.caption.startswith("标题")


def test_prepare_series_auto_both_formats_needs_choice(tmp_path) -> None:
	service, cache = make_service(tmp_path, kind="series")
	cache.set("series:16181401:txt", "TXT_ID")
	cache.set("series:16181401:zip", "ZIP_ID")

	result = run(service.prepare("ds", SERIES_LINK))

	assert isinstance(result, FormatChoice)
	assert result.link == SERIES_LINK


def test_prepare_series_auto_single_format_reuses_cache(tmp_path) -> None:
	service, cache = make_service(tmp_path, kind="series")
	cache.set("series:16181401:zip", "ZIP_ID", file_name="s.zip")

	result = run(service.prepare("ds", SERIES_LINK))

	assert isinstance(result, DownloadArtifact)
	assert result.file_type == "zip"
	assert result.file_id == "ZIP_ID"
	assert result.from_cache is True


def test_prepare_auto_infers_file_type(tmp_path) -> None:
	service, _ = make_service(tmp_path, kind="series", save_ext="zip")

	artifact = run(service.prepare("ds", SERIES_LINK))

	assert isinstance(artifact, DownloadArtifact)
	assert artifact.file_type == "zip"
	assert artifact.cache_key == "series:16181401:zip"
	assert artifact.path is not None and artifact.path.suffix == ".zip"


def test_prepare_resolves_novel_to_series(tmp_path) -> None:
	def resolve(link: str, kind: str) -> str:
		return SERIES_LINK if kind == "series" else link

	service, _ = make_service(tmp_path, resolve=resolve)
	artifact = run(service.prepare("dst", NOVEL_LINK))

	assert isinstance(artifact, DownloadArtifact)
	assert artifact.target_link == SERIES_LINK
	assert artifact.item_id == "16181401"
	assert artifact.cache_key == "series:16181401:txt"


def test_prepare_invalid_target_id(tmp_path) -> None:
	service, _ = make_service(
		tmp_path, resolve=lambda link, kind: "https://linpx.ink/no-id")
	with pytest.raises(DownloadInvalidLinkError):
		run(service.prepare("dn", NOVEL_LINK))


def test_prepare_empty_link(tmp_path) -> None:
	service, _ = make_service(tmp_path)
	with pytest.raises(DownloadInvalidLinkError):
		run(service.prepare("dn", ""))


def test_unsupported_action_raises(tmp_path) -> None:
	service, _ = make_service(tmp_path)
	assert service.supports_action("dn") is True
	assert service.supports_action("xx") is False
	with pytest.raises(DownloadUnsupportedActionError):
		run(service.prepare("xx", NOVEL_LINK))


def test_deliver_uploads_then_cleans_file(tmp_path) -> None:
	service, _ = make_service(tmp_path)
	seen: list[DownloadArtifact] = []

	async def upload(artifact: DownloadArtifact) -> None:
		seen.append(artifact)

	outcome = run(service.deliver("dn", NOVEL_LINK, upload=upload))

	assert outcome.artifact is not None
	assert outcome.format_choice_link is None
	assert len(seen) == 1
	assert seen[0].path is not None
	assert not seen[0].path.exists()
	assert seen[0].cache_key == "novel:18012577:txt"


def test_deliver_cleans_file_when_upload_fails(tmp_path) -> None:
	service, _ = make_service(tmp_path)
	seen: list[DownloadArtifact] = []

	async def upload(artifact: DownloadArtifact) -> None:
		seen.append(artifact)
		raise RuntimeError("boom")

	with pytest.raises(RuntimeError):
		run(service.deliver("dn", NOVEL_LINK, upload=upload))

	assert len(seen) == 1
	assert seen[0].path is not None
	assert not seen[0].path.exists()


def test_same_link_prepare_is_serialized(tmp_path) -> None:
	"""同一链接并发 prepare 串行：后到的请求等前一个完成，再复用它的结果。"""
	cache = FileCacheStore(path=tmp_path / "files_cache.json", default_ttl_days=1)
	active = 0
	peak = 0
	saves: list[str] = []

	async def fake_fetch(link: str) -> FakeItem:
		return FakeItem()

	async def fake_save(link: str, ext: str):
		nonlocal active, peak
		active += 1
		peak = max(peak, active)
		try:
			await asyncio.sleep(0.01)
			saves.append(ext)
			path = tmp_path / f"out.{ext or 'txt'}"
			path.write_text("data", encoding="utf-8")
			return path
		finally:
			active -= 1

	async def fake_resolve(link: str, kind: str) -> str:
		return link

	service = DownloadService(
		cache=cache,
		fetch_fn=fake_fetch,
		save_fn=fake_save,
		resolve_link_fn=fake_resolve,
		resolve_source_fn=lambda link: FakeSource("series"),
		list_manager=FakeListManager(furry={"42"}),
	)

	async def main():
		return await asyncio.gather(
			service.prepare("dst", SERIES_LINK),
			service.prepare("dst", SERIES_LINK),
		)

	results = run(main())

	assert len(results) == 2
	assert peak == 1  # 同一时刻只有一路在保存
	assert len(saves) == 2  # 串行执行：第二次仍会抓取（prepare 不写 file_id 缓存）


def test_different_links_are_not_serialized(tmp_path) -> None:
	"""锁按链接生效：不同作品仍可并发，不能被一把全局锁串成一队。"""
	other_link = "https://linpx.ink/pixiv/series/16181402"

	async def fake_fetch(link: str) -> FakeItem:
		return FakeItem()

	async def fake_resolve(link: str, kind: str) -> str:
		return link

	async def main():
		both_started = asyncio.Event()
		entered = 0

		async def fake_save(link: str, ext: str):
			nonlocal entered
			entered += 1
			if entered == 2:
				both_started.set()
			# 若被串行化，第一路会在这里超时
			await asyncio.wait_for(both_started.wait(), timeout=1)
			item_id = link.rsplit("/", 1)[-1]
			path = tmp_path / f"out-{item_id}.{ext or 'txt'}"
			path.write_text("data", encoding="utf-8")
			return path

		service = DownloadService(
			cache=FileCacheStore(
				path=tmp_path / "files_cache.json", default_ttl_days=1),
			fetch_fn=fake_fetch,
			save_fn=fake_save,
			resolve_link_fn=fake_resolve,
			resolve_source_fn=lambda link: FakeSource("series"),
			list_manager=FakeListManager(furry={"42"}),
		)
		return await asyncio.gather(
			service.prepare("dst", SERIES_LINK),
			service.prepare("dst", other_link),
		)

	results = run(main())

	assert len(results) == 2
	assert results[0].item_id == "16181401"
	assert results[1].item_id == "16181402"


def test_deliver_same_link_uploads_once(tmp_path) -> None:
	"""并发 deliver 同一链接：第二个等第一个传完，直接复用它的 file_id 缓存。"""
	cache = FileCacheStore(path=tmp_path / "files_cache.json", default_ttl_days=1)
	saves: list[str] = []
	fetches: list[str] = []
	uploads: list[DownloadArtifact] = []

	async def fake_fetch(link: str) -> FakeItem:
		fetches.append(link)
		return FakeItem()

	async def fake_save(link: str, ext: str):
		saves.append(ext)
		await asyncio.sleep(0.01)
		path = tmp_path / "out.txt"
		path.write_text("data", encoding="utf-8")
		return path

	async def fake_resolve(link: str, kind: str) -> str:
		return link

	service = DownloadService(
		cache=cache,
		fetch_fn=fake_fetch,
		save_fn=fake_save,
		resolve_link_fn=fake_resolve,
		resolve_source_fn=lambda link: FakeSource("novel"),
		list_manager=FakeListManager(furry={"42"}),
	)

	async def upload(artifact: DownloadArtifact) -> None:
		uploads.append(artifact)
		# 模拟 handlers/telegram/upload.py：上传成功后写 file_id 缓存
		cache.set(
			artifact.cache_key,
			"FILE_ID",
			file_name=artifact.filename or "out.txt",
			author_id=artifact.author_id,
		)
		await asyncio.sleep(0.01)

	async def main():
		return await asyncio.gather(
			service.deliver("dn", NOVEL_LINK, upload=upload),
			service.deliver("dn", NOVEL_LINK, upload=upload),
		)

	outcomes = run(main())

	assert len(outcomes) == 2
	assert len(uploads) == 2
	assert len(saves) == 1  # 第二路命中缓存，不再抓取/落盘
	assert len(fetches) == 1
	assert sum(1 for artifact in uploads if artifact.from_cache) == 1
	cached = [artifact for artifact in uploads if artifact.from_cache][0]
	assert cached.file_id == "FILE_ID"


@pytest.mark.parametrize("cached", [False, True])
def test_deliver_refused_after_author_blacklisted(tmp_path, cached) -> None:
	"""菜单发出后作者被拉黑：旧的下载按钮（无论是否命中缓存）都不能再拿到文件。"""
	service, cache = make_service(
		tmp_path, list_manager=FakeListManager(black={"42"}))
	if cached:
		cache.set("novel:18012577:txt", "FILE_ID", file_name="a.txt", author_id="42")
	uploads: list = []

	async def upload(artifact) -> None:
		uploads.append(artifact)

	with pytest.raises(DownloadForbiddenError):
		run(service.deliver("dn", NOVEL_LINK, upload=upload))
	assert uploads == []
	assert not (tmp_path / "out.txt").exists()
