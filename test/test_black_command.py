"""handlers.author.black：/black 命令的参数解析与下架确认键盘。

运行（在项目根目录）:
	.venv\\Scripts\\python.exe -m pytest test/test_black_command.py -q
"""

from __future__ import annotations

import asyncio

from handlers.author import black
from utils.links import get_id


AUTHOR_ID = "10809330"
AUTHOR_URL = f"https://linpx.ink/pixiv/user/{AUTHOR_ID}"


def run(coro):
	return asyncio.run(coro)


class FakeMessage:
	def __init__(self) -> None:
		self.replies: list[tuple[str, dict]] = []

	async def reply_text(self, text: str, **kwargs):
		self.replies.append((text, kwargs))


class FakeUpdate:
	def __init__(self) -> None:
		self.effective_message = FakeMessage()


class FakeContext:
	def __init__(self, *args: str) -> None:
		self.args = list(args)


def call(*args: str) -> list[tuple[str, dict]]:
	update = FakeUpdate()
	run(black(update, FakeContext(*args)))
	return update.effective_message.replies


def confirm_callback_data(replies: list[tuple[str, dict]]) -> str:
	"""取确认键盘第一个按钮的 callback_data。"""
	_, kwargs = replies[-1]
	markup = kwargs["reply_markup"]
	return markup.inline_keyboard[0][0].callback_data


def test_black_without_args_sends_usage() -> None:
	replies = call()

	assert len(replies) == 1
	text, kwargs = replies[0]
	assert "发送 Linpx 主页链接即可申请下架" in text
	assert "reply_markup" not in kwargs


def test_black_author_id_sends_confirm_keyboard() -> None:
	replies = call(AUTHOR_ID)

	text, kwargs = replies[-1]
	assert "确认发起申请吗？" in text
	assert "reply_markup" in kwargs
	assert confirm_callback_data(replies) == f"aby;{AUTHOR_URL}"

	# 与 callbacks/blacklist.py 的 aby 入口对齐：按钮数据拆开后能拿回作者 ID
	action, _, link = confirm_callback_data(replies).partition(";")
	assert action == "aby"
	assert get_id(link) == AUTHOR_ID


def test_black_author_url_sends_confirm_keyboard() -> None:
	replies = call(AUTHOR_URL)

	assert confirm_callback_data(replies) == f"aby;{AUTHOR_URL}"


def test_black_author_url_with_cache_suffix() -> None:
	"""非标准写法（/cache、www.）归一化成标准作者链接，控件数据不会超长。"""
	for link in (f"{AUTHOR_URL}/cache", f"https://www.linpx.ink/pixiv/user/{AUTHOR_ID}"):
		replies = call(link)

		assert confirm_callback_data(replies) == f"aby;{AUTHOR_URL}"


def test_black_rejects_non_author_arg() -> None:
	for arg in ("https://linpx.ink/pixiv/novel/123", "hello"):
		replies = call(arg)

		assert len(replies) == 1
		text, kwargs = replies[0]
		assert "发送 Linpx 主页链接即可申请下架" in text
		assert "reply_markup" not in kwargs
