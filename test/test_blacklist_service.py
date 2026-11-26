"""BlacklistService：作者下架申请的状态流转与名单更新。

运行（在项目根目录）:
	python -m pytest test/test_blacklist_service.py -q
"""

from __future__ import annotations

import pytest

from services.blacklist_service import BlacklistService
from storage.black_request import BlackRequestStore


AUTHOR_ID = "42"
AUTHOR_URL = "https://linpx.ink/pixiv/user/42"


class FakeList:
	def __init__(self, names: dict[str, str] | None = None) -> None:
		self.names = dict(names or {})

	def get_name(self, author_id: str | int) -> str:
		return self.names.get(str(author_id), "")


class FakeListManager:
	def __init__(self, *, furry=(), black=()) -> None:
		self.furry = {str(x) for x in furry}
		self.black = {str(x) for x in black}
		self.furrylist = FakeList({x: f"兽人{x}" for x in self.furry})
		self.blacklist = FakeList({x: f"黑名单{x}" for x in self.black})
		self.calls: list[tuple] = []

	def is_blacklisted(self, author_id) -> bool:
		return str(author_id) in self.black

	def is_furryauthor(self, author_id) -> bool:
		return str(author_id) in self.furry

	def add_blacklist(self, author_id, name: str = "", note: str = "") -> None:
		self.calls.append(("black", str(author_id), name, note))
		self.black.add(str(author_id))

	def remove_furrylist(self, author_id) -> bool:
		self.calls.append(("unfurry", str(author_id)))
		self.furry.discard(str(author_id))
		return True


class FailingListManager(FakeListManager):
	def add_blacklist(self, author_id, name: str = "", note: str = "") -> None:
		raise RuntimeError("list write failed")


def make_service(tmp_path, manager=None, *, cooldown_hours: float | None = None):
	store = BlackRequestStore(
		path=tmp_path / "black_request.json",
		apply_cooldown_hours=cooldown_hours,
	)
	manager = manager or FakeListManager()
	service = BlacklistService(store, list_manager=manager)
	return service, store, manager


def test_request_needs_material(tmp_path) -> None:
	service, store, _ = make_service(tmp_path)

	result = service.request(
		AUTHOR_ID, author_url=AUTHOR_URL, author_name="作者",
		user_id=7, user_name="Alice")

	assert result.status == "needs_material"
	record = store.get(AUTHOR_ID)
	assert record is not None
	assert record.status == BlackRequestStore.STATUS_MATERIAL
	assert record.author_url == AUTHOR_URL
	assert record.author_name == "作者"
	assert record.user_id == "7"
	assert record.count == 1
	assert record.photo_file_id == ""


def test_request_prefers_caller_name_then_list(tmp_path) -> None:
	service, store, _ = make_service(
		tmp_path, FakeListManager(furry={AUTHOR_ID}))

	service.request(AUTHOR_ID, author_url=AUTHOR_URL)
	assert store.get(AUTHOR_ID).author_name == "兽人42"

	service.request(AUTHOR_ID, author_url=AUTHOR_URL, author_name="抓到的名字")
	assert store.get(AUTHOR_ID).author_name == "抓到的名字"


def test_request_again_reopens_material(tmp_path) -> None:
	"""(只受理、不交截图不算一次申请：不占 1 天冷却)"""
	service, store, _ = make_service(tmp_path)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)

	record = store.get(AUTHOR_ID)
	assert record.status == BlackRequestStore.STATUS_MATERIAL
	assert record.count == 2


def test_request_pending_review_does_not_reopen(tmp_path) -> None:
	service, store, _ = make_service(tmp_path)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)
	store.attach_photo(AUTHOR_ID, "PHOTO")

	result = service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)

	assert result.status == "pending_review"
	assert store.get(AUTHOR_ID).status == BlackRequestStore.STATUS_REVIEW
	assert store.get(AUTHOR_ID).count == 1


def test_request_already_blacklisted(tmp_path) -> None:
	service, store, _ = make_service(
		tmp_path, FakeListManager(black={AUTHOR_ID}))

	result = service.request(AUTHOR_ID, author_url=AUTHOR_URL)

	assert result.status == "already_blacklisted"
	assert store.get(AUTHOR_ID) is None


def test_request_after_reject_hits_cooldown(tmp_path) -> None:
	"""送审被拒后 1 天内不能再申请：同一作者 1 天只能申请一次。"""
	service, store, _ = make_service(tmp_path)
	service.request(
		AUTHOR_ID, author_url=AUTHOR_URL, author_name="作者", user_id=7)
	service.submit_material(7, "PHOTO")
	service.review(AUTHOR_ID, "reject")

	result = service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)

	assert result.status == "cooldown"
	assert result.author_name == "作者"
	assert 0 < result.remaining_seconds <= 24 * 3600
	assert store.get(AUTHOR_ID).status == BlackRequestStore.STATUS_REJECTED
	assert store.get(AUTHOR_ID).count == 1


def test_request_after_reject_allowed_when_cooldown_zero(tmp_path) -> None:
	service, store, _ = make_service(tmp_path, cooldown_hours=0)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)
	service.submit_material(7, "PHOTO")
	service.review(AUTHOR_ID, "reject")

	result = service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)

	assert result.status == "needs_material"
	assert store.get(AUTHOR_ID).status == BlackRequestStore.STATUS_MATERIAL
	assert store.get(AUTHOR_ID).count == 2


def test_other_user_cannot_take_over_pending_material(tmp_path) -> None:
	"""同一作者只允许同一用户受理：别人正在交截图时，第二位用户被挡下。"""
	service, store, _ = make_service(tmp_path)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)

	result = service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=8)

	assert result.status == "other_applicant"
	assert result.record is not None
	assert result.record.user_id == "7"
	record = store.get(AUTHOR_ID)
	assert record.user_id == "7"      # 没有被覆盖
	assert record.count == 1
	# 第一位用户之后仍能正常交截图（不会再被静默丢弃）
	assert service.submit_material(7, "PHOTO").status == "submitted"


def test_other_user_cannot_take_over_review(tmp_path) -> None:
	service, store, _ = make_service(tmp_path)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)
	service.submit_material(7, "PHOTO")

	result = service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=8)

	assert result.status == "other_applicant"
	assert result.record is not None
	assert result.record.status == BlackRequestStore.STATUS_REVIEW
	assert store.get(AUTHOR_ID).user_id == "7"


def test_rejected_record_does_not_lock_author(tmp_path) -> None:
	"""被拒的记录不能再挡住别人：冷却过去后应由新用户接手。"""
	service, store, _ = make_service(tmp_path, cooldown_hours=0)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)
	service.submit_material(7, "PHOTO")
	service.review(AUTHOR_ID, "reject")

	result = service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=8)

	assert result.status == "needs_material"
	record = store.get(AUTHOR_ID)
	assert record.user_id == "8"
	assert record.status == BlackRequestStore.STATUS_MATERIAL
	assert record.count == 2


def test_rejected_record_blocks_other_user_only_by_cooldown(tmp_path) -> None:
	"""冷却期内别人也该拿到冷却提示，而不是「已由其他用户受理」。"""
	service, _store, _ = make_service(tmp_path)   # 默认 24h
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)
	service.submit_material(7, "PHOTO")
	service.review(AUTHOR_ID, "reject")

	result = service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=8)

	assert result.status == "cooldown"
	assert 0 < result.remaining_seconds <= 24 * 3600


def test_same_user_can_reopen_material(tmp_path) -> None:
	"""本人重复点受理：允许（只刷新材料窗口）。"""
	service, store, _ = make_service(tmp_path)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)

	result = service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)

	assert result.status == "needs_material"
	assert store.get(AUTHOR_ID).count == 2


def test_expired_material_does_not_lock_author(tmp_path) -> None:
	"""没人交截图的僵尸受理过期后必须放行，否则作者会被永久占住。"""
	service, store, _ = make_service(tmp_path)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)
	store.material_ttl_minutes = 0

	result = service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=8)

	assert result.status == "needs_material"
	assert store.get(AUTHOR_ID).user_id == "8"


def test_other_author_material_blocks_new_request(tmp_path) -> None:
	"""同一用户同时只留一条待交材料：先把上一张交了再申请别的作者。"""
	service, store, _ = make_service(tmp_path)
	service.request(
		AUTHOR_ID, author_url=AUTHOR_URL, author_name="作者A", user_id=7)

	result = service.request(
		"99", author_url="https://linpx.ink/pixiv/user/99", user_id=7)

	assert result.status == "material_open"
	assert result.pending_record is not None
	assert result.pending_record.author_id == AUTHOR_ID
	assert 0 < result.remaining_seconds <= 30 * 60
	# 新作者没有被受理，旧材料仍然有效
	assert store.get("99") is None
	assert store.get(AUTHOR_ID).status == BlackRequestStore.STATUS_MATERIAL


def test_expired_other_author_material_does_not_block(tmp_path) -> None:
	service, store, _ = make_service(tmp_path)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)
	store.material_ttl_minutes = 0

	result = service.request(
		"99", author_url="https://linpx.ink/pixiv/user/99", user_id=7)

	assert result.status == "needs_material"
	assert store.get(AUTHOR_ID) is None      # 过期的那条已作废
	assert store.get("99") is not None

def test_submit_material_marks_review(tmp_path) -> None:
	service, store, _ = make_service(tmp_path)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)

	result = service.submit_material(7, "PHOTO")

	assert result.status == "submitted"
	record = store.get(AUTHOR_ID)
	assert record.status == BlackRequestStore.STATUS_REVIEW
	assert record.photo_file_id == "PHOTO"


def test_submit_material_without_request(tmp_path) -> None:
	service, store, _ = make_service(tmp_path)

	result = service.submit_material(7, "PHOTO")

	assert result.status == "no_request"
	assert store.records() == {}


def test_submit_material_expired(tmp_path) -> None:
	service, store, _ = make_service(tmp_path)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)

	store.material_ttl_minutes = 0
	result = service.submit_material(7, "PHOTO")

	assert result.status == "expired"
	# 只提示一次：之后同一用户再发图按普通图片忽略
	assert service.submit_material(7, "PHOTO").status == "no_request"


def test_review_approve_blacklists_and_unlists(tmp_path) -> None:
	service, store, manager = make_service(
		tmp_path, FakeListManager(furry={AUTHOR_ID}))
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)
	service.submit_material(7, "PHOTO")

	result = service.review(AUTHOR_ID, "approve")

	assert result.status == "approved"
	assert AUTHOR_ID in manager.black
	assert AUTHOR_ID not in manager.furry
	assert manager.calls == [
		("black", AUTHOR_ID, "兽人42", "作者本人申请下架"),
		("unfurry", AUTHOR_ID),
	]
	assert store.get(AUTHOR_ID).status == BlackRequestStore.STATUS_APPROVED


def test_review_reject_keeps_lists(tmp_path) -> None:
	service, store, manager = make_service(tmp_path)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)
	service.submit_material(7, "PHOTO")

	result = service.review(AUTHOR_ID, "reject")

	assert result.status == "rejected"
	assert manager.calls == []
	assert AUTHOR_ID not in manager.black
	assert store.get(AUTHOR_ID).status == BlackRequestStore.STATUS_REJECTED


def test_review_missing_or_already_processed(tmp_path) -> None:
	service, store, _ = make_service(tmp_path)
	assert service.review("404", "approve").status == "missing"

	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)
	assert service.review(AUTHOR_ID, "approve").status == "already_processed"

	service.submit_material(7, "PHOTO")
	assert service.review(AUTHOR_ID, "reject").status == "rejected"
	assert service.review(AUTHOR_ID, "reject").status == "already_processed"


def test_review_rolls_back_when_list_write_fails(tmp_path) -> None:
	manager = FailingListManager()
	service, store, _ = make_service(tmp_path, manager)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)
	service.submit_material(7, "PHOTO")

	with pytest.raises(RuntimeError):
		service.review(AUTHOR_ID, "approve")

	assert store.get(AUTHOR_ID).status == BlackRequestStore.STATUS_REVIEW
	assert AUTHOR_ID not in manager.black


def test_unknown_decision_raises(tmp_path) -> None:
	service, store, _ = make_service(tmp_path)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)
	service.submit_material(7, "PHOTO")

	with pytest.raises(ValueError):
		service.review(AUTHOR_ID, "unknown")  # type: ignore[arg-type]


def test_retry_takedown_only_for_blacklisted(tmp_path) -> None:
	service, _store, manager = make_service(tmp_path)
	assert service.can_retry_takedown(AUTHOR_ID) is False

	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)
	service.submit_material(7, "PHOTO")
	service.review(AUTHOR_ID, "approve")

	assert service.can_retry_takedown(AUTHOR_ID) is True
	assert service.review(AUTHOR_ID, "approve").status == "already_processed"

def test_pending_review_records_for_resend(tmp_path) -> None:
	service, _store, _ = make_service(tmp_path)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)
	assert service.pending_review_records() == []

	service.submit_material(7, "PHOTO")

	assert [r.author_id for r in service.pending_review_records()] == [AUTHOR_ID]
