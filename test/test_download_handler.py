"""handlers/download.py：私聊链接 → 检查 → 文案（重点覆盖来源错误的透传）。

运行（在项目根目录）:
	.venv\\Scripts\\python.exe -m pytest test/test_download_handler.py -q

说明：只替换 `DownloadService.inspect_text`，handler 本身走真实代码；
这样 `SourceError → 提示文案` 的映射改了就会红。
"""

from __future__ import annotations

import asyncio

from handlers.download import download as download_handler
from services import (
	AuthorAccess,
	DownloadOffer,
	DownloadService,
	DownloadUnsupportedLinkError,
)
from sources.linpx.errors import LinpxNetworkError
from sources.pixiv.errors import PixivAuthError


PIXIV_NOVEL = "https://www.pixiv.net/novel/show.php?id=29588541"
LINPX_NOVEL = "https://linpx.ink/pixiv/novel/18012577"
SERIES_URL = "https://www.pixiv.net/novel/series/16747997"
AUTHOR_URL = "https://www.pixiv.net/users/15478020"


def run(coro):
	return asyncio.run(coro)


class FakeMessage:
	def __init__(self, text: str) -> None:
		self.text = text
		self.replies: list[tuple[str, dict]] = []

	async def reply_text(self, text: str, **kwargs):
		self.replies.append((text, kwargs))


class FakeUpdate:
	def __init__(self, text: str) -> None:
		self.effective_message = FakeMessage(text)


class FakeContext:
	def __init__(self) -> None:
		self.args: list[str] = []


def call(text: str, monkeypatch, error: Exception) -> list[tuple[str, dict]]:
	"""把 inspect_text 换成抛指定异常，返回 handler 的回复。"""

	async def boom(self, message_text: str):
		raise error

	monkeypatch.setattr(DownloadService, "inspect_text", boom)
	update = FakeUpdate(text)
	run(download_handler(update, FakeContext()))
	return update.effective_message.replies


def test_pixiv_auth_error_reaches_user(monkeypatch) -> None:
	"""Pixiv 登录态错误必须原样回复，不能被吞成「获取作品信息失败」。"""
	error = PixivAuthError("该作品是 R18，需要配置 PIXIV_COOKIE 才能读取正文")

	replies = call(PIXIV_NOVEL, monkeypatch, error)

	assert replies == [(str(error), {})]


def test_linpx_network_error_reaches_user(monkeypatch) -> None:
	"""两家来源都继承 SourceError：换来源不需要改 handler。"""
	error = LinpxNetworkError("Linpx 暂时无法访问，请稍后重试")

	replies = call(LINPX_NOVEL, monkeypatch, error)

	assert replies == [(str(error), {})]


def test_unsupported_link_mentions_both_sources(monkeypatch) -> None:
	replies = call(
		"https://example.com/novel/1", monkeypatch,
		DownloadUnsupportedLinkError("暂不支持该链接"))

	text, kwargs = replies[0]
	assert "Pixiv / Linpx" in text
	assert "reply_markup" not in kwargs


def test_series_link_offers_first_chapter(monkeypatch) -> None:
	"""系列链接的菜单要带上「📄 下载首章」：按钮只带系列链接，首章由服务层取。"""
	async def fake_inspect(self, message_text: str) -> DownloadOffer:
		return DownloadOffer(
			kind="series",
			link=SERIES_URL,
			description="系列名\n作者：安怀烈先",
			author_id="15478020",
			author_name="安怀烈先",
			author_url=AUTHOR_URL,
		)

	monkeypatch.setattr(DownloadService, "inspect_text", fake_inspect)
	monkeypatch.setattr(
		DownloadService, "check_access",
		lambda self, offer: AuthorAccess("allowed", "15478020", "安怀烈先"))

	update = FakeUpdate(SERIES_URL)
	run(download_handler(update, FakeContext()))

	_text, kwargs = update.effective_message.replies[0]
	rows = kwargs["reply_markup"].inline_keyboard
	data = [button.callback_data for row in rows for button in row]

	assert f"dn;{SERIES_URL}" in data
	assert [len(row) for row in rows] == [3, 3]


if __name__ == "__main__":
	print("请使用 pytest 运行：python -m pytest test/test_download_handler.py -q")
