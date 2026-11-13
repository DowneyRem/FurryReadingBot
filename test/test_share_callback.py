"""handlers.callbacks.share：分享到频道时挂的「开源阅读」键盘。

聚焦一个真实缺口：`import_to_legado_keyboard(link)` 需要作品链接，
而分享链路只拿到 `kind;item_id`，链接必须由服务层随产物带过来。

运行（在项目根目录）:
	python -m pytest test/test_share_callback.py -q

说明：不依赖 pytest-asyncio，异步用例统一用 asyncio.run 驱动。
"""

from __future__ import annotations

import asyncio

from handlers.callbacks import share as share_handler
from handlers.telegram import SentDocument
from services.share_service import ShareService
from storage.file_cache import FileCacheStore
from storage.share_records import ShareRecordStore


NOVEL_LINK = "https://linpx.ink/pixiv/novel/1"


def run(coro):
	return asyncio.run(coro)


class FakeUser:
	id = 42
	first_name = "Alice"


class FakeQuery:
	from_user = FakeUser()


class FakeUpdate:
	callback_query = FakeQuery()


def patch_handler(monkeypatch, tmp_path, *, link=""):
	"""把 service / 上传 / 回复都换成可观测的替身。"""
	cache = FileCacheStore(
		path=tmp_path / "files_cache.json", default_ttl_days=1)
	if link:
		cache.set(
			"novel:1:txt", "FILE_ID",
			file_name="a.txt", caption="标题", link=link, author_id="456")
	service = ShareService(
		cache=cache,
		records=ShareRecordStore(
			path=tmp_path / "share_records.json", cooldown_days=1),
		channels=("channel",),
		support_text="频道",
	)
	monkeypatch.setattr(share_handler, "ShareService", lambda: service)

	uploads: list[dict] = []

	async def fake_upload(update, context, **kwargs):
		uploads.append(kwargs)
		return {
			chat_id: SentDocument(file_id="FILE_ID", message_id=11)
			for chat_id in kwargs["chat_id"]
		}

	monkeypatch.setattr(share_handler, "upload_file", fake_upload)

	replies: list[str] = []

	async def fake_reply(update, context, text, **kwargs):
		replies.append(text)

	monkeypatch.setattr(share_handler, "reply", fake_reply)
	return uploads, replies


def keyboard_urls(markup) -> list[str]:
	return [
		button.url
		for row in markup.inline_keyboard
		for button in row
		if button.url
	]


def test_share_public_attaches_legado_keyboard(monkeypatch, tmp_path) -> None:
	uploads, replies = patch_handler(monkeypatch, tmp_path, link=NOVEL_LINK)

	run(share_handler.share_public(
		FakeUpdate(), object(), data="snp;novel;1;txt"))

	assert len(uploads) == 1
	assert uploads[0]["chat_id"] == ("channel",)

	urls = keyboard_urls(uploads[0]["reply_markup"])
	assert any(
		"legado://import/addToBookshelf" in url and NOVEL_LINK in url
		for url in urls
	), urls
	assert "已经公开分享至 channel" in replies[0]


def test_share_private_attaches_legado_keyboard(monkeypatch, tmp_path) -> None:
	uploads, replies = patch_handler(monkeypatch, tmp_path, link=NOVEL_LINK)

	run(share_handler.share_private(
		FakeUpdate(), object(), data="sna;novel;1;txt"))

	urls = keyboard_urls(uploads[0]["reply_markup"])
	assert any(NOVEL_LINK in url for url in urls)
	assert "已经匿名分享至 channel" in replies[0]


def test_share_without_cached_link_still_has_bookshelf(
		monkeypatch, tmp_path) -> None:
	"""老缓存没存 link：服务层按 kind + item_id 兜底，按钮不能空着。"""
	uploads, _replies = patch_handler(monkeypatch, tmp_path)
	cache = share_handler.ShareService().cache
	cache.set(
		"novel:1:txt", "FILE_ID",
		file_name="a.txt", caption="标题", author_id="456")

	run(share_handler.share_public(
		FakeUpdate(), object(), data="snp;novel;1;txt"))

	urls = keyboard_urls(uploads[0]["reply_markup"])
	assert any(NOVEL_LINK in url for url in urls)


def test_share_missing_cache_does_not_upload(monkeypatch, tmp_path) -> None:
	uploads, replies = patch_handler(monkeypatch, tmp_path)

	run(share_handler.share_public(
		FakeUpdate(), object(), data="snp;novel;2;txt"))

	assert uploads == []
	assert replies == ["缓存已失效，请重新下载后再分享"]
