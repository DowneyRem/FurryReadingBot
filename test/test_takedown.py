"""handlers.telegram.takedown：删除适配与 chat_id 归一化。

运行（在项目根目录）:
	python -m pytest test/test_takedown.py -q
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from telegram.error import BadRequest

from handlers.telegram.takedown import chat_target, delete_message


def run(coro):
	return asyncio.run(coro)


class FakeBot:
	def __init__(self, error: Exception | None = None) -> None:
		self.error = error
		self.deleted: list[tuple[int | str, int]] = []

	async def delete_message(self, *, chat_id, message_id):
		if self.error is not None:
			raise self.error
		self.deleted.append((chat_id, message_id))


def context_with(bot: FakeBot) -> SimpleNamespace:
	return SimpleNamespace(bot=bot)


def test_chat_target() -> None:
	assert chat_target("-1001234567890") == -1001234567890
	assert chat_target(-1001234567890) == -1001234567890
	assert chat_target("@furry_novels") == "@furry_novels"
	assert chat_target("") == ""


def test_delete_message_converts_chat_id() -> None:
	bot = FakeBot()
	run(delete_message(context_with(bot), "-1001234567890", 903))
	assert bot.deleted == [(-1001234567890, 903)]


def test_delete_message_treats_not_found_as_success() -> None:
	"""消息已经不存在算成功，下架才能重放。"""
	bot = FakeBot(BadRequest("Message to delete not found"))
	run(delete_message(context_with(bot), "-1001", 903))


def test_delete_message_reraises_other_errors() -> None:
	bot = FakeBot(BadRequest("Not enough rights to delete this message"))
	with pytest.raises(BadRequest):
		run(delete_message(context_with(bot), "-1001", 903))
