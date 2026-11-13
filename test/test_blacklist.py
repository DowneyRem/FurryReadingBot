"""handlers：作者下架申请（ab / aby / rby / rbn）与截图提交。

运行（在项目根目录）:
	python -m pytest test/test_blacklist.py -q
"""

from __future__ import annotations

import asyncio

from handlers import media as media_handler
from handlers.callbacks import blacklist as blacklist_handler
from handlers.callbacks.blacklist import (
	applicant_text,
	material_notice,
	request_blacklist,
	request_blacklist_confirm,
	review_blacklist,
	review_receipt,
	takedown_notice,
)
from handlers.telegram.transit import blacklist_caption
from keyboards import review_black_keyboard
from policy.admin import AdminDecision
from services.blacklist_service import (
	BlacklistRequest,
	BlacklistReview,
	MaterialSubmission,
)
from services.takedown_service import TakedownResult
from utils.json import JsonDict


AUTHOR_URL = "https://linpx.ink/pixiv/user/42"
RECORD = JsonDict(
	author_id="42", author_name="作者", user_id="7", user_name="Alice")


def run(coro):
	return asyncio.run(coro)


class FakeUser:
	id = 9
	first_name = "Admin"
	last_name = "User"


class FakeMessage:
	def __init__(self, file_id: str = "PHOTO") -> None:
		self.photo = [FakePhoto(file_id)]
		self.replies: list[str] = []

	async def reply_text(self, text: str, **kwargs) -> None:
		self.replies.append(text)


class FakePhoto:
	def __init__(self, file_id: str) -> None:
		self.file_id = file_id


class FakeUpdate:
	def __init__(self, message=None) -> None:
		self.effective_user = FakeUser()
		self.effective_message = message
		self.callback_query = None


class FakeContext:
	bot = object()


class FakeAdmin:
	def __init__(self, allowed: bool) -> None:
		self.allowed = allowed

	async def check(self, user_id):
		return AdminDecision(str(user_id), self.allowed)


class FakeService:
	def __init__(self, *, request=None, submission=None, review=None) -> None:
		self.request_result = request
		self.submission_result = submission
		self.review_result = review
		self.calls: list[tuple] = []

	def request(self, author_id, **kwargs):
		self.calls.append(("request", str(author_id), kwargs))
		return self.request_result

	def submit_material(self, user_id, file_id):
		self.calls.append(("submit", user_id, file_id))
		return self.submission_result

	def review(self, author_id, decision):
		self.calls.append(("review", str(author_id), decision))
		return self.review_result


async def _no_name() -> str:
	return ""


def patch_handler(
		monkeypatch, *,
		service=None,
		admin: bool = True,
		takedown: TakedownResult | None = None,
		takedown_error: Exception | None = None,
):
	service = service or FakeService()
	monkeypatch.setattr(blacklist_handler, "BlacklistService", lambda: service)
	monkeypatch.setattr(
		blacklist_handler, "transit_admin_policy", lambda bot: FakeAdmin(admin))
	monkeypatch.setattr(
		blacklist_handler, "_author_name", lambda link: _no_name())
	replies: list[tuple[str, object]] = []
	closed: list[str] = []
	notified: list[tuple[JsonDict, str]] = []
	takedowns: list[str] = []

	async def fake_edit(update, context, text, *, reply_markup=None):
		replies.append((text, reply_markup))

	async def fake_close(update, context, text):
		closed.append(text)

	async def fake_notify(context, record, text):
		notified.append((record, text))

	async def fake_takedown(context, author_id):
		takedowns.append(str(author_id))
		if takedown_error is not None:
			raise takedown_error
		if takedown is not None:
			return takedown
		return TakedownResult(str(author_id), deleted=2)

	monkeypatch.setattr(blacklist_handler, "edit_or_reply", fake_edit)
	monkeypatch.setattr(blacklist_handler, "close_transit_message", fake_close)
	monkeypatch.setattr(blacklist_handler, "notify_applicant", fake_notify)
	monkeypatch.setattr(blacklist_handler, "takedown_author", fake_takedown)
	return service, replies, closed, notified, takedowns


def test_material_notice_contains_requirements() -> None:
	text = material_notice("作者", "42")
	assert "Pixiv 后台数据" in text
	assert "截图" in text
	assert "30 分钟" in text


def test_receipt_and_applicant_text() -> None:
	approved = BlacklistReview("approved", "42", "作者", RECORD)
	text = review_receipt(approved, FakeUser())
	assert "🈲 #作者下架申请已通过" in text
	assert "🚫 已下架：作者（#a42）" in text
	assert "🈸 申请人：Alice（#u7）" in text
	assert "👤 审核人：Admin User（#u9）" in text
	assert "已通过" in applicant_text(approved)

	rejected = BlacklistReview("rejected", "42", "作者", RECORD)
	text = review_receipt(rejected, FakeUser())
	assert "🈲 #作者下架申请已拒绝" in text
	assert "❌ 已拒绝：作者（#a42）" in text
	assert "未通过" in applicant_text(rejected)


def test_takedown_notice_variants() -> None:
	assert takedown_notice(None) == ""
	# total 为 0 时仍保留一行「已删除：0 条」，回执始终带下架结果
	assert "已删除：0 条历史分享" in takedown_notice(TakedownResult("42"))

	partial = TakedownResult("42", deleted=2, skipped=1, failed=3)
	notice = takedown_notice(partial)
	assert "已删除：2 条历史分享" in notice
	assert "1 条旧记录没有消息 ID" in notice
	assert "3 条删除失败" in notice


def test_receipt_reports_takedown() -> None:
	approved = BlacklistReview("approved", "42", "作者", RECORD)
	takedown = TakedownResult("42", deleted=2)

	assert "已删除：2 条历史分享" in review_receipt(
		approved, FakeUser(), takedown)
	assert "历史分享已删除 2 条" in applicant_text(approved, takedown)


def test_blacklist_card_uses_takedown_wording() -> None:
	record = JsonDict(
		author_id="42", author_name="作者", author_url=AUTHOR_URL,
		user_id="7", user_name="Alice", count=2)

	text = blacklist_caption(record)
	assert "🈲 #作者下架申请" in text
	assert "👤 作者名称：作者（#a42）" in text
	assert f"🏡 主页链接：{AUTHOR_URL}" in text
	assert "🈸 申请用户：Alice（#u7）" in text
	assert "🔢 申请次数：2" in text
	assert "再决定是否下架" in text

	buttons = [
		button
		for row in review_black_keyboard("42").inline_keyboard
		for button in row
	]
	assert [button.text for button in buttons] == [
		"🈲 下架", "❌ 拒绝", "🏡 主页"]
	assert [button.callback_data for button in buttons[:2]] == [
		"rby;42", "rbn;42"]


def test_request_blacklist_shows_confirm(monkeypatch) -> None:
	_, replies, _, _, _ = patch_handler(monkeypatch)

	run(request_blacklist(
		FakeUpdate(), FakeContext(), data=f"ab;{AUTHOR_URL}"))

	assert "确认发起申请吗" in replies[0][0]
	buttons = [
		button.callback_data
		for row in replies[0][1].inline_keyboard for button in row
	]
	assert f"aby;{AUTHOR_URL}" in buttons


def test_request_blacklist_bad_link(monkeypatch) -> None:
	_, replies, _, _, _ = patch_handler(monkeypatch)

	run(request_blacklist(FakeUpdate(), FakeContext(), data="ab;"))

	assert "无法从链接中解析作者 ID" in replies[0][0]


def test_confirm_needs_material(monkeypatch) -> None:
	service, replies, _, _, _ = patch_handler(
		monkeypatch,
		service=FakeService(
			request=BlacklistRequest("needs_material", "42", "作者")))

	run(request_blacklist_confirm(
		FakeUpdate(), FakeContext(), data=f"aby;{AUTHOR_URL}"))

	assert service.calls[0][0] == "request"
	assert service.calls[0][1] == "42"
	assert "Pixiv 后台数据" in replies[-1][0]
	assert "30 分钟" in replies[-1][0]


def test_confirm_pending_review(monkeypatch) -> None:
	_, replies, _, _, _ = patch_handler(
		monkeypatch,
		service=FakeService(
			request=BlacklistRequest("pending_review", "42", "作者")))

	run(request_blacklist_confirm(
		FakeUpdate(), FakeContext(), data=f"aby;{AUTHOR_URL}"))

	assert "已在核验中" in replies[-1][0]


def test_confirm_already_blacklisted(monkeypatch) -> None:
	_, replies, _, _, _ = patch_handler(
		monkeypatch,
		service=FakeService(
			request=BlacklistRequest("already_blacklisted", "42", "作者")))

	run(request_blacklist_confirm(
		FakeUpdate(), FakeContext(), data=f"aby;{AUTHOR_URL}"))

	assert "已停止分享" in replies[-1][0]

def test_review_requires_admin(monkeypatch) -> None:
	service, _, closed, notified, takedowns = patch_handler(
		monkeypatch, admin=False)

	run(review_blacklist(
		FakeUpdate(), FakeContext(), data="rby;42", decision="approve"))

	assert service.calls == []
	assert "仅中转频道管理员" in closed[0]
	assert notified == []
	assert takedowns == []


def test_review_approve(monkeypatch) -> None:
	service, _, closed, notified, takedowns = patch_handler(
		monkeypatch,
		service=FakeService(
			review=BlacklistReview("approved", "42", "作者", RECORD)))

	run(review_blacklist(
		FakeUpdate(), FakeContext(), data="rby;42", decision="approve"))

	assert service.calls == [("review", "42", "approve")]
	# 核验通过后下架该作者在频道里的历史分享
	assert takedowns == ["42"]
	assert "🈲 #作者下架申请已通过" in closed[0]
	assert "🚫 已下架：作者（#a42）" in closed[0]
	assert "已删除：2 条历史分享" in closed[0]
	assert len(notified) == 1
	assert "已通过" in notified[0][1]
	assert "历史分享已删除 2 条" in notified[0][1]


def test_review_approve_without_history(monkeypatch) -> None:
	_, _, closed, _, _ = patch_handler(
		monkeypatch,
		service=FakeService(
			review=BlacklistReview("approved", "42", "作者", RECORD)),
		takedown=TakedownResult("42"))

	run(review_blacklist(
		FakeUpdate(), FakeContext(), data="rby;42", decision="approve"))

	assert "已删除：0 条历史分享" in closed[0]


def test_review_approve_reports_takedown_failures(monkeypatch) -> None:
	_, _, closed, _, _ = patch_handler(
		monkeypatch,
		service=FakeService(
			review=BlacklistReview("approved", "42", "作者", RECORD)),
		takedown=TakedownResult("42", deleted=1, skipped=1, failed=1))

	run(review_blacklist(
		FakeUpdate(), FakeContext(), data="rby;42", decision="approve"))

	assert "已删除：1 条历史分享" in closed[0]
	assert "没有消息 ID" in closed[0]
	assert "删除失败，记录已保留可重试" in closed[0]


def test_review_approve_keeps_result_when_takedown_raises(monkeypatch) -> None:
	"""下架抛异常不影响核验结果与申请人通知。"""
	_, _, closed, notified, takedowns = patch_handler(
		monkeypatch,
		service=FakeService(
			review=BlacklistReview("approved", "42", "作者", RECORD)),
		takedown_error=RuntimeError("delete failed"))

	run(review_blacklist(
		FakeUpdate(), FakeContext(), data="rby;42", decision="approve"))

	assert takedowns == ["42"]
	assert "🚫 已下架：作者（#a42）" in closed[0]
	assert "已删除" not in closed[0]
	assert len(notified) == 1


def test_review_reject(monkeypatch) -> None:
	service, _, closed, notified, takedowns = patch_handler(
		monkeypatch,
		service=FakeService(
			review=BlacklistReview("rejected", "42", "作者", RECORD)))

	run(review_blacklist(
		FakeUpdate(), FakeContext(), data="rbn;42", decision="reject"))

	assert service.calls == [("review", "42", "reject")]
	# 拒绝不进名单，也不动频道里的历史分享
	assert takedowns == []
	assert "🈲 #作者下架申请已拒绝" in closed[0]
	assert "未通过" in notified[0][1]


def test_review_missing_and_already_processed(monkeypatch) -> None:
	_, _, closed, notified, takedowns = patch_handler(
		monkeypatch, service=FakeService(review=BlacklistReview("missing", "42")))
	run(review_blacklist(
		FakeUpdate(), FakeContext(), data="rby;42", decision="approve"))
	assert "申请记录不存在" in closed[0]
	assert takedowns == []

	_, _, closed, notified, takedowns = patch_handler(
		monkeypatch,
		service=FakeService(
			review=BlacklistReview("already_processed", "42", "作者", RECORD)))
	run(review_blacklist(
		FakeUpdate(), FakeContext(), data="rby;42", decision="approve"))
	assert "该申请已处理" in closed[0]
	assert notified == []
	assert takedowns == []


def patch_media(monkeypatch, *, submission, sent=True):
	service = FakeService(submission=submission)
	monkeypatch.setattr(media_handler, "BlacklistService", lambda: service)
	cards: list[JsonDict] = []

	async def fake_send(context, record) -> bool:
		cards.append(record)
		return sent

	monkeypatch.setattr(media_handler, "send_blacklist_card", fake_send)
	return service, cards


def test_on_photo_submits_material(monkeypatch) -> None:
	record = JsonDict(
		author_id="42", author_name="作者", photo_file_id="PHOTO")
	service, cards = patch_media(
		monkeypatch,
		submission=MaterialSubmission("submitted", record))
	message = FakeMessage()

	run(media_handler.on_photo(FakeUpdate(message), FakeContext()))

	assert service.calls == [("submit", 9, "PHOTO")]
	assert len(cards) == 1
	assert "材料已收到" in message.replies[-1]


def test_on_photo_without_request_is_silent(monkeypatch) -> None:
	service, cards = patch_media(
		monkeypatch, submission=MaterialSubmission("no_request"))
	message = FakeMessage()

	run(media_handler.on_photo(FakeUpdate(message), FakeContext()))

	assert cards == []
	assert message.replies == []


def test_on_photo_expired(monkeypatch) -> None:
	_, cards = patch_media(
		monkeypatch,
		submission=MaterialSubmission("expired", JsonDict(author_id="42")))
	message = FakeMessage()

	run(media_handler.on_photo(FakeUpdate(message), FakeContext()))

	assert cards == []
	assert "超时" in message.replies[-1]


def test_on_photo_send_failure(monkeypatch) -> None:
	record = JsonDict(author_id="42", photo_file_id="PHOTO")
	_, _cards = patch_media(
		monkeypatch,
		submission=MaterialSubmission("submitted", record),
		sent=False)
	message = FakeMessage()

	run(media_handler.on_photo(FakeUpdate(message), FakeContext()))

	assert "送审失败" in message.replies[-1]
