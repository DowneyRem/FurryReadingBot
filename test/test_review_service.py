"""ReviewService：审核状态、名单更新、幂等与失败回滚。

运行（在项目根目录）:
	python -m pytest test/test_review_service.py -q
"""

from __future__ import annotations

import pytest

from services.review_service import ReviewService
from storage.application import ApplicationStore


AUTHOR_ID = "42"
AUTHOR_LINK = "https://linpx.ink/pixiv/user/42"


class FakeListManager:
	def __init__(self) -> None:
		self.furry: set[str] = set()
		self.black: set[str] = set()
		self.calls: list[tuple[str, str, str, str]] = []

	def add_furrylist(self, author_id, name: str = "", note: str = "") -> None:
		self.calls.append(("furry", str(author_id), name, note))
		self.furry.add(str(author_id))

	def add_blacklist(self, author_id, name: str = "", note: str = "") -> None:
		self.calls.append(("black", str(author_id), name, note))
		self.black.add(str(author_id))


class FailingFurryListManager(FakeListManager):
	def add_furrylist(self, author_id, name: str = "", note: str = "") -> None:
		raise RuntimeError("list write failed")


class FailingBlackListManager(FakeListManager):
	def add_blacklist(self, author_id, name: str = "", note: str = "") -> None:
		raise RuntimeError("list write failed")


def make_service(tmp_path, manager=None):
	store = ApplicationStore(path=tmp_path / "apply_authors.json")
	manager = manager or FakeListManager()
	service = ReviewService(applications=store, list_manager=manager)
	return service, store, manager


def submit(store: ApplicationStore, *, author_name: str = "作者") -> None:
	store.submit(
		AUTHOR_ID,
		author_name=author_name,
		link=AUTHOR_LINK,
		user_id=1,
		user_name="Alice",
	)


def test_approve_updates_status_and_furrylist(tmp_path) -> None:
	service, store, manager = make_service(tmp_path)
	submit(store)

	result = service.review(
		AUTHOR_ID, "approve", reviewer_id=9, reviewer_name="Admin")

	assert result.status == "approved"
	assert result.previous_status == ApplicationStore.STATUS_PENDING
	assert result.author_name == "作者"
	assert result.blacklisted is False
	assert result.record is not None
	assert result.record.status == ApplicationStore.STATUS_APPROVED
	assert AUTHOR_ID in manager.furry
	assert manager.calls == [
		("furry", AUTHOR_ID, "作者", "兽人作者申请通过"),
	]
	assert store.get(AUTHOR_ID).status == ApplicationStore.STATUS_APPROVED


def test_reject_updates_status_without_list(tmp_path) -> None:
	service, store, manager = make_service(tmp_path)
	submit(store)

	result = service.review(AUTHOR_ID, "reject")

	assert result.status == "rejected"
	assert result.record is not None
	assert result.record.status == ApplicationStore.STATUS_REJECTED
	assert result.blacklisted is False
	assert manager.calls == []
	assert store.get(AUTHOR_ID).status == ApplicationStore.STATUS_REJECTED


def test_blacklist_updates_status_and_blacklist(tmp_path) -> None:
	service, store, manager = make_service(tmp_path)
	submit(store)

	result = service.review(AUTHOR_ID, "blacklist")

	assert result.status == "rejected"
	assert result.blacklisted is True
	assert result.record is not None
	assert result.record.status == ApplicationStore.STATUS_REJECTED
	assert AUTHOR_ID in manager.black
	assert manager.calls == [
		("black", AUTHOR_ID, "作者", "申请核验未通过"),
	]


def test_missing_record(tmp_path) -> None:
	service, store, manager = make_service(tmp_path)

	result = service.review("404", "approve")

	assert result.status == "missing"
	assert result.author_id == "404"
	assert result.record is None
	assert manager.calls == []
	assert store.get("404") is None


def test_already_processed_does_nothing(tmp_path) -> None:
	service, store, manager = make_service(tmp_path)
	submit(store)
	store.set_status(AUTHOR_ID, ApplicationStore.STATUS_APPROVED)

	result = service.review(AUTHOR_ID, "approve")

	assert result.status == "already_processed"
	assert result.previous_status == ApplicationStore.STATUS_APPROVED
	assert result.record is not None
	assert manager.calls == []


def test_approve_is_idempotent(tmp_path) -> None:
	service, store, manager = make_service(tmp_path)
	submit(store)

	first = service.review(AUTHOR_ID, "approve")
	second = service.review(AUTHOR_ID, "approve")

	assert first.status == "approved"
	assert second.status == "already_processed"
	assert len(manager.calls) == 1
	assert len(manager.furry) == 1


def test_approve_rolls_back_status_when_list_fails(tmp_path) -> None:
	manager = FailingFurryListManager()
	service, store, _ = make_service(tmp_path, manager)
	submit(store)

	with pytest.raises(RuntimeError):
		service.review(AUTHOR_ID, "approve")

	record = store.get(AUTHOR_ID)
	assert record is not None
	assert record.status == ApplicationStore.STATUS_PENDING
	assert manager.furry == set()


def test_blacklist_rolls_back_status_when_list_fails(tmp_path) -> None:
	manager = FailingBlackListManager()
	service, store, _ = make_service(tmp_path, manager)
	submit(store)

	with pytest.raises(RuntimeError):
		service.review(AUTHOR_ID, "blacklist")

	record = store.get(AUTHOR_ID)
	assert record is not None
	assert record.status == ApplicationStore.STATUS_PENDING
	assert manager.black == set()


def test_unknown_decision_raises(tmp_path) -> None:
	service, store, _ = make_service(tmp_path)
	submit(store)

	with pytest.raises(ValueError):
		service.review(AUTHOR_ID, "unknown")  # type: ignore[arg-type]
