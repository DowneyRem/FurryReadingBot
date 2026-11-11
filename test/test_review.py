"""handlers.callbacks.review：审核回执、申请人通知与 ReviewService 接线。

运行（在项目根目录）:
	python -m pytest test/test_review.py -q
"""

from __future__ import annotations

import asyncio

from handlers.callbacks import review as review_handler
from handlers.callbacks.review import (
	applicant_text,
	_receipt_text,
	review_application,
)
from policy.admin import AdminDecision
from services.review_service import ReviewResult
from utils.json import JsonDict


RECORD = JsonDict(
	author_id="42",
	author_name="作者",
	user_id="1",
	user_name="Alice",
	status="pending",
)


def run(coro):
	return asyncio.run(coro)


class FakeUser:
	id = 9
	first_name = "Admin"
	last_name = "User"


class FakeUpdate:
	def __init__(self) -> None:
		self.effective_user = FakeUser()


class FakeContext:
	bot = object()


class FakeAdminPolicy:
	def __init__(self, allowed: bool) -> None:
		self.allowed = allowed

	async def check(self, user_id):
		return AdminDecision(str(user_id), self.allowed)


class FakeService:
	def __init__(self, result: ReviewResult) -> None:
		self.result = result
		self.called: dict | None = None

	def review(self, author_id, decision, *, reviewer_id, reviewer_name):
		self.called = {
			"author_id": author_id,
			"decision": decision,
			"reviewer_id": reviewer_id,
			"reviewer_name": reviewer_name,
		}
		return self.result


def patch_review(
		monkeypatch, result: ReviewResult, *, admin: bool = True):
	service = FakeService(result)
	monkeypatch.setattr(review_handler, "ReviewService", lambda: service)
	monkeypatch.setattr(
		review_handler, "transit_admin_policy",
		lambda bot: FakeAdminPolicy(admin))
	closed: list[str] = []
	notified: list[tuple[JsonDict, str]] = []

	async def fake_close(update, context, text):
		closed.append(text)

	async def fake_notify(context, record, text):
		notified.append((record, text))

	monkeypatch.setattr(review_handler, "close_transit_message", fake_close)
	monkeypatch.setattr(review_handler, "notify_applicant", fake_notify)
	return service, closed, notified


def test_applicant_text_approve() -> None:
	text = applicant_text(RECORD, approve=True)
	assert "已通过" in text
	assert "作者" in text
	assert "重新发送链接" in text


def test_applicant_text_blacklist() -> None:
	text = applicant_text(RECORD, approve=False, blacklist=True)
	assert "未通过" in text
	assert "禁止通过" in text


def test_receipt_text_approved() -> None:
	text = _receipt_text(
		ReviewResult("approved", "42", "作者", "pending", RECORD),
		FakeUser(),
	)
	assert "#兽人作者申请已完成" in text
	assert "✅ 通过" in text
	assert "🈸 申请" in text
	assert "👤 审核" in text


def test_receipt_text_blacklisted() -> None:
	text = _receipt_text(
		ReviewResult(
			"rejected", "42", "作者", "pending", RECORD, blacklisted=True),
		FakeUser(),
	)
	assert "🚫 拒绝并拉黑" in text


def test_review_application_approved(monkeypatch) -> None:
	service, closed, notified = patch_review(
		monkeypatch,
		ReviewResult("approved", "42", "作者", "pending", RECORD),
	)

	run(review_application(
		FakeUpdate(), FakeContext(), data="afa;42", decision="approve"))

	assert service.called is not None
	assert service.called["author_id"] == "42"
	assert service.called["reviewer_id"] == 9
	assert "✅ 通过" in closed[0]
	assert len(notified) == 1
	assert "已通过" in notified[0][1]


def test_review_application_missing(monkeypatch) -> None:
	_, closed, notified = patch_review(
		monkeypatch, ReviewResult("missing", "404"))

	run(review_application(
		FakeUpdate(), FakeContext(), data="afa;404", decision="approve"))

	assert "申请记录不存在" in closed[0]
	assert notified == []


def test_review_application_already_processed(monkeypatch) -> None:
	_, closed, notified = patch_review(
		monkeypatch,
		ReviewResult(
			"already_processed", "42", "作者", "approved", RECORD),
	)

	run(review_application(
		FakeUpdate(), FakeContext(), data="afa;42", decision="approve"))

	assert "该申请已处理" in closed[0]
	assert notified == []


def test_review_application_requires_admin(monkeypatch) -> None:
	service, closed, notified = patch_review(
		monkeypatch,
		ReviewResult("approved", "42", "作者", "pending", RECORD),
		admin=False,
	)

	run(review_application(
		FakeUpdate(), FakeContext(), data="afa;42", decision="approve"))

	assert service.called is None
	assert "仅中转频道管理员" in closed[0]
	assert notified == []


def test_review_application_invalid_data(monkeypatch) -> None:
	_, closed, _ = patch_review(
		monkeypatch, ReviewResult("missing", ""))

	run(review_application(
		FakeUpdate(), FakeContext(), data="afa", decision="approve"))

	assert "申请参数不完整" in closed[0]
