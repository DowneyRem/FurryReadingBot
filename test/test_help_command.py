"""handlers.start：`/help` 按中转频道管理员身份裁剪命令列表。

产品语义：`/help` 先过一次 `transit_admin_policy`（默认拒绝）。

	非管理员 / 查不到身份 → 只发公开命令
	creator / administrator → 公开命令 + 管理命令

运行（在项目根目录）:
	python -m pytest test/test_help_command.py -q
"""

from __future__ import annotations

import asyncio
import importlib

from handlers.start import ADMIN_COMMANDS, USER_COMMANDS, help_cmd, help_text
from policy.admin import AdminDecision


# handlers/__init__ 导出的是函数，patch 模块属性时要显式取模块
start_module = importlib.import_module("handlers.start")


def run(coro):
	return asyncio.run(coro)


class FakeUser:
	id = 9


class FakeMessage:
	def __init__(self) -> None:
		self.replies: list[str] = []

	async def reply_text(self, text: str, **kwargs) -> None:
		self.replies.append(text)


class FakeUpdate:
	def __init__(self, *, with_user: bool = True) -> None:
		self.effective_user = FakeUser() if with_user else None
		self.effective_message = FakeMessage()


class FakeContext:
	def __init__(self) -> None:
		self.bot = object()


class FakeAdminPolicy:
	def __init__(self, *, allowed: bool, status: str | None) -> None:
		self.allowed = allowed
		self.status = status

	async def check(self, user_id):
		return AdminDecision(str(user_id), self.allowed, self.status)


def patch(
		monkeypatch,
		*,
		allowed: bool = True,
		status: str | None = "administrator") -> None:
	monkeypatch.setattr(
		start_module, "transit_admin_policy",
		lambda bot: FakeAdminPolicy(allowed=allowed, status=status))


def test_public_help_hides_admin_commands() -> None:
	text = help_text(is_admin=False)

	for line in USER_COMMANDS:
		assert line in text
	for line in ADMIN_COMMANDS:
		assert line not in text


def test_admin_help_shows_all_commands() -> None:
	text = help_text(is_admin=True)

	for line in USER_COMMANDS:
		assert line in text
	for line in ADMIN_COMMANDS:
		assert line in text
	# 管理命令单独成段，与公开命令之间留空行
	assert text.splitlines()[len(USER_COMMANDS)] == ""


def test_help_command_hides_admin_commands_for_member(monkeypatch) -> None:
	patch(monkeypatch, allowed=False, status="member")
	update = FakeUpdate()

	run(help_cmd(update, FakeContext()))

	text = update.effective_message.replies[0]
	for line in ADMIN_COMMANDS:
		assert line not in text


def test_help_command_shows_admin_commands_for_admin(monkeypatch) -> None:
	patch(monkeypatch, allowed=True, status="creator")
	update = FakeUpdate()

	run(help_cmd(update, FakeContext()))

	text = update.effective_message.replies[0]
	for line in ADMIN_COMMANDS:
		assert line in text


def test_help_command_without_user_skips_admin_check(monkeypatch) -> None:
	"""没有用户信息时按非管理员处理，连身份查询都不发。"""

	def boom(bot):
		raise AssertionError("没有用户时不应查询管理员身份")

	monkeypatch.setattr(start_module, "transit_admin_policy", boom)
	update = FakeUpdate(with_user=False)

	run(help_cmd(update, FakeContext()))

	text = update.effective_message.replies[0]
	for line in ADMIN_COMMANDS:
		assert line not in text
