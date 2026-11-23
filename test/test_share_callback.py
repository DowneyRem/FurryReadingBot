"""handlers.callbacks.share：分享到频道时挂的「开源阅读」键盘。

聚焦一个真实缺口：`import_to_legado_keyboard(link)` 需要作品链接，
而分享链路只拿到 `kind;item_id`，链接必须由服务层随产物带过来。

运行（在项目根目录）:
	python -m pytest test/test_share_callback.py -q

说明：不依赖 pytest-asyncio，异步用例统一用 asyncio.run 驱动。
"""

from __future__ import annotations

import asyncio

import services.share_service as share_service_module
from handlers.callbacks import share as share_handler
from handlers.telegram import SentDocument
from policy.author import AuthorPolicy
from services.share_service import ShareService
from storage.file_cache import FileCacheStore
from storage.share_records import ShareRecordStore


NOVEL_LINK = "https://linpx.ink/pixiv/novel/1"


def run(coro):
	return asyncio.run(coro)


class FakeUser:
	id = 42
	first_name = "Alice"
	last_name = None


class FakeQuery:
	from_user = FakeUser()


class FakeUpdate:
	callback_query = FakeQuery()


class FurryLists:
	"""名单替身：所有作者都在兽人作者名单。"""

	class furrylist:
		@staticmethod
		def get_name(author_id) -> str:
			return ""

	def is_blacklisted(self, author_id) -> bool:
		return False

	def is_furryauthor(self, author_id) -> bool:
		return True


def patch_handler(monkeypatch, tmp_path, *, link=""):
	"""把 service / 上传 / 回复都换成可观测的替身。"""
	cache = FileCacheStore(
		path=tmp_path / "files_cache.json", default_ttl_days=1)
	if link:
		cache.set(
			"novel:1:txt", "FILE_ID",
			file_name="a.txt", caption="标题", link=link, author_id="456",
			score=5.0, tags=("Furry", "Gay"))
	service = ShareService(
		cache=cache,
		records=ShareRecordStore(
			path=tmp_path / "share_records.json", cooldown_days=1),
		channels=("channel",),
		support_text="频道",
		policy=AuthorPolicy(FurryLists()),
	)
	monkeypatch.setattr(share_handler, "ShareService", lambda: service)

	uploads: list[dict] = []

	async def fake_upload(update, context, **kwargs):
		uploads.append(kwargs)
		return SentDocument(file_id="FILE_ID", message_id=11)

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


def callback_data(markup) -> list[str]:
	return [
		button.callback_data
		for row in markup.inline_keyboard
		for button in row
		if button.callback_data
	]


def test_share_public_attaches_legado_keyboard(monkeypatch, tmp_path) -> None:
	uploads, replies = patch_handler(monkeypatch, tmp_path, link=NOVEL_LINK)

	run(share_handler.share_public(
		FakeUpdate(), object(), data="snp;novel;1;txt"))

	assert len(uploads) == 1
	assert uploads[0]["chat_id"] == "channel"

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


def test_share_missing_cache_does_not_upload(monkeypatch, tmp_path) -> None:
	uploads, replies = patch_handler(monkeypatch, tmp_path)

	run(share_handler.share_public(
		FakeUpdate(), object(), data="snp;novel;2;txt"))

	assert uploads == []
	assert replies == ["缓存已失效，请重新下载后再分享"]


def test_share_non_furry_replies_transit(monkeypatch, tmp_path) -> None:
	"""标签没命中 Furry：发到中转频道，挂 cfy / cfn 核验键盘。"""
	monkeypatch.setattr(share_service_module, "TRANSIT_CHANNEL", "@transit")
	uploads, replies = patch_handler(monkeypatch, tmp_path, link=NOVEL_LINK)
	# 覆盖缓存里的标签：同一部作品但没有兽人标签
	share_handler.ShareService().cache.set(
		"novel:1:txt", "FILE_ID",
		file_name="a.txt", caption="标题", link=NOVEL_LINK,
		author_id="456", score=5.0, tags=("Original",))

	run(share_handler.share_public(
		FakeUpdate(), object(), data="snp;novel;1;txt"))

	assert uploads[0]["chat_id"] == "@transit"
	assert "现已转入中转频道 @transit" in replies[0]
	assert "待核验" in uploads[0]["caption"]
	assert callback_data(uploads[0]["reply_markup"]) == [
		f"cfy;{NOVEL_LINK}", f"cfn;{NOVEL_LINK}"]


# ----- 中转卡片：cfy 放行 / cfn 不通过 -----


class FakeTransitMessage:
	def __init__(self, caption: str = "") -> None:
		self.caption = caption
		self.chat_id = "@transit"
		self.message_id = 900


class FakeTransitQuery:
	def __init__(self, caption: str = "") -> None:
		self.from_user = FakeUser()
		self.message = FakeTransitMessage(caption)


class FakeTransitUpdate:
	def __init__(self, caption: str = "") -> None:
		self.callback_query = FakeTransitQuery(caption)
		self.effective_user = FakeUser()


class FakeAuthorPolicy:
	"""作者一律可分享，避免测试依赖真实名单。"""

	class Decision:
		can_download = True

	def check(self, author_id, author_name: str = ""):
		return self.Decision()


def patch_transit(monkeypatch, tmp_path, *, admin: bool = True):
	cache = FileCacheStore(
		path=tmp_path / "files_cache.json", default_ttl_days=1)
	cache.set(
		"novel:1:txt", "FILE_ID",
		file_name="a.txt", caption="标题", link=NOVEL_LINK,
		author_id="456", author_name="作者A", score=5.0, tags=("Furry",))
	records = ShareRecordStore(
		path=tmp_path / "share_records.json", cooldown_days=1)
	records.record(
		author_id="456", author_name="作者A", kind="novel", item_id="1",
		messages=[("@transit", 900)], title="标题")

	monkeypatch.setattr(share_handler, "get_file_cache", lambda: cache)
	monkeypatch.setattr(share_handler, "get_share_records", lambda: records)
	monkeypatch.setattr(share_handler, "FURRY_NOVELS", "@novels")
	monkeypatch.setattr(share_handler, "AuthorPolicy", FakeAuthorPolicy)

	async def fake_admin(update, context, action: str) -> bool:
		return admin

	monkeypatch.setattr(share_handler, "ensure_transit_admin", fake_admin)

	uploads: list[dict] = []

	async def fake_upload(update, context, **kwargs):
		uploads.append(kwargs)
		return SentDocument(file_id="FILE_ID", message_id=11)

	monkeypatch.setattr(share_handler, "upload_file", fake_upload)

	closed: list[str] = []

	async def fake_close(update, context, text, *, reply_markup=None):
		closed.append(text)

	monkeypatch.setattr(share_handler, "close_transit_message", fake_close)
	return cache, records, uploads, closed


def test_transit_approve_sends_to_furry_novels(monkeypatch, tmp_path) -> None:
	"""cfy：发到兽人小说频道，挂开源阅读键盘，并结掉中转卡片。"""
	caption = f"{share_service_module.TRANSIT_NOTICE}\n\n标题\n\n来自 Alice 的分享"
	_cache, records, uploads, closed = patch_transit(
		monkeypatch, tmp_path, admin=True)

	run(share_handler.share_transit_approve(
		FakeTransitUpdate(caption), object(), data=f"cfy;{NOVEL_LINK}"))

	assert len(uploads) == 1
	assert uploads[0]["chat_id"] == "@novels"
	# 正式频道不带「待核验」提示
	assert uploads[0]["caption"] == "标题\n\n来自 Alice 的分享"
	assert any(
		NOVEL_LINK in url for url in keyboard_urls(uploads[0]["reply_markup"]))
	assert closed and closed[0].startswith("✅ #兽人小说已放行")
	# 记录里只剩正式频道那条，下架时才不会追一条已删的中转消息
	rows = records.by_author("456")
	assert [(row.chat_id, row.message_id) for row in rows] == [("@novels", 11)]


def test_transit_reject_closes_card(monkeypatch, tmp_path) -> None:
	"""cfn：不发正式频道，删掉卡片并留下未通过回执。"""
	_cache, records, uploads, closed = patch_transit(
		monkeypatch, tmp_path, admin=True)

	run(share_handler.share_transit_reject(
		FakeTransitUpdate(), object(), data=f"cfn;{NOVEL_LINK}"))

	assert uploads == []
	assert closed and closed[0].startswith("❌ #兽人小说未通过")
	assert records.by_author("456") == []


def test_transit_actions_require_admin(monkeypatch, tmp_path) -> None:
	"""非管理员点 cfy / cfn：既不转发也不动卡片。"""
	_cache, _records, uploads, closed = patch_transit(
		monkeypatch, tmp_path, admin=False)

	run(share_handler.share_transit_approve(
		FakeTransitUpdate(), object(), data=f"cfy;{NOVEL_LINK}"))
	run(share_handler.share_transit_reject(
		FakeTransitUpdate(), object(), data=f"cfn;{NOVEL_LINK}"))

	assert uploads == []
	assert closed == []
