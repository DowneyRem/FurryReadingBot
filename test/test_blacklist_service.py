"""BlacklistService：作者下架申请的状态流转与名单更新。

运行（在项目根目录）:
	python -m pytest test/test_blacklist_service.py -q
"""

from __future__ import annotations

import pytest

from services.blacklist_service import BlacklistService
from storage.blacklist_requests import BlacklistRequestStore


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


def make_service(tmp_path, manager=None):
	store = BlacklistRequestStore(path=tmp_path / "black_request.json")
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
	assert record.status == BlacklistRequestStore.STATUS_MATERIAL
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
	service, store, _ = make_service(tmp_path)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)

	record = store.get(AUTHOR_ID)
	assert record.status == BlacklistRequestStore.STATUS_MATERIAL
	assert record.count == 2


def test_request_pending_review_does_not_reopen(tmp_path) -> None:
	service, store, _ = make_service(tmp_path)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)
	store.attach_photo(AUTHOR_ID, "PHOTO")

	result = service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)

	assert result.status == "pending_review"
	assert store.get(AUTHOR_ID).status == BlacklistRequestStore.STATUS_REVIEW
	assert store.get(AUTHOR_ID).count == 1


def test_request_already_blacklisted(tmp_path) -> None:
	service, store, _ = make_service(
		tmp_path, FakeListManager(black={AUTHOR_ID}))

	result = service.request(AUTHOR_ID, author_url=AUTHOR_URL)

	assert result.status == "already_blacklisted"
	assert store.get(AUTHOR_ID) is None

def test_submit_material_marks_review(tmp_path) -> None:
	service, store, _ = make_service(tmp_path)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)

	result = service.submit_material(7, "PHOTO")

	assert result.status == "submitted"
	record = store.get(AUTHOR_ID)
	assert record.status == BlacklistRequestStore.STATUS_REVIEW
	assert record.photo_file_id == "PHOTO"


def test_submit_material_without_request(tmp_path) -> None:
	service, store, _ = make_service(tmp_path)

	result = service.submit_material(7, "PHOTO")

	assert result.status == "no_request"
	assert store.records() == {}


def test_submit_material_expired(tmp_path) -> None:
	service, store, _ = make_service(tmp_path)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)

	store.MATERIAL_TTL_MINUTES = 0
	result = service.submit_material(7, "PHOTO")

	assert result.status == "expired"
	assert store.get(AUTHOR_ID).status == BlacklistRequestStore.STATUS_MATERIAL


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
	assert store.get(AUTHOR_ID).status == BlacklistRequestStore.STATUS_APPROVED


def test_review_reject_keeps_lists(tmp_path) -> None:
	service, store, manager = make_service(tmp_path)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)
	service.submit_material(7, "PHOTO")

	result = service.review(AUTHOR_ID, "reject")

	assert result.status == "rejected"
	assert manager.calls == []
	assert AUTHOR_ID not in manager.black
	assert store.get(AUTHOR_ID).status == BlacklistRequestStore.STATUS_REJECTED


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

	assert store.get(AUTHOR_ID).status == BlacklistRequestStore.STATUS_REVIEW
	assert AUTHOR_ID not in manager.black


def test_unknown_decision_raises(tmp_path) -> None:
	service, store, _ = make_service(tmp_path)
	service.request(AUTHOR_ID, author_url=AUTHOR_URL, user_id=7)
	service.submit_material(7, "PHOTO")

	with pytest.raises(ValueError):
		service.review(AUTHOR_ID, "unknown")  # type: ignore[arg-type]
