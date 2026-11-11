"""ApplyService：申请检查、重复待审、写入记录与送审编排。

运行（在项目根目录）:
	python -m pytest test/test_apply_service.py -q

说明：不依赖 pytest-asyncio，异步用例统一用 asyncio.run 驱动。
"""

from __future__ import annotations

import asyncio

import pytest

from services.apply_service import (
	ApplyService,
	ApplyInvalidLinkError,
)
from storage.applications import ApplicationStore


AUTHOR_LINK = "https://linpx.ink/pixiv/user/42"


def run(coro):
	return asyncio.run(coro)


class FakeList:
	def __init__(self, names: dict[str, str] | None = None) -> None:
		self.names = names or {}

	def get_name(self, author_id: str) -> str:
		return self.names.get(str(author_id), "")


class FakeListManager:
	def __init__(self, *, black=(), furry=()) -> None:
		self.black = {str(x) for x in black}
		self.furry = {str(x) for x in furry}
		self.blacklist = FakeList({x: f"黑名单{x}" for x in self.black})
		self.furrylist = FakeList({x: f"兽人{x}" for x in self.furry})

	def is_blacklisted(self, author_id: str) -> bool:
		return str(author_id) in self.black

	def is_furryauthor(self, author_id: str) -> bool:
		return str(author_id) in self.furry


class FakeAuthor:
	def __init__(self, author_name: str = "作者") -> None:
		self.author_name = author_name


def make_service(
	tmp_path,
	*,
	black=(),
	furry=(),
	fetch_name: str = "作者",
	fetch_calls: list[str] | None = None,
):
	store = ApplicationStore(path=tmp_path / "furry_request.json")

	async def fake_fetch(link: str) -> FakeAuthor:
		if fetch_calls is not None:
			fetch_calls.append(link)
		return FakeAuthor(fetch_name)

	service = ApplyService(
		applications=store,
		list_manager=FakeListManager(black=black, furry=furry),
		fetch_fn=fake_fetch,
	)
	return service, store


def test_inspect_needs_confirm(tmp_path) -> None:
	fetch_calls: list[str] = []
	service, _ = make_service(tmp_path, fetch_calls=fetch_calls)

	result = run(service.inspect(AUTHOR_LINK))

	assert result.status == "needs_confirm"
	assert result.author_id == "42"
	assert result.author_name == "作者"
	assert result.link == AUTHOR_LINK
	assert result.record is None
	assert fetch_calls == [AUTHOR_LINK]


def test_inspect_blacklisted_skips_fetch(tmp_path) -> None:
	fetch_calls: list[str] = []
	service, _ = make_service(
		tmp_path, black={"42"}, fetch_calls=fetch_calls)

	result = run(service.inspect(AUTHOR_LINK))

	assert result.status == "blacklisted"
	assert result.author_name == "黑名单42"
	assert fetch_calls == []


def test_inspect_already_furry_skips_fetch(tmp_path) -> None:
	fetch_calls: list[str] = []
	service, _ = make_service(
		tmp_path, furry={"42"}, fetch_calls=fetch_calls)

	result = run(service.inspect(AUTHOR_LINK))

	assert result.status == "already_furry"
	assert result.author_name == "兽人42"
	assert fetch_calls == []


def test_inspect_pending_skips_fetch(tmp_path) -> None:
	service, store = make_service(tmp_path)
	store.submit(
		"42", author_name="已有", link=AUTHOR_LINK,
		user_id=1, user_name="Alice")

	fetch_calls: list[str] = []
	service, _ = make_service(
		tmp_path, fetch_calls=fetch_calls)
	result = run(service.inspect(AUTHOR_LINK))

	assert result.status == "pending"
	assert result.author_name == "已有"
	assert result.record is not None
	assert fetch_calls == []


def test_submit_creates_record_and_sends_transit(tmp_path) -> None:
	service, store = make_service(tmp_path)
	sent = []

	async def send_transit(record) -> bool:
		sent.append(record)
		return True

	result = run(service.submit(
		AUTHOR_LINK, user_id=42, user_name="Alice",
		send_transit=send_transit))

	assert result.status == "submitted"
	assert result.author_id == "42"
	assert result.author_name == "作者"
	assert result.transit_sent is True
	assert result.record is not None
	assert result.record.count == 1
	assert len(sent) == 1

	record = store.get("42")
	assert record is not None
	assert record.status == ApplicationStore.STATUS_PENDING
	assert record.user_id == "42"
	assert record.user_name == "Alice"


def test_submit_pending_does_not_duplicate(tmp_path) -> None:
	service, store = make_service(tmp_path)
	sent = []

	async def send_transit(record) -> bool:
		sent.append(record)
		return True

	first = run(service.submit(
		AUTHOR_LINK, user_id=1, user_name="A",
		send_transit=send_transit))
	second = run(service.submit(
		AUTHOR_LINK, user_id=2, user_name="B",
		send_transit=send_transit))

	assert first.status == "submitted"
	assert second.status == "pending"
	assert second.record is not None
	assert second.record.count == 1
	assert len(sent) == 1
	assert store.get("42").count == 1


def test_submit_blacklisted_does_not_write(tmp_path) -> None:
	service, store = make_service(tmp_path, black={"42"})
	sent = []

	async def send_transit(record) -> bool:
		sent.append(record)
		return True

	result = run(service.submit(
		AUTHOR_LINK, user_id=1, user_name="A",
		send_transit=send_transit))

	assert result.status == "blacklisted"
	assert store.get("42") is None
	assert sent == []


def test_submit_transit_failure_keeps_record(tmp_path) -> None:
	service, store = make_service(tmp_path)

	async def send_transit(record) -> bool:
		raise RuntimeError("boom")

	result = run(service.submit(
		AUTHOR_LINK, user_id=1, user_name="A",
		send_transit=send_transit))

	assert result.status == "submitted"
	assert result.transit_sent is False
	assert store.get("42") is not None


def test_submit_without_transit(tmp_path) -> None:
	service, store = make_service(tmp_path)

	result = run(service.submit(
		AUTHOR_LINK, user_id=1, user_name="A"))

	assert result.status == "submitted"
	assert result.transit_sent is False
	assert store.get("42") is not None


def test_invalid_link_raises(tmp_path) -> None:
	service, _ = make_service(tmp_path)

	with pytest.raises(ApplyInvalidLinkError):
		run(service.inspect("https://linpx.ink/no-id"))
	with pytest.raises(ApplyInvalidLinkError):
		run(service.submit(
			"https://linpx.ink/no-id", user_id=1, user_name="A"))


def test_pending_records(tmp_path) -> None:
	service, _ = make_service(tmp_path)

	run(service.submit(AUTHOR_LINK, user_id=1, user_name="A"))
	records = service.pending_records()

	assert len(records) == 1
	assert records[0].author_id == "42"
	assert records[0].status == ApplicationStore.STATUS_PENDING
