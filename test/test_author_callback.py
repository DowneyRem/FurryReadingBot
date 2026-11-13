"""handlers.callbacks.author：ba（查看作者 / 返回）按名单决定回哪一页。

运行（在项目根目录）:
	.venv\\Scripts\\python.exe -m pytest test/test_author_callback.py -q

说明：不依赖 pytest-asyncio，异步用例统一用 asyncio.run 驱动。
"""

from __future__ import annotations

import asyncio

from handlers.callbacks import author as author_handler
from policy.author import AuthorDecision
from sources.base import Author, Novel


AUTHOR_URL = "https://linpx.ink/pixiv/user/42"
NOVEL_URL = "https://linpx.ink/pixiv/novel/7"
AUTHOR_ID = "42"


def run(coro):
	return asyncio.run(coro)


def make_author() -> Author:
	return Author(
		novel_id="7",
		novel_url=NOVEL_URL,
		novel_title="标题",
		series_id=None,
		series_url=None,
		series_title=None,
		author_id=AUTHOR_ID,
		author_url=AUTHOR_URL,
		author_name="作者",
	)


def make_novel() -> Novel:
	return Novel(
		novel_id="7",
		novel_url=NOVEL_URL,
		novel_title="标题",
		series_id=None,
		series_url=None,
		series_title=None,
		author_id=AUTHOR_ID,
		author_url=AUTHOR_URL,
		author_name="作者",
		caption="",
		content="",
		like_count=0,
		read_count=0,
		create_date="",
	)


class FakeQuery:
	def __init__(self) -> None:
		self.text: str | None = None
		self.markup = None

	async def edit_message_text(self, text, *, reply_markup=None) -> None:
		self.text = text
		self.markup = reply_markup


class FakeUpdate:
	def __init__(self) -> None:
		self.callback_query = FakeQuery()


class FakePolicy:
	"""只替换 AuthorPolicy.check，键盘仍用真实 keyboards.py 渲染。"""

	def __init__(self, status: str) -> None:
		self.status = status
		self.calls: list[tuple[str, str]] = []

	def check(self, author_id, author_name: str = "") -> AuthorDecision:
		self.calls.append((str(author_id), author_name))
		return AuthorDecision(self.status, str(author_id), author_name or str(author_id))


def patch_handler(monkeypatch, status: str, *, item=None):
	"""fetch 固定返回 item（默认真实 Author），并替换 AuthorPolicy。"""
	author = item if item is not None else make_author()
	calls: list[str] = []

	async def fake_fetch(link: str):
		calls.append(link)
		return author

	policy = FakePolicy(status)
	monkeypatch.setattr(author_handler, "fetch", fake_fetch)
	monkeypatch.setattr(author_handler, "AuthorPolicy", lambda: policy)
	return policy, calls


def actions(markup) -> set[str]:
	if markup is None:
		return set()
	return {
		button.callback_data.partition(";")[0]
		for row in markup.inline_keyboard
		for button in row
		if button.callback_data
	}


def test_back_to_author_returns_author_page_for_furry(monkeypatch) -> None:
	policy, calls = patch_handler(monkeypatch, "furry")
	update = FakeUpdate()

	run(author_handler.back_to_author(update, object(), data=f"ba;{AUTHOR_URL}"))

	assert policy.calls == [(AUTHOR_ID, "作者")]
	assert calls == [AUTHOR_URL]  # 作者链接只抓一次，不重复请求
	assert update.callback_query.text == str(make_author())
	assert "dan" in actions(update.callback_query.markup)


def test_back_to_author_returns_apply_page_for_unknown(monkeypatch) -> None:
	policy, _ = patch_handler(monkeypatch, "unknown")
	update = FakeUpdate()

	run(author_handler.back_to_author(update, object(), data=f"ba;{AUTHOR_URL}"))

	assert policy.calls == [(AUTHOR_ID, "作者")]
	assert "不在兽人作者名单" in update.callback_query.text
	assert "af" in actions(update.callback_query.markup)


def test_back_to_author_hides_buttons_for_blacklisted(monkeypatch) -> None:
	patch_handler(monkeypatch, "blacklisted")
	update = FakeUpdate()

	run(author_handler.back_to_author(update, object(), data=f"ba;{AUTHOR_URL}"))

	assert "已停止" in update.callback_query.text
	assert update.callback_query.markup is None


def test_back_to_author_fetches_author_from_novel(monkeypatch) -> None:
	novel = make_novel()
	author = make_author()
	calls: list[str] = []

	async def fake_fetch(link: str):
		calls.append(link)
		return author if link == AUTHOR_URL else novel

	policy = FakePolicy("furry")
	monkeypatch.setattr(author_handler, "fetch", fake_fetch)
	monkeypatch.setattr(author_handler, "AuthorPolicy", lambda: policy)
	update = FakeUpdate()

	run(author_handler.back_to_author(update, object(), data=f"ba;{NOVEL_URL}"))

	assert calls == [NOVEL_URL, AUTHOR_URL]  # 小说链接先换成作者链接
	assert policy.calls == [(AUTHOR_ID, "作者")]
	assert update.callback_query.text == str(author)


def test_back_to_author_skips_author_fetch_for_unknown_novel(monkeypatch) -> None:
	novel = make_novel()
	policy, calls = patch_handler(monkeypatch, "unknown", item=novel)
	update = FakeUpdate()

	run(author_handler.back_to_author(update, object(), data=f"ba;{NOVEL_URL}"))

	assert calls == [NOVEL_URL]  # 申请页不需要作者对象，Novel 自带作者字段
	assert policy.calls == [(AUTHOR_ID, "作者")]
	assert "不在兽人作者名单" in update.callback_query.text
	assert "af" in actions(update.callback_query.markup)


def test_back_to_author_skips_author_fetch_for_blacklisted_novel(monkeypatch) -> None:
	novel = make_novel()
	policy, calls = patch_handler(monkeypatch, "blacklisted", item=novel)
	update = FakeUpdate()

	run(author_handler.back_to_author(update, object(), data=f"ba;{NOVEL_URL}"))

	assert calls == [NOVEL_URL]  # 黑名单只给结论，同样不抓作者
	assert policy.calls == [(AUTHOR_ID, "作者")]
	assert "已停止" in update.callback_query.text
	assert update.callback_query.markup is None
