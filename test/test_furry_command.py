
"""handlers.author.furry：/furry 命令的参数解析与申请确认键盘。

命令复用 `handlers.callbacks.apply · apply_furry`（即按钮 `af` 的入口），
所以状态拦截（已拉黑 / 已在名单 / 审核中）与按钮流程一致。

运行（在项目根目录）:
	.venv\\Scripts\\python.exe -m pytest test/test_furry_command.py -q
"""

from __future__ import annotations

import asyncio

from handlers.author import furry
from handlers.callbacks import apply as apply_handler
from services.apply_service import ApplyInspection


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
		self.callback_query = None


class FakeContext:
	def __init__(self, *args: str) -> None:
		self.args = list(args)


class FakeApplyService:
	def __init__(self, *, inspection=None, error: Exception | None = None) -> None:
		self.inspection = inspection
		self.error = error
		self.inspected: str | None = None

	async def inspect(self, link: str):
		self.inspected = link
		if self.error is not None:
			raise self.error
		return self.inspection


def call(*args: str) -> list[tuple[str, dict]]:
	update = FakeUpdate()
	run(furry(update, FakeContext(*args)))
	return update.effective_message.replies


def patch_service(monkeypatch, **kwargs) -> FakeApplyService:
	service = FakeApplyService(**kwargs)
	monkeypatch.setattr(apply_handler, "ApplyService", lambda: service)
	return service


def test_furry_without_args_sends_usage() -> None:
	replies = call()

	assert len(replies) == 1
	text, kwargs = replies[0]
	assert "申请加入兽人作者名单" in text
	assert "reply_markup" not in kwargs


def test_furry_author_id_sends_confirm_keyboard(monkeypatch) -> None:
	service = patch_service(
		monkeypatch,
		inspection=ApplyInspection("needs_confirm", AUTHOR_ID, "某作者", AUTHOR_URL),
	)

	replies = call(AUTHOR_ID)

	assert service.inspected == AUTHOR_URL
	text, kwargs = replies[-1]
	assert "某作者" in text
	assert "#a" + AUTHOR_ID in text
	assert "确认发起申请吗" in text
	markup = kwargs["reply_markup"]
	assert markup.inline_keyboard[0][0].callback_data == f"afy;{AUTHOR_URL}"


def test_furry_author_url_sends_confirm_keyboard(monkeypatch) -> None:
	service = patch_service(
		monkeypatch,
		inspection=ApplyInspection("needs_confirm", AUTHOR_ID, "某作者", AUTHOR_URL),
	)

	replies = call(f"{AUTHOR_URL}/cache")

	assert service.inspected == AUTHOR_URL
	markup = replies[-1][1]["reply_markup"]
	assert markup.inline_keyboard[0][0].callback_data == f"afy;{AUTHOR_URL}"


def test_furry_already_furry_has_no_keyboard(monkeypatch) -> None:
	patch_service(
		monkeypatch,
		inspection=ApplyInspection("already_furry", AUTHOR_ID, "某作者", AUTHOR_URL),
	)

	replies = call(AUTHOR_ID)

	text, kwargs = replies[-1]
	assert "无需申请" in text
	assert kwargs.get("reply_markup") is None


def test_furry_blacklisted_has_no_keyboard(monkeypatch) -> None:
	patch_service(
		monkeypatch,
		inspection=ApplyInspection("blacklisted", AUTHOR_ID, "某作者", AUTHOR_URL),
	)

	replies = call(AUTHOR_ID)

	text, kwargs = replies[-1]
	assert "禁止" in text
	assert kwargs.get("reply_markup") is None


def test_furry_rejects_non_author_arg() -> None:
	for arg in ("https://linpx.ink/pixiv/novel/123", "hello"):
		replies = call(arg)

		assert len(replies) == 1
		text, kwargs = replies[0]
		assert "申请加入兽人作者名单" in text
		assert "reply_markup" not in kwargs


def test_furry_inspect_failure_replies_fallback(monkeypatch) -> None:
	patch_service(monkeypatch, error=RuntimeError("linpx down"))

	replies = call(AUTHOR_ID)

	text, kwargs = replies[-1]
	assert "获取作者信息失败" in text
	assert "reply_markup" not in kwargs
