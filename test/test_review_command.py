"""handlers.review：/review 命令的管理员校验与重推。

运行（在项目根目录）:
	python -m pytest test/test_review_command.py -q
"""

from __future__ import annotations

import asyncio
import importlib

from handlers.review import review as review_command
from policy.admin import AdminDecision

# handlers/__init__ 导出的 review 是函数，会遮住同名子模块，这里显式取模块
review_module = importlib.import_module("handlers.review")


def run(coro):
	return asyncio.run(coro)


class FakeUser:
	id = 9
	first_name = "Admin"
	last_name = "User"


class FakeMessage:
	def __init__(self) -> None:
		self.replies: list[str] = []

	async def reply_text(self, text: str, **kwargs) -> None:
		self.replies.append(text)


class FakeUpdate:
	def __init__(self) -> None:
		self.effective_user = FakeUser()
		self.effective_message = FakeMessage()


class FakeContext:
	bot = object()


class FakeAdminPolicy:
	def __init__(self, allowed: bool) -> None:
		self.allowed = allowed

	async def check(self, user_id):
		return AdminDecision(str(user_id), self.allowed)


class FakeApplyService:
	def __init__(self, records: list | None = None) -> None:
		self._records = records or []

	def pending_records(self) -> list:
		return self._records


class FakeBlacklistService:
	def __init__(self, records: list | None = None) -> None:
		self._records = records or []

	def pending_review_records(self) -> list:
		return self._records


def patch_review_command(
		monkeypatch, *,
		admin: bool = True,
		records: list | None = None,
		takedown: list | None = None,
		sent: list | None = None) -> None:
	monkeypatch.setattr(
		review_module, "transit_admin_policy", lambda bot: FakeAdminPolicy(admin))
	monkeypatch.setattr(
		review_module, "ApplyService", lambda: FakeApplyService(records))
	# 下架申请也读默认 Store：不 patch 会去读真实的 data/black_request.json，
	# 结果取决于本地数据，测试会时绿时红
	monkeypatch.setattr(
		review_module, "BlacklistService", lambda: FakeBlacklistService(takedown))

	async def fake_send(update, context, record) -> bool:
		if sent is not None:
			sent.append(record)
		return True

	async def fake_send_card(context, record) -> bool:
		if sent is not None:
			sent.append(record)
		return True

	monkeypatch.setattr(review_module, "send_to_transit", fake_send)
	monkeypatch.setattr(review_module, "send_blacklist_card", fake_send_card)


def test_review_command_requires_admin(monkeypatch) -> None:
	patch_review_command(monkeypatch, admin=False)
	update = FakeUpdate()

	run(review_command(update, FakeContext()))

	assert "仅中转频道管理员" in update.effective_message.replies[0]


def test_review_command_repushes_pending(monkeypatch) -> None:
	sent: list = []
	patch_review_command(monkeypatch, records=[{"author_id": "42"}], sent=sent)
	update = FakeUpdate()

	run(review_command(update, FakeContext()))

	assert len(sent) == 1
	assert "1/1" in update.effective_message.replies[-1]


def test_review_command_repushes_takedown(monkeypatch) -> None:
	"""下架申请也走注入的 service，不再依赖真实 data/black_request.json。"""
	sent: list = []
	patch_review_command(
		monkeypatch, records=[], takedown=[{"author_id": "42"}], sent=sent)
	update = FakeUpdate()

	run(review_command(update, FakeContext()))

	assert len(sent) == 1
	assert "1/1" in update.effective_message.replies[-1]
	assert "作者下架 1" in update.effective_message.replies[-1]


def test_review_command_without_pending(monkeypatch) -> None:
	patch_review_command(monkeypatch, records=[])
	update = FakeUpdate()

	run(review_command(update, FakeContext()))

	assert "没有待审核" in update.effective_message.replies[0]
