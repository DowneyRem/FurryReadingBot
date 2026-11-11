"""handlers.callbacks.apply：callback_data 解析、申请文案、af / afy 分支。

运行（在项目根目录）:
	python -m pytest test/test_apply.py -q

说明：不依赖 pytest-asyncio，异步用例统一用 asyncio.run 驱动。
"""

from __future__ import annotations

import asyncio

import pytest

from handlers.callbacks import apply as apply_handler
from handlers.callbacks.apply import (
	_blocked_text,
	_link_from_data,
	apply_notice,
)
from services.apply_service import (
	ApplyInspection,
	ApplyInvalidLinkError,
	ApplySubmission,
)


AUTHOR_LINK = "https://linpx.ink/pixiv/user/42"


def run(coro):
	return asyncio.run(coro)


def test_link_from_data() -> None:
	assert _link_from_data(f"af;{AUTHOR_LINK}") == AUTHOR_LINK
	assert _link_from_data(f"afy;{AUTHOR_LINK}") == AUTHOR_LINK


def test_link_from_data_incomplete() -> None:
	with pytest.raises(ApplyInvalidLinkError):
		_link_from_data("af")
	with pytest.raises(ApplyInvalidLinkError):
		_link_from_data("afy;")


def test_link_from_data_keeps_url_colons_and_query() -> None:
	link = "https://linpx.ink/pn/18012577?id=1"
	assert _link_from_data(f"af;{link}") == link


def test_apply_notice() -> None:
	text = apply_notice("某作者", "123")
	assert "某作者" in text
	assert "123" in text
	# 必须明确告知后果：可能被分享、可投诉下架、需人工核验
	assert "分享" in text
	assert "下架" in text
	assert "核验" in text
	assert "确认发起申请吗" in text


def test_blocked_text() -> None:
	black = _blocked_text("blacklisted", "某作者")
	furry = _blocked_text("already_furry", "某作者")
	assert "禁止" in black
	assert "无需申请" in furry
	assert _blocked_text("needs_confirm", "某作者") == ""


class FakeUser:
	id = 42
	first_name = "Alice"
	last_name = "Wang"


class FakeUpdate:
	def __init__(self) -> None:
		self.effective_user = FakeUser()


class FakeService:
	def __init__(self, *, inspection=None, submission=None) -> None:
		self.inspection = inspection
		self.submission = submission
		self.inspected: str | None = None
		self.submitted: dict | None = None

	async def inspect(self, link: str):
		self.inspected = link
		return self.inspection

	async def submit(self, link: str, *, user_id, user_name, send_transit=None):
		self.submitted = {
			"link": link,
			"user_id": user_id,
			"user_name": user_name,
			"send_transit": send_transit,
		}
		return self.submission


def patch_handler(monkeypatch, *, inspection=None, submission=None):
	service = FakeService(
		inspection=inspection,
		submission=submission or ApplySubmission(
			status="submitted",
			author_id="42",
			author_name="作者",
			link=AUTHOR_LINK,
			transit_sent=True,
		),
	)
	monkeypatch.setattr(apply_handler, "ApplyService", lambda: service)
	captured: list[dict] = []

	async def fake_edit(update, context, text, *, reply_markup=None):
		captured.append({"text": text, "markup": reply_markup})

	monkeypatch.setattr(apply_handler, "edit_or_reply", fake_edit)
	return service, captured


def test_apply_furry_shows_notice(monkeypatch) -> None:
	service, captured = patch_handler(
		monkeypatch,
		inspection=ApplyInspection(
			"needs_confirm", "42", "作者", AUTHOR_LINK),
	)

	run(apply_handler.apply_furry(
		FakeUpdate(), object(), data=f"af;{AUTHOR_LINK}"))

	assert service.inspected == AUTHOR_LINK
	assert captured[0]["text"] == apply_notice("作者", "42")
	assert captured[0]["markup"] is not None


def test_apply_furry_pending(monkeypatch) -> None:
	_, captured = patch_handler(
		monkeypatch,
		inspection=ApplyInspection("pending", "42", "已有", AUTHOR_LINK),
	)

	run(apply_handler.apply_furry(
		FakeUpdate(), object(), data=f"af;{AUTHOR_LINK}"))

	assert "已在审核中" in captured[0]["text"]
	assert captured[0]["markup"] is None


def test_apply_furry_blacklisted(monkeypatch) -> None:
	_, captured = patch_handler(
		monkeypatch,
		inspection=ApplyInspection("blacklisted", "42", "黑名单作者", AUTHOR_LINK),
	)

	run(apply_handler.apply_furry(
		FakeUpdate(), object(), data=f"af;{AUTHOR_LINK}"))

	assert "禁止" in captured[0]["text"]
	assert captured[0]["markup"] is None


def test_apply_furry_confirm_submits(monkeypatch) -> None:
	service, captured = patch_handler(monkeypatch)

	run(apply_handler.apply_furry_confirm(
		FakeUpdate(), object(), data=f"afy;{AUTHOR_LINK}"))

	assert captured[0]["text"] == "正在提交申请，请稍候……"
	assert "已提交" in captured[-1]["text"]
	assert "作者" in captured[-1]["text"]
	assert service.submitted is not None
	assert service.submitted["user_id"] == 42
	assert service.submitted["user_name"] == "Alice Wang"


def test_apply_furry_confirm_pending(monkeypatch) -> None:
	service, captured = patch_handler(
		monkeypatch,
		submission=ApplySubmission(
			status="pending",
			author_id="42",
			author_name="作者",
			link=AUTHOR_LINK,
		),
	)

	run(apply_handler.apply_furry_confirm(
		FakeUpdate(), object(), data=f"afy;{AUTHOR_LINK}"))

	assert service.submitted is not None
	assert "请勿重复提交" in captured[-1]["text"]


def test_apply_furry_confirm_invalid_data(monkeypatch) -> None:
	service, captured = patch_handler(monkeypatch)

	run(apply_handler.apply_furry_confirm(
		FakeUpdate(), object(), data="afy;"))

	assert "无法从链接中解析作者 ID" in captured[0]["text"]
	assert service.submitted is None


if __name__ == "__main__":
	print("请使用 pytest 运行：python -m pytest test/test_apply.py -q")
